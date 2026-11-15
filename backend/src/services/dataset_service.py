from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.dataset import SpatialDataset
from ..models.sampling_point import SamplingPoint
from ..models.common import serialize
from .point_data import parse_points

def expand(db,row):
 points=db.scalars(select(SamplingPoint).where(SamplingPoint.dataset_id==row.id).order_by(SamplingPoint.point_id)).all()
 return {**serialize(row),"points":[{"point_id":p.point_id,"x":p.x,"y":p.y,"value":p.value} for p in points]}

def create(db,body):
 if db.scalar(select(SpatialDataset).where(SpatialDataset.name==body.name)):raise HTTPException(409,"空间采样批次名称已存在")
 try:points=parse_points(body.csv_text)
 except ValueError as e:raise HTTPException(422,str(e))
 row=SpatialDataset(id=str(uuid4()),name=body.name,coordinate_system=body.coordinate_system,description=body.description);db.add(row);db.flush()
 for point in points:db.add(SamplingPoint(id=str(uuid4()),dataset_id=row.id,**point))
 db.commit();return row
