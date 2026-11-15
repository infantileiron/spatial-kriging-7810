"""分区均值联合校正。

给定一次普通克里金运行的逐点预测 x 与空间方差 v，以及若干（可重叠）分区：
每个待估点在每个分区中有面积权重 w，分区的面积加权均值必须等于外业实测均值 b。

校正只调整预测点值 y，不改变变异函数、权重或模型方差；原推断 x 始终保留。
目标函数为

    sum_i (y_i - x_i)^2 / v_i

即按原空间方差倒数加权的最小改动平方和，等价于马氏意义下的最小总改变量。
v_i = 0 的点不参与调整，锁定在原预测值；所有自由点值限制在 [0, 100] 含水率区间。
约束矩阵按分区内面积权重归一化，因此各分区面积权重可按任意正数导入。
"""
import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

LOWER = 0.0
UPPER = 100.0
MAX_ZONES = 100
MAX_POINTS = 100
MAX_ROWS = 5000
CONSTRAINT_TOLERANCE = 1e-7


class CalibrationInputError(ValueError):
    """导入的分区/权重/均值格式不合法。"""


class CalibrationConflict(ValueError):
    """约束与边界或锁定点相互矛盾，无法同时满足。"""

    def __init__(self, message, conflict_zones=None, zone_diagnostics=None):
        super().__init__(message)
        self.conflict_zones = list(conflict_zones or [])
        self.zone_diagnostics = list(zone_diagnostics or [])


class CalibrationValidationError(ValueError):
    """求解结果未通过全部数值校验，拒绝替换旧版本。"""


@dataclass
class System:
    query_ids: list
    x: np.ndarray
    variance: np.ndarray
    locked: np.ndarray
    free: np.ndarray
    A_full: np.ndarray
    A: np.ndarray
    b: np.ndarray
    b_effective: np.ndarray


def _finite_number(raw, field, line_no):
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise CalibrationInputError(f"第{line_no}行{field}须为数值")
    if not math.isfinite(value):
        raise CalibrationInputError(f"第{line_no}行{field}须为有限数值")
    return value


def _clean_identifier(raw, field, line_no):
    value = (raw or "").strip().lstrip("﻿") if isinstance(raw, str) else ""
    if not value:
        raise CalibrationInputError(f"第{line_no}行{field}不能为空")
    if len(value) > 80:
        raise CalibrationInputError(f"第{line_no}行{field}长度不得超过80字符")
    return value


def _rows(text, required, label):
    if not isinstance(text, str) or not text.strip():
        raise CalibrationInputError(f"{label}不能为空")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise CalibrationInputError(f"{label}缺少表头")
    fields = {str(name).strip() for name in reader.fieldnames if name is not None}
    missing = required - fields
    if missing:
        raise CalibrationInputError(f"{label}缺少列：{', '.join(sorted(missing))}")
    count = 0
    for row in reader:
        if not any((value or "").strip() for key, value in row.items() if key is not None):
            continue
        count += 1
        if count > MAX_ROWS:
            raise CalibrationInputError(f"{label}行数超过{MAX_ROWS}")
        yield row


