from sqlalchemy import select
from ..services import dataset_service
from ..models.dataset import SpatialDataset
from .common import require
def list_all(db):return [dataset_service.expand(db,r) for r in db.scalars(select(SpatialDataset).order_by(SpatialDataset.created_at.desc()).limit(200))]
def detail(db,ident):return dataset_service.expand(db,require(db,SpatialDataset,ident))
def create(db,body):return dataset_service.expand(db,dataset_service.create(db,body))
