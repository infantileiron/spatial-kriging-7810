import json
import numpy as np
from sqlalchemy import select,func
from src.config.database import initialize,Session
from src.models import SpatialDataset,SamplingPoint,VariogramSpec,KrigingStudy,QueryPoint,KrigingRun,FieldReview,Report,User
from src.utils.security import hash_password
from src.services.run_service import compute

def make_points():
 coordinates=np.array([(float(x),float(y)) for x in [0,12,24,36,58,90,125,150] for y in [0,15,30,45,70,95,120,150]],dtype=np.float64)
 distance=np.linalg.norm(coordinates[:,None,:]-coordinates[None,:,:],axis=2);C=8*np.exp(-distance/55)+.2*np.eye(64)
 values=28+np.random.default_rng(20261112).multivariate_normal(np.zeros(64),C)
 return [{"point_id":f"NZ-S{i+1:02}","x":float(c[0]),"y":float(c[1]),"value":float(values[i])} for i,c in enumerate(coordinates)]
def make_queries():return [{"query_id":f"NZ-Q{i+1:02}","x":float(x),"y":float(y)} for i,(x,y) in enumerate((x,y) for x in [10,45,80,115,160] for y in [10,45,80,115,160])]

def seed():
 initialize()
 with Session() as db:
  for role in ["admin","analyst","viewer"]:
   email=role+"@spatial.demo"
   if not db.scalar(select(User).where(User.email==email)):db.add(User(id="user-"+role,email=email,role=role,password_hash=hash_password("SoilDemo2026!")))
  if not db.get(SpatialDataset,"demo-dataset"):db.add(SpatialDataset(id="demo-dataset",name="宁泽北试验地块含水采样",coordinate_system="local_meters",description="64个局部米制采样点；文件ningze_moisture_202611.csv；含稀疏与边缘区域"))
  db.commit()
  for p in make_points():
   ident="sample-"+p["point_id"]
   if not db.get(SamplingPoint,ident):db.add(SamplingPoint(id=ident,dataset_id="demo-dataset",**p))
  if not db.get(VariogramSpec,"demo-spec"):db.add(VariogramSpec(id="demo-spec",name="指数半变异 · 计数加权拟合",mode="fit",n_bins=8,min_pairs=5,max_distance=200.,nugget=.2,fixed_sill=8.,fixed_range=55.,sill_min=.1,sill_max=50.,range_min=5.,range_max=300.,condition_limit=1e10,negative_tolerance=1e-10))
  db.commit()
  if not db.get(KrigingStudy,"demo-study"):db.add(KrigingStudy(id="demo-study",name="北地块25点空间推断",dataset_id="demo-dataset",spec_id="demo-spec",query_coordinate_system="local_meters"))
  db.commit()
  for q in make_queries():
   ident="query-"+q["query_id"]
   if not db.get(QueryPoint,ident):db.add(QueryPoint(id=ident,study_id="demo-study",**q))
  db.commit()
  if not db.get(KrigingRun,"demo-run"):db.add(KrigingRun(id="demo-run",study_id="demo-study",status="queued",result={},error=""));db.commit();compute(db,"demo-run")
  if not db.get(FieldReview,"demo-review"):db.add(FieldReview(id="demo-review",run_id="demo-run",action="核对稀疏区与边缘查询的空间方差及变异函数边界；参数和预测锁定，空间随机场方差不当作真实误差。",state="approved",reviewer="admin@spatial.demo"))
  db.commit()
  if not db.get(Report,"demo-report"):db.add(Report(id="demo-report",review_id="demo-review",title="宁泽地块含水空间推断底稿",snapshot={"result":db.get(KrigingRun,"demo-run").result,"action":db.get(FieldReview,"demo-review").action,"reviewer":"admin@spatial.demo"}))
  db.commit()
  return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in [User,SpatialDataset,SamplingPoint,VariogramSpec,KrigingStudy,QueryPoint,KrigingRun,FieldReview,Report]}
if __name__=="__main__":print(json.dumps(seed(),ensure_ascii=False))