def parse_zone_weights(text):
    """解析 `zone_id,query_id,area_weight[,measured_mean]`。

    同一对待估点与分区只能出现一次；同一分区可覆盖任意多个待估点，
    不同分区可以重叠。可选 measured_mean 列便于把分区与实测均值放在一个文件里。
    """
    zones = {}
    rows = _rows(text, {"zone_id", "query_id", "area_weight"}, "分区权重CSV")
    has_mean = None
    for line_no, row in enumerate(rows, start=2):
        if has_mean is None:
            has_mean = "measured_mean" in {str(k).strip() for k in row if k is not None}
        zone_id = _clean_identifier(row.get("zone_id"), "zone_id", line_no)
        query_id = _clean_identifier(row.get("query_id"), "query_id", line_no)
        weight = _finite_number(row.get("area_weight"), "area_weight", line_no)
        if weight <= 0:
            raise CalibrationInputError(f"第{line_no}行面积权重须严格为正")
        entry = zones.setdefault(zone_id, {"weights": {}, "measured_mean": None})
        if query_id in entry["weights"]:
            raise CalibrationInputError(f"分区{zone_id}中的待估点{query_id}重复出现")
        entry["weights"][query_id] = weight
        if has_mean:
            mean = _finite_number(row.get("measured_mean"), "measured_mean", line_no)
            if not LOWER <= mean <= UPPER:
                raise CalibrationInputError(f"第{line_no}行实测均值须在0–100%之间")
            if entry["measured_mean"] is not None and not math.isclose(entry["measured_mean"], mean, rel_tol=0, abs_tol=1e-12):
                raise CalibrationInputError(f"分区{zone_id}的实测均值在同一文件中不一致")
            entry["measured_mean"] = mean
        if len(zones) > MAX_ZONES:
            raise CalibrationInputError(f"分区数量超过{MAX_ZONES}")
    if not zones:
        raise CalibrationInputError("分区权重CSV没有有效数据行")
    return zones, bool(has_mean)


def parse_means(text):
    means = {}
    rows = _rows(text, {"zone_id", "measured_mean"}, "实测均值CSV")
    for line_no, row in enumerate(rows, start=2):
        zone_id = _clean_identifier(row.get("zone_id"), "zone_id", line_no)
        mean = _finite_number(row.get("measured_mean"), "measured_mean", line_no)
        if not LOWER <= mean <= UPPER:
            raise CalibrationInputError(f"第{line_no}行实测均值须在0–100%之间")
        if zone_id in means:
            raise CalibrationInputError(f"实测均值CSV中分区{zone_id}重复出现")
        means[zone_id] = mean
        if len(means) > MAX_ZONES:
            raise CalibrationInputError(f"实测均值分区数量超过{MAX_ZONES}")
    if not means:
        raise CalibrationInputError("实测均值CSV没有有效数据行")
    return means


def prepare_zones(zones_csv, means_csv, query_ids):
    """合并分区、面积权重与实测均值，并校验待估点引用。"""
    zones, _ = parse_zone_weights(zones_csv)
    means = {}
    if isinstance(means_csv, str) and means_csv.strip():
        means = parse_means(means_csv)
    if means:
        for zone_id, mean in means.items():
            if zone_id not in zones:
                raise CalibrationInputError(f"实测均值中的分区{zone_id}没有对应的面积权重")
            existing = zones[zone_id]["measured_mean"]
            if existing is not None and not math.isclose(existing, mean, rel_tol=0, abs_tol=1e-12):
                raise CalibrationInputError(f"分区{zone_id}的实测均值在分区CSV与均值CSV中不一致")
            zones[zone_id]["measured_mean"] = mean
    missing = sorted(zone_id for zone_id, entry in zones.items() if entry["measured_mean"] is None)
    if missing:
        raise CalibrationInputError("以下分区缺少实测均值：" + "、".join(missing))
    known = set(query_ids)
    unknown = sorted({query_id for entry in zones.values() for query_id in entry["weights"] if query_id not in known})
    if unknown:
        shown = "、".join(unknown[:8]) + ("等" if len(unknown) > 8 else "")
        raise CalibrationInputError(f"分区引用了不存在的待估点：{shown}")
    result = []
    for zone_id in sorted(zones):
        entry = zones[zone_id]
        weight_sum = float(sum(entry["weights"].values()))
        if not math.isfinite(weight_sum) or weight_sum <= 0:
            raise CalibrationInputError(f"分区{zone_id}的面积权重合计无效")
        result.append(
            {
                "zone_id": zone_id,
                "measured_mean": float(entry["measured_mean"]),
                "weights": dict(entry["weights"]),
                "area_weight_sum": weight_sum,
            }
        )
    if len(result) > MAX_ZONES:
        raise CalibrationInputError(f"分区数量超过{MAX_ZONES}")
    return result


