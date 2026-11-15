from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.study import KrigingStudy
from ..models.dataset import SpatialDataset
from ..models.spec import VariogramSpec
from ..models.query_point import QueryPoint
from ..models.common import serialize
from .point_data import parse_points

def expand(db,row):
 queries=db.scalars(select(QueryPoint).where(QueryPoint.study_id==row.id).order_by(QueryPoint.query_id)).all()
 return {**serialize(row),"queries":[{"query_id":p.query_id,"x":p.x,"y":p.y} for p in queries]}

def create(db,body):
 data=db.get(SpatialDataset,body.dataset_id)
 if not data or not db.get(VariogramSpec,body.spec_id):raise HTTPException(422,"采样批次或变异函数口径不存在")
 if data.coordinate_system!=body.query_coordinate_system:raise HTTPException(422,"采样和待估坐标系统不一致")
 if db.scalar(select(KrigingStudy).where(KrigingStudy.name==body.name)):raise HTTPException(409,"空间推断研究名称已存在")
 try:queries=parse_points(body.queries_csv,query=True)
 except ValueError as e:raise HTTPException(422,str(e))
 row=KrigingStudy(id=str(uuid4()),name=body.name,dataset_id=body.dataset_id,spec_id=body.spec_id,query_coordinate_system=body.query_coordinate_system);db.add(row);db.flush()
 for point in queries:db.add(QueryPoint(id=str(uuid4()),study_id=row.id,**point))
 db.commit();return row
