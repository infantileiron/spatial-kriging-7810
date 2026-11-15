from typing import Literal
from pydantic import BaseModel,Field
class DatasetCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 coordinate_system:Literal["local_meters"]="local_meters"
 csv_text:str=Field(min_length=20,max_length=500000)
 description:str=Field(default="",max_length=2000)
class DatasetEdit(BaseModel):
 description:str=Field(max_length=2000)
