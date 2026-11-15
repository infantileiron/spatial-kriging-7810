import json,hashlib
from uuid import uuid4
import numpy as np
from sqlalchemy import select
from fastapi import HTTPException
from ..models.run import KrigingRun
from ..models.study import KrigingStudy
from ..models.dataset import SpatialDataset
from ..models.spec import VariogramSpec
from ..models.sampling_point import SamplingPoint
from ..models.query_point import QueryPoint
from ..models.prediction import Prediction
from ..models.kriging_weight import KrigingWeight
from ..models.variogram_bin import VariogramBin
from ..models.curve_point import CurvePoint
from ..utils.queue import enqueue
from .variogram import empirical_variogram,fit_exponential,semivariance
from .ordinary_kriging import ordinary_kriging
SPEC_FIELDS=["mode","n_bins","min_pairs","max_distance","nugget","fixed_sill","fixed_range","sill_min","sill_max","range_min","range_max","condition_limit","negative_tolerance"]

def create(db,body):
 if not db.get(KrigingStudy,body.study_id):raise HTTPException(422,"空间推断研究不存在")
 row=KrigingRun(id=str(uuid4()),study_id=body.study_id,status="queued",result={},error="");db.add(row);db.commit()
 try:enqueue(row.id)
 except Exception:
  row.status="failed";row.error="Redis队列不可用，请稍后重试";db.commit();raise HTTPException(503,row.error)
 return row

def compute(db,run_id):
 row=db.get(KrigingRun,run_id)
 if row is None or row.status not in ["queued","running"]:return
 row.status="running";db.commit()
 try:
  study=db.get(KrigingStudy,row.study_id);dataset=db.get(SpatialDataset,study.dataset_id);spec=db.get(VariogramSpec,study.spec_id)
  samples=db.scalars(select(SamplingPoint).where(SamplingPoint.dataset_id==dataset.id).order_by(SamplingPoint.point_id)).all();query_rows=db.scalars(select(QueryPoint).where(QueryPoint.study_id==study.id).order_by(QueryPoint.query_id)).all()
  points=[{"point_id":p.point_id,"x":p.x,"y":p.y,"value":p.value} for p in samples];queries=[{"query_id":p.query_id,"x":p.x,"y":p.y} for p in query_rows]
  config={k:getattr(spec,k) for k in SPEC_FIELDS}
  empirical=empirical_variogram(points,spec.n_bins,spec.max_distance,spec.min_pairs)
  model=fit_exponential(empirical,spec.nugget,(spec.sill_min,spec.sill_max),(spec.range_min,spec.range_max)) if spec.mode=="fit" else {"mode":"fixed","sill":spec.fixed_sill,"range":spec.fixed_range,"nugget":spec.nugget,"weighted_sse":None,"at_boundary":False,"warnings":[],"active_bins":sum(b["used"] for b in empirical["bins"])}
  distances=np.concatenate(([0.],np.linspace(spec.max_distance*1e-6,spec.max_distance,100,dtype=np.float64)))
  model["curve"]=[{"distance":float(h),"semivariance":float(g)} for h,g in zip(distances,semivariance(distances,model["sill"],model["range"],model["nugget"]))]
  kriging=ordinary_kriging(points,queries,model["sill"],model["range"],model["nugget"],spec.condition_limit,spec.negative_tolerance)
  warnings=list(model["warnings"])
  if any(p["prediction"]<0 or p["prediction"]>100 for p in kriging["predictions"]):warnings.append("部分线性预测超出0–100%，未截断，需现场与模型复核")
  fingerprint=hashlib.sha256(json.dumps({"points":points,"queries":queries,"config":config},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  row.result={"dataset_name":dataset.name,"spec_name":spec.name,"study_name":study.name,"coordinate_system":"local_meters","value_unit":"%","variance_unit":"percentage_points_squared","points":points,"queries":queries,"empirical":empirical,"model":model,"kriging":kriging,"config":config,"warnings":warnings,"input_sha256":fingerprint,"validation_note":"未输出LOO或真实误差；模型参数与预测结果在本次运行中锁定。"}
  row.model_sill=model["sill"];row.model_range=model["range"];row.model_nugget=model["nugget"];row.system_condition=kriging["condition_number"]
  for b in empirical["bins"]:db.add(VariogramBin(id=str(uuid4()),run_id=row.id,bin_index=b["index"],lower=b["lower"],upper=b["upper"],distance=b["distance"],semivariance=b["semivariance"],count=b["count"],used=b["used"]))
  for p in model["curve"]:db.add(CurvePoint(id=str(uuid4()),run_id=row.id,**p))
  for predicted in kriging["predictions"]:
   fields={k:predicted[k] for k in ["query_id","x","y","prediction","variance","raw_variance","standard_deviation","mu","weight_sum","variance_clipped"]}
   record=Prediction(id=str(uuid4()),run_id=row.id,**fields);db.add(record);db.flush()
   for weight in predicted["weights"]:db.add(KrigingWeight(id=str(uuid4()),prediction_id=record.id,**weight))
  row.status="completed";db.commit()
 except Exception as error:
  db.rollback();row=db.get(KrigingRun,run_id);row.status="failed";row.error=str(error)[:1000];db.commit()
