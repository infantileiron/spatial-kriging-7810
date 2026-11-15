from sqlalchemy import String,Text,JSON,ForeignKey,Integer,UniqueConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class Calibration(RecordMixin,Base):
 __tablename__="calibrations"
 __table_args__=(UniqueConstraint("run_id","version",name="uq_calibration_run_version"),Index("ix_calibration_run_state","run_id","state"))
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"),nullable=False)
 version:Mapped[int]=mapped_column(Integer,nullable=False)
 state:Mapped[str]=mapped_column(String(20),default="applied",nullable=False)
 payload:Mapped[dict]=mapped_column(JSON,default=dict)
 error:Mapped[str]=mapped_column(Text,default="")
 conflict_zones:Mapped[list]=mapped_column(JSON,default=list)
 input_sha256:Mapped[str]=mapped_column(String(64),default="")
 actor:Mapped[str]=mapped_column(String(160),default="")
