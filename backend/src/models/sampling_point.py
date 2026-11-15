from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class SamplingPoint(RecordMixin,Base):
 __tablename__="sampling_points"
 dataset_id:Mapped[str]=mapped_column(ForeignKey("datasets.id"))
 point_id:Mapped[str]=mapped_column(String(80,collation="utf8mb4_bin"))
 x:Mapped[float]=mapped_column(Double)
 y:Mapped[float]=mapped_column(Double)
 value:Mapped[float]=mapped_column(Double)
