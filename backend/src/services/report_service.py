import csv,io
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.review import FieldReview
from ..models.run import KrigingRun
from ..models.report import Report
from . import calibration_service

def create(db,body):
 review=db.get(FieldReview,body.review_id)
 if review is None or review.state!="approved":raise HTTPException(409,"报告须关联已批准的空间推断复核")
 existing=db.scalar(select(Report).where(Report.review_id==body.review_id))
 if existing:
  # 已批准底稿不可变；CSV导出时仍会采用该运行当前通过的校正版本。
  return existing
 run=db.get(KrigingRun,review.run_id)
 # 快照采用发布时当前有效的校正版本（若有），并原样锁定，后续校正不影响已批准底稿。
 applied=calibration_service.current_applied(db,run.id)
 snapshot={"result":run.result,"action":review.action,"reviewer":review.reviewer,"run_id":run.id,"calibration_version":applied.version if applied else None,"calibration":applied.payload if applied else None}
 row=Report(id=str(uuid4()),review_id=review.id,title=body.title,snapshot=snapshot);db.add(row);db.commit();return row

def _effective_points(db,row):
 snapshot=row.snapshot;result=snapshot["result"];rows=[dict(p) for p in result["kriging"]["predictions"]]
 # 导出采用当前通过的校正版本；若运行没有新的通过版本，则沿用快照中锁定的版本。
 run_id=snapshot.get("run_id")
 if not run_id:
  review=db.get(FieldReview,row.review_id);run_id=review.run_id if review else None
 applied=calibration_service.current_applied(db,run_id) if run_id else None
 calibration=applied.payload if applied is not None else snapshot.get("calibration")
 if not calibration:return rows,None
 after={row["query_id"]:row for row in calibration.get("points",[])}
 for point in rows:
  row=after.get(point["query_id"])
  if row is None:continue
  point["original_prediction"]=point["prediction"];point["prediction"]=row["after"];point["calibration_change"]=row["change"]
 return rows,calibration

def export(db,row):
 snapshot=row.snapshot;result=snapshot["result"];model=result["model"];points,calibration=_effective_points(db,row)
 version="" if not calibration else calibration.get("version","")
 out=io.StringIO();writer=csv.writer(out);writer.writerow(["query_id","x_m","y_m","prediction_percent","field_variance_pp2","field_sd_pp","raw_variance","micro_negative_clipped","weight_sum","mu","sill","range_m","nugget","condition_number","input_sha256","original_prediction_percent","calibration_change","calibration_version"])
 for p in points:writer.writerow([p["query_id"],p["x"],p["y"],p["prediction"],p["variance"],p["standard_deviation"],p["raw_variance"],p["variance_clipped"],p["weight_sum"],p["mu"],model["sill"],model["range"],model["nugget"],result["kriging"]["condition_number"],result["input_sha256"],p.get("original_prediction",""),p.get("calibration_change",""),version])
 return "\ufeff"+out.getvalue()