def build_system(zones, predictions):
    if not predictions:
        raise CalibrationInputError("运行没有可校正的预测点")
    if len(predictions) > MAX_POINTS:
        raise CalibrationInputError(f"待估点数量超过{MAX_POINTS}")
    query_ids = [p["query_id"] for p in predictions]
    x = np.asarray([float(p["prediction"]) for p in predictions], dtype=np.float64)
    variance = np.asarray([float(p["variance"]) for p in predictions], dtype=np.float64)
    if not np.isfinite(x).all() or not np.isfinite(variance).all():
        raise CalibrationInputError("原预测值或空间方差非有限")
    if (variance < 0).any():
        raise CalibrationInputError("原空间方差不能为负")
    locked = variance <= 0
    free = ~locked
    index = {query_id: i for i, query_id in enumerate(query_ids)}
    A_full = np.zeros((len(zones), len(query_ids)), dtype=np.float64)
    b = np.zeros(len(zones), dtype=np.float64)
    for row, zone in enumerate(zones):
        total = zone["area_weight_sum"]
        for query_id, weight in zone["weights"].items():
            A_full[row, index[query_id]] = float(weight) / total
        b[row] = zone["measured_mean"]
    # 锁定点的贡献移到等式右端；自由点保留为变量。
    A = A_full[:, free]
    b_effective = b - (A_full[:, locked] @ x[locked] if locked.any() else 0.0)
    return System(query_ids, x, variance, locked, free, A_full, A, b, b_effective)


def lp_feasible(A, b, lower=LOWER, upper=UPPER):
    rows = A.shape[0]
    if rows == 0:
        return True
    if A.shape[1] == 0:
        return bool(np.max(np.abs(b), initial=0.0) <= 1e-9)
    result = linprog(
        np.zeros(A.shape[1], dtype=np.float64),
        A_eq=A,
        b_eq=b,
        bounds=[(lower, upper)] * A.shape[1],
        method="highs",
    )
    return result.status == 0


def zone_diagnostics(system, zones):
    """给出每个分区单独可达到的加权均值区间（考虑锁定点与0–100%边界）。"""
    diagnostics = []
    for zone in zones:
        total = zone["area_weight_sum"]
        locked_sum = 0.0
        free_sum = 0.0
        locked_count = 0
        for query_id, weight in zone["weights"].items():
            position = system.query_ids.index(query_id)
            if system.locked[position]:
                locked_sum += weight * system.x[position]
                locked_count += 1
            else:
                free_sum += weight
        low = (locked_sum + free_sum * LOWER) / total
        high = (locked_sum + free_sum * UPPER) / total
        target = zone["measured_mean"]
        diagnostics.append(
            {
                "zone_id": zone["zone_id"],
                "measured_mean": target,
                "achievable_min": float(low),
                "achievable_max": float(high),
                "point_count": len(zone["weights"]),
                "locked_point_count": locked_count,
                "individually_satisfiable": bool(low - 1e-9 <= target <= high + 1e-9),
            }
        )
    return diagnostics


def find_conflicting_zones(system, zones):
    """删除过滤法求一个极小矛盾分区子集，并标出其中每个分区的可达到区间。

    冗余但一致的约束不会进入结果；单个分区自身不可满足时也会直接入选。
    """
    rows = list(range(system.A.shape[0]))
    if not lp_feasible(system.A, system.b_effective):
        for candidate in range(system.A.shape[0]):
            if candidate not in rows:
                continue
            trial = [row for row in rows if row != candidate]
            if not lp_feasible(system.A[trial], system.b_effective[trial]):
                rows = trial
    return [zones[row]["zone_id"] for row in rows], rows


def conflict_diagnostics(system, zones, rows):
    """冲突分区：单独可达到区间、锁定点面积权重与极小冲突子集标记。"""
    standalone = {row["zone_id"]: row for row in zone_diagnostics(system, zones)}
    index = {query_id: position for position, query_id in enumerate(system.query_ids)}
    output = []
    for row in rows:
        zone = zones[row]
        weights = zone["weights"]
        total = zone["area_weight_sum"]
        locked_weight = sum(w for q, w in weights.items() if system.locked[index[q]])
        output.append(
            {
                **standalone[zone["zone_id"]],
                "in_minimal_conflict_set": True,
                "locked_area_weight_sum": float(locked_weight),
                "locked_area_weight_fraction": float(locked_weight / total) if total else 0.0,
            }
        )
    return output


