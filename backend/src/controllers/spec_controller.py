from ..services import spec_service
from ..models.spec import VariogramSpec
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,VariogramSpec)
def detail(db,ident):return serialize(require(db,VariogramSpec,ident))
def create(db,body):return serialize(spec_service.create(db,body))
