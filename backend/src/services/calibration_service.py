from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models.calibration import Calibration
from . import calibration


def _version(db, run_id):
    return (
        db.scalar(
            select(Calibration.version)
            .where(Calibration.run_id == run_id)
            .order_by(Calibration.version.desc())
            .limit(1)
        )
        or 0
    )


def _snapshot(row):
    return {
        "id": row.id,
        "run_id": row.run_id,
        "version": row.version,
        "state": row.state,
        "error": row.error,
        "conflict_zones": row.conflict_zones or [],
        "input_sha256": row.input_sha256,
        "actor": row.actor,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        "payload": row.payload or {},
    }


def _current(db, run_id, states):
    return db.scalar(
        select(Calibration)
        .where(Calibration.run_id == run_id, Calibration.state.in_(states))
        .order_by(Calibration.version.desc())
        .limit(1)
    )


def current_applied(db, run_id):
    return _current(db, run_id, ["applied"])


def history(db, run_id):
    rows = db.scalars(
        select(Calibration).where(Calibration.run_id == run_id).order_by(Calibration.version)
    ).all()
    return [_snapshot(row) for row in rows]


def effective_points(db, run_id, result):
    """展示与导出用：当前通过的校正版本优先，否则用原推断。"""
    points = [dict(p) for p in result.get("kriging", {}).get("predictions", [])]
    applied = current_applied(db, run_id)
    if applied is None:
        return points, None
    payload = applied.payload or {}
    after = {row["query_id"]: row for row in payload.get("points", [])}
    for point in points:
        row = after.get(point["query_id"])
        if row is None:
            continue
        point["original_prediction"] = point["prediction"]
        point["prediction"] = row["after"]
        point["calibration_change"] = row["change"]
        point["calibration_locked"] = row["locked"]
    return points, applied


def _record_failure(db, run_id, version, fingerprint, actor, reason, message, diagnostics=None, conflict=None):
    # 失败版本单独成行；旧通过版本从未被触碰，因此无需回滚校正数据。
    try:
        db.add(
            Calibration(
                id=str(uuid4()),
                run_id=run_id,
                version=version,
                state="failed",
                payload={"version": version, "reason": reason, "message": message, "zones": diagnostics or []},
                error=message[:2000],
                conflict_zones=conflict or [],
                input_sha256=fingerprint,
                actor=actor,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "另一校正版本正在写入，请刷新后重试；旧版本未受影响")


def create(db, run, zones, actor, means_sha256=""):
    """计算并原子替换。任一校验失败则保留旧通过版本，仅登记失败版本行。"""
    base = run.result or {}
    if run.status != "completed" or not base.get("kriging", {}).get("predictions"):
        raise HTTPException(409, "仅已完成且含预测的运行可做分区校正")
    version = _version(db, run.id) + 1
    fingerprint = calibration.canonical_hash(
        {
            "run_id": run.id,
            "version": version,
            "means_sha256": means_sha256,
            "zones": [
                {"zone_id": z["zone_id"], "measured_mean": z["measured_mean"], "weights": z["weights"]}
                for z in zones
            ],
            "predictions": [
                {"query_id": p["query_id"], "prediction": p["prediction"], "variance": p["variance"]}
                for p in base["kriging"]["predictions"]
            ],
        }
    )
    system = None
    try:
        system = calibration.build_system(zones, base["kriging"]["predictions"])
        payload, _ = calibration.calibrate_result(base, zones, system=system)
        payload["run_id"] = run.id
        payload["version"] = version
        payload["source"] = {"run_input_sha256": base.get("input_sha256", ""), "zones": len(zones)}
    except calibration.CalibrationConflict as error:
        conflicts = error.conflict_zones
        message = (
            "分区均值约束相互矛盾，无法同时满足（冲突分区："
            + ("、".join(conflicts) if conflicts else "全部")
            + "）。请核对重叠分区的实测均值、面积权重与零方差锁定点。"
        )
        _record_failure(
            db,
            run.id,
            version,
            fingerprint,
            actor,
            "conflict",
            message,
            diagnostics=error.zone_diagnostics,
            conflict=conflicts,
        )
        raise HTTPException(
            422,
            {
                "message": message,
                "reason": "conflict",
                "conflict_zones": conflicts,
                "zone_diagnostics": error.zone_diagnostics,
                "version": version,
                "kept_version": _version(db, run.id) - 1,
            },
        )
    except calibration.CalibrationInputError as error:
        raise HTTPException(422, {"message": str(error), "reason": "input"})
    except calibration.CalibrationValidationError as error:
        _record_failure(db, run.id, version, fingerprint, actor, "validation", str(error))
        raise HTTPException(
            422,
            {
                "message": "校正结果未通过全部校验，旧版本保留：" + str(error),
                "reason": "validation",
                "conflict_zones": [],
                "version": version,
                "kept_version": _version(db, run.id) - 1,
            },
        )
    row = Calibration(
        id=str(uuid4()),
        run_id=run.id,
        version=version,
        state="applied",
        payload=payload,
        conflict_zones=[],
        input_sha256=fingerprint,
        actor=actor,
    )
    # 每个运行仅保留一个已通过版本；旧版本标为 superseded，历史与原推断仍可回看。
    # 新版本与替换在同一事务提交，失败则整体回滚、旧版继续生效。
    try:
        db.add(row)
        db.flush()
        for previous in db.scalars(
            select(Calibration).where(Calibration.run_id == run.id, Calibration.state == "applied")
        ).all():
            if previous.id != row.id:
                previous.state = "superseded"
                previous.payload = {**(previous.payload or {}), "superseded_by": version}
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "另一校正版本正在写入，请刷新后重试；旧版本未受影响")
    return _snapshot(row)