def dual_lower_bound(x, variance, A, b, lam):
    """对偶函数值 g(lam)：箱约束下 inf_y [0.5*sum((y-x)^2/v) + lam^T(Ay-b)]。

    对任何可行 y 有 g(lam) <= 最优值 <= 原目标值，因此
    `primal(y) - g(lam)` 是可直接计算的最优性证书（强对偶间隙）。
    """
    slack = A.T @ lam
    y = np.clip(x - variance * slack, LOWER, UPPER)
    penalized = float(np.sum(((y - x) ** 2) / (2.0 * variance))) + float(slack @ (y - x))
    return float(lam @ (A @ x - b) + penalized)


def _solve_equality_on_free(x, variance, A, b, free, fixed_y):
    """固定触界点后，在自由变量上精确解等式约束二次问题。

    KKT 约定：y = x - V A^T lam，故 (y-x)/v + A^T lam = 0。
    """
    fixed_term = A[:, ~free] @ fixed_y[~free] if (~free).any() else 0.0
    if not free.any():
        return None, None
    A_free = A[:, free]
    v_free = variance[free]
    gram = (A_free * v_free[None, :]) @ A_free.T
    try:
        lam = np.linalg.lstsq(gram, A_free @ x[free] + fixed_term - b, rcond=1e-14)[0]
    except np.linalg.LinAlgError:
        return None, None
    candidate = fixed_y.copy()
    candidate[free] = x[free] - v_free * (A_free.T @ lam)
    return candidate, lam


def _feasible_start(A, b, x):
    """用线性规划得到等式约束 + 箱约束的一个可行起点。"""
    if A.shape[0] == 0:
        return np.clip(x, LOWER, UPPER)
    result = linprog(
        np.zeros(A.shape[1], dtype=np.float64),
        A_eq=A,
        b_eq=b,
        bounds=[(LOWER, UPPER)] * A.shape[1],
        method="highs",
    )
    if result.status != 0:
        return None
    return np.clip(np.asarray(result.x, dtype=np.float64), LOWER, UPPER)


