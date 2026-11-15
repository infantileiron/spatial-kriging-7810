from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.spec import VariogramSpec

def create(db,body):
 if db.scalar(select(VariogramSpec).where(VariogramSpec.name==body.name)):raise HTTPException(409,"变异函数口径名称已存在")
 row=VariogramSpec(id=str(uuid4()),**body.model_dump());db.add(row);db.commit();return row
