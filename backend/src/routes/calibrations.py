from fastapi import APIRouter,Depends,HTTPException
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.calibration import CalibrationCreate
from ..models.run import KrigingRun
from ..services import calibration,calibration_service
from ..controllers.common import require
router=APIRouter(prefix="/runs",tags=["calibrations"])


@router.get("/{ident}/calibrations")
def listing(ident:str,db=Depends(get_db),user=Depends(current)):
    require(db,KrigingRun,ident)
    return calibration_service.history(db,ident)


@router.post("/{ident}/calibrations",status_code=201)
def create(ident:str,body:CalibrationCreate,db=Depends(get_db),user=Depends(write_user)):
    run=require(db,KrigingRun,ident)
    if run.status!="completed":raise HTTPException(409,"仅已完成且含预测的运行可做分区校正")
    query_ids=[p["query_id"] for p in (run.result or {}).get("kriging",{}).get("predictions",[])]
    try:
        zones=calibration.prepare_zones(body.zones_csv,body.means_csv,query_ids)
    except calibration.CalibrationInputError as error:
        raise HTTPException(422,{"message":str(error),"reason":"input"})
    return calibration_service.create(db,run,zones,user.email,calibration.canonical_hash({"means_csv":body.means_csv,"note":body.note}))