def solve_min_change(system, max_iterations=2000):
    """原-对偶活跃集法解箱约束等式二次规划。

    目标 min Σ (y-x)²/v，s.t. A y = b，0 ≤ y ≤ 100。
    从LP可行起点出发，按“沿方向走到第一个边界、固定该点、KKT复核、释放违反符号的点”迭代。
    最终解必须通过可行性与对偶间隙证书，否则标记为失败供上层拒绝替换。
    """
    x = system.x[system.free]
    variance = system.variance[system.free]
    A = system.A
    b = system.b_effective
    n = x.size
    m = A.shape[0]
    if not n:
        return x.copy(), {
            "method": "no_free_points",
            "iterations": 0,
            "converged": True,
            **_certify(x, variance, A, b, x, np.zeros(m)),
        }

    y = _feasible_start(A, b, x) if m else np.clip(x, LOWER, UPPER)
    if y is None:
        # 起点失败通常意味着可行域退化；交由上层作为校验失败处理。
        y = np.clip(x, LOWER, UPPER)
    if not m:
        diagnostics = _certify(x, variance, A, b, y, np.zeros(0))
        diagnostics.update({"method": "bound_projection", "iterations": 0, "converged": True})
        return y, diagnostics

    tol = 1e-12
    free = (y > LOWER + tol) & (y < UPPER - tol)
    fixed_y = np.clip(y, LOWER, UPPER)
    lam = np.zeros(m, dtype=np.float64)
    iterations = 0
    converged = False
    for iterations in range(1, max_iterations + 1):
        candidate, lam = _solve_equality_on_free(x, variance, A, b, free, fixed_y)
        if candidate is None:
            break
        # 从当前可行点沿 (candidate - y) 走，遇到边界即截断。
        direction = candidate - y
        limits = np.ones(n, dtype=np.float64)
        index = np.where(free)[0]
        for position in index:
            if direction[position] < -tol:
                limits[position] = max(0.0, (LOWER - y[position]) / direction[position])
            elif direction[position] > tol:
                limits[position] = max(0.0, (UPPER - y[position]) / direction[position])
        step = float(limits.min(initial=1.0)) if index.size else 1.0
        if np.isfinite(step) and step < 1.0:
            y = y + max(step, 0.0) * direction
            hit = index[limits[index] <= step + 1e-9]
        else:
            y = candidate
            hit = np.array([], dtype=int)
        y = np.clip(y, LOWER, UPPER)
        if hit.size:
            for position in hit:
                y[position] = LOWER if direction[position] < 0 else UPPER
                free[position] = False
                fixed_y[position] = y[position]
            continue
        # 内点解已就位：复核固定点的乘子符号，释放违反者。
        gradient = (y - x) / variance + A.T @ lam
        at_lower = (~free) & (y <= LOWER + tol) & (gradient < -1e-11)
        at_upper = (~free) & (y >= UPPER - tol) & (gradient > 1e-11)
        release = at_lower | at_upper
        if not release.any():
            converged = True
            break
        # 一次只释放违反最严重的点，避免循环。
        violations = np.where(release, np.abs(gradient), -1.0)
        chosen = int(np.argmax(violations))
        y[chosen] = np.clip(candidate[chosen], LOWER, UPPER)
        fixed_y[chosen] = y[chosen]
        free[chosen] = True
    diagnostics = _certify(x, variance, A, b, np.clip(y, LOWER, UPPER), lam)
    diagnostics.update(
        {"method": "primal_active_set", "iterations": int(iterations), "converged": bool(converged)}
    )
    if not diagnostics["optimal"]:
        polished, extra = _primal_polish(system, y)
        extra_cert = _certify(x, variance, A, b, polished, lam)
        if extra_cert["optimal"]:
            polished, diagnostics = polished, {
                **extra_cert,
                "method": "primal_active_set+polish",
                "iterations": int(iterations),
                "converged": True,
            }
    return np.clip(y, LOWER, UPPER), diagnostics


def _certify(x, variance, A, b, y, lam):
    """检查原可行性与对偶间隙；两者都满足才判定为全局最优。"""
    equality = float(np.max(np.abs(A @ y - b), initial=0.0)) if A.shape[0] else 0.0
    bound = float(np.max(np.maximum(0.0, np.maximum(LOWER - y, y - UPPER)), initial=0.0)) if y.size else 0.0
    # 目标函数对用户按 sum(change^2/v) 报告；对偶证书用它的 0.5 倍，对应标准QP形式。
    total = float(np.sum((y - x) ** 2 / variance)) if y.size else 0.0
    primal = 0.5 * total
    dual = dual_lower_bound(x, variance, A, b, lam) if A.shape[0] and y.size else primal
    gap = primal - dual
    scale = max(1.0, primal)
    return {
        "equality_max_abs": equality,
        "bound_violation": bound,
        "objective": total,
        "dual_objective": float(dual),
        "optimality_gap": float(gap),
        "optimality_gap_relative": float(abs(gap) / scale),
        "primal_feasible": bool(equality <= 1e-9 and bound <= 1e-12),
        "optimal": bool(equality <= 1e-9 and bound <= 1e-12 and gap <= 1e-9 * scale),
    }


