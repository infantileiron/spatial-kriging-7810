from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class Prediction(RecordMixin,Base):
 __tablename__="predictions"
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"))
 query_id:Mapped[str]=mapped_column(String(80,collation="utf8mb4_bin"))
 x:Mapped[float]=mapped_column(Double)
 y:Mapped[float]=mapped_column(Double)
 prediction:Mapped[float]=mapped_column(Double)
 variance:Mapped[float]=mapped_column(Double)
 raw_variance:Mapped[float]=mapped_column(Double)
 standard_deviation:Mapped[float]=mapped_column(Double)
 mu:Mapped[float]=mapped_column(Double)
 weight_sum:Mapped[float]=mapped_column(Double)
 variance_clipped:Mapped[bool]
