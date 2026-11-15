from ..services import run_service,calibration_service
from ..models.run import KrigingRun
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,KrigingRun)
def detail(db,ident):
 run=require(db,KrigingRun,ident)
 data=serialize(run)
 applied=calibration_service.current_applied(db,run.id)
 if applied is not None and isinstance(data.get("result"),dict):
  points,applied_row=calibration_service.effective_points(db,run.id,data["result"])
  data["result"]={**data["result"],"kriging":{**data["result"].get("kriging",{}),"predictions":points,"calibrated":True}}
  data["calibration"]={"version":applied_row.version,"payload":applied_row.payload}
 data["calibration_versions"]=calibration_service.history(db,run.id)
 return data
def create(db,body):return serialize(run_service.create(db,body))
