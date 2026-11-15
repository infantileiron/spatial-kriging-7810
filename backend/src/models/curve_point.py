from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class CurvePoint(RecordMixin,Base):
 __tablename__="curve_points"
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"))
 distance:Mapped[float]=mapped_column(Double)
 semivariance:Mapped[float]=mapped_column(Double)
