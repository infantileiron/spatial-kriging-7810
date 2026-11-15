from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class QueryPoint(RecordMixin,Base):
 __tablename__="query_points"
 study_id:Mapped[str]=mapped_column(ForeignKey("studies.id"))
 query_id:Mapped[str]=mapped_column(String(80,collation="utf8mb4_bin"))
 x:Mapped[float]=mapped_column(Double)
 y:Mapped[float]=mapped_column(Double)