def _primal_polish(system, candidate):
    """用候选激活集精确重解等式子系统并复核KKT，作为稳健兜底。"""
    x = system.x[system.free]
    variance = system.variance[system.free]
    A = system.A
    b = system.b_effective
    m = A.shape[0]
    y = np.clip(np.asarray(candidate, dtype=np.float64), LOWER, UPPER)
    if not m or not y.size:
        return y, {"method": "primal_active_set", "iterations": 0, **_certify(x, variance, A, b, y, np.zeros(m))}
    lam = np.zeros(m, dtype=np.float64)
    for attempt in range(20):
        interior = (y > LOWER) & (y < UPPER)
        fixed = ~interior
        if fixed.any():
            y[fixed] = np.where(y[fixed] <= LOWER, LOWER, UPPER)
        if not interior.any():
            break
        A_int = A[:, interior]
        try:
            lam = np.linalg.lstsq((A_int * variance[interior][None, :]) @ A_int.T, A_int @ x[interior] + (A[:, fixed] @ y[fixed] if fixed.any() else 0.0) - b, rcond=1e-14)[0]
        except np.linalg.LinAlgError:
            break
        proposed = x[interior] - variance[interior] * (A_int.T @ lam)
        if not np.isfinite(proposed).all():
            break
        y[interior] = np.clip(proposed, LOWER, UPPER)
        if not ((proposed < LOWER - 1e-12).any() or (proposed > UPPER + 1e-12).any()):
            break
    result = _certify(x, variance, A, b, y, lam)
    result.update({"method": "primal_active_set", "iterations": attempt + 1, "converged": bool(result["optimal"])})
    return y, result


def validate_calibration(system, zones, y_free, diagnostics):
    """全部校验通过才允许原子替换；返回问题列表。"""
    issues = []
    if not diagnostics.get("optimal"):
        issues.append("二次规划未达到可验证的最优解")
    if not np.isfinite(y_free).all():
        issues.append("校正值存在非有限数")
    if y_free.size and float(np.max(np.abs(y_free), initial=0.0)) > 1e9:
        issues.append("校正值量级异常")
    if y_free.size:
        bound = float(np.max(np.maximum(0.0, np.maximum(LOWER - y_free, y_free - UPPER)), initial=0.0))
        if bound > 1e-9:
            issues.append(f"校正值越出0–100%边界（最大越界{bound:.3e}）")
    y_full = system.x.copy()
    y_full[system.free] = y_free
    y_full[system.locked] = system.x[system.locked]
    residual = float(np.max(np.abs(system.A_full @ y_full - system.b), initial=0.0)) if system.A_full.shape[0] else 0.0
    if residual > CONSTRAINT_TOLERANCE:
        issues.append(f"分区加权均值未闭合（最大残差{residual:.3e}）")
    if system.locked.any() and not np.array_equal(y_full[system.locked], system.x[system.locked]):
        issues.append("零方差锁定点被改动")
    if not np.isfinite(system.A_full @ y_full).all():
        issues.append("加权均值计算出现非有限值")
    variance = system.variance[system.free]
    if y_free.size and variance.size:
        objective = float(np.sum((y_free - system.x[system.free]) ** 2 / variance))
        if not math.isfinite(objective) or objective < -1e-12:
            issues.append("目标函数值非有限或为负")
    return issues


