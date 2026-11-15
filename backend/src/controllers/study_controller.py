from sqlalchemy import select
from ..services import study_service
from ..models.study import KrigingStudy
from .common import require
def list_all(db):return [study_service.expand(db,r) for r in db.scalars(select(KrigingStudy).order_by(KrigingStudy.created_at.desc()).limit(200))]
def detail(db,ident):return study_service.expand(db,require(db,KrigingStudy,ident))
def create(db,body):return study_service.expand(db,study_service.create(db,body))
