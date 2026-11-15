from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class KrigingWeight(RecordMixin,Base):
 __tablename__="kriging_weights"
 prediction_id:Mapped[str]=mapped_column(ForeignKey("predictions.id"))
 point_id:Mapped[str]=mapped_column(String(80,collation="utf8mb4_bin"))
 weight:Mapped[float]=mapped_column(Double)
