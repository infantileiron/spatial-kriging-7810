from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class VariogramBin(RecordMixin,Base):
 __tablename__="variogram_bins"
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"))
 bin_index:Mapped[int]
 lower:Mapped[float]=mapped_column(Double)
 upper:Mapped[float]=mapped_column(Double)
 distance:Mapped[float|None]=mapped_column(Double,nullable=True)
 semivariance:Mapped[float|None]=mapped_column(Double,nullable=True)
 count:Mapped[int]
 used:Mapped[bool]