def calibrate_result(result, zones, system=None):
    """纯计算：返回 (calibration, diagnostics)。不改动输入的 result。"""
    predictions = result.get("kriging", {}).get("predictions") or []
    if system is None:
        system = build_system(zones, predictions)
    diagnostics_all = {
        "zone_constraints": len(zones),
        "free_points": int(system.free.sum()),
        "locked_points": int(system.locked.sum()),
        "constraint_rank": int(np.linalg.matrix_rank(system.A, tol=1e-10)) if system.A.size else 0,
        "redundant_constraints": bool(
            system.A.shape[0] > 1
            and np.linalg.matrix_rank(system.A, tol=1e-10) < system.A.shape[0]
        ),
    }
    if not lp_feasible(system.A, system.b_effective):
        conflict, rows = find_conflicting_zones(system, zones)
        detail = "、".join(conflict) if conflict else "全部"
        raise CalibrationConflict(
            f"分区均值约束相互矛盾，无法同时满足（冲突分区：{detail}）。"
            "请核对重叠分区的实测均值、面积权重与零方差锁定点。",
            conflict_zones=conflict,
            zone_diagnostics=conflict_diagnostics(system, zones, rows),
        )
    y_free, solver = solve_min_change(system)
    issues = validate_calibration(system, zones, y_free, solver)
    if issues:
        raise CalibrationValidationError("；".join(issues))
    y_full = system.x.copy()
    y_full[system.free] = y_free
    y_full[system.locked] = system.x[system.locked]
    objective = 0.0
    if system.free.any():
        objective = float(np.sum((y_full[system.free] - system.x[system.free]) ** 2 / system.variance[system.free]))
    zone_output = []
    for zone in zones:
        weights = zone["weights"]
        total = zone["area_weight_sum"]
        before = sum(weights[q] * system.x[system.query_ids.index(q)] for q in weights) / total
        after = sum(weights[q] * y_full[system.query_ids.index(q)] for q in weights) / total
        zone_output.append(
            {
                "zone_id": zone["zone_id"],
                "measured_mean": float(zone["measured_mean"]),
                "area_weight_sum": float(total),
                "point_count": len(weights),
                "locked_point_count": sum(
                    int(system.locked[system.query_ids.index(q)]) for q in weights
                ),
                "before_mean": float(before),
                "after_mean": float(after),
                "delta_before": float(before - zone["measured_mean"]),
                "delta_after": float(after - zone["measured_mean"]),
                "satisfied": bool(abs(after - zone["measured_mean"]) <= CONSTRAINT_TOLERANCE),
            }
        )
    point_zones = {query_id: [] for query_id in system.query_ids}
    for zone in zones:
        for query_id in zone["weights"]:
            point_zones[query_id].append(zone["zone_id"])
    points = []
    for i, query_id in enumerate(system.query_ids):
        points.append(
            {
                "query_id": query_id,
                "before": float(system.x[i]),
                "after": float(y_full[i]),
                "change": float(y_full[i] - system.x[i]),
                "variance": float(system.variance[i]),
                "locked": bool(system.locked[i]),
                "out_of_range_preserved": bool(not LOWER <= y_full[i] <= UPPER),
                "zones": point_zones[query_id],
            }
        )
    warnings = []
    if diagnostics_all["redundant_constraints"]:
        warnings.append("分区约束存在线性相关（冗余），已合并为同一可行域求解，对账结果不受影响。")
    if system.locked.any():
        warnings.append(f"{int(system.locked.sum())}个零方差点锁定原预测值，未参与调整。")
        outside = [
            system.query_ids[i]
            for i in np.where(system.locked)[0]
            if not LOWER <= system.x[i] <= UPPER
        ]
        if outside:
            warnings.append(
                "锁定的零方差点原推断已超出0–100%（"
                + "、".join(outside[:6])
                + ("等" if len(outside) > 6 else "")
                + "），按锁定原值保留，未在校正中截断。"
            )
    locked_only = [
        zone["zone_id"]
        for zone in zones
        if all(system.locked[system.query_ids.index(q)] for q in zone["weights"])
    ]
    if locked_only:
        warnings.append("以下分区的待估点全部为零方差锁定点，仅校验均值：" + "、".join(locked_only))
    if any(not zone["satisfied"] for zone in zone_output):
        warnings.append("部分分区校正后均值残差超出常规容差。")
    calibration = {
        "state": "applied",
        "version": None,  # 由运行服务分配，保证版本单调递增
        "zones": zone_output,
        "points": points,
        "objective": float(objective),
        "objective_definition": "sum((after-before)^2 / original_variance_pp2)，仅计入方差大于0的自由点",
        "constraints": diagnostics_all,
        "solver": solver,
        "residual_tolerance": CONSTRAINT_TOLERANCE,
        "warnings": warnings,
        "max_zone_residual": float(
            max((abs(zone["delta_after"]) for zone in zone_output), default=0.0)
        ),
        "max_point_change": float(
            max((abs(point["change"]) for point in points), default=0.0)
        ),
    }
    return calibration, system


def canonical_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
