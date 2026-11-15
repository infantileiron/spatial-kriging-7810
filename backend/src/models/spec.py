from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class VariogramSpec(RecordMixin,Base):
 __tablename__="specs"
 name:Mapped[str]=mapped_column(String(180),unique=True)
 mode:Mapped[str]=mapped_column(String(12))
 n_bins:Mapped[int]
 min_pairs:Mapped[int]
 max_distance:Mapped[float]=mapped_column(Double)
 nugget:Mapped[float]=mapped_column(Double)
 fixed_sill:Mapped[float]=mapped_column(Double)
 fixed_range:Mapped[float]=mapped_column(Double)
 sill_min:Mapped[float]=mapped_column(Double)
 sill_max:Mapped[float]=mapped_column(Double)
 range_min:Mapped[float]=mapped_column(Double)
 range_max:Mapped[float]=mapped_column(Double)
 condition_limit:Mapped[float]=mapped_column(Double)
 negative_tolerance:Mapped[float]=mapped_column(Double)
