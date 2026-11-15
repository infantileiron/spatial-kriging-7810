from typing import Literal
from pydantic import BaseModel,Field
class StudyCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 dataset_id:str
 spec_id:str
 query_coordinate_system:Literal["local_meters"]="local_meters"
 queries_csv:str=Field(min_length=10,max_length=200000)
