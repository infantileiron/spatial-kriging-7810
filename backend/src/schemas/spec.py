from pydantic import BaseModel,Field,model_validator
from ..constants.enums import ModelMode
class SpecCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 mode:ModelMode="fit"
 n_bins:int=Field(default=8,ge=3,le=20)
 min_pairs:int=Field(default=5,ge=1,le=100)
 max_distance:float=Field(default=200,gt=0,le=20000,allow_inf_nan=False)
 nugget:float=Field(default=.2,ge=0,le=1000,allow_inf_nan=False)
 fixed_sill:float=Field(default=8,gt=0,le=100000,allow_inf_nan=False)
 fixed_range:float=Field(default=55,gt=0,le=20000,allow_inf_nan=False)
 sill_min:float=Field(default=.1,gt=0,le=100000,allow_inf_nan=False)
 sill_max:float=Field(default=50,gt=0,le=100000,allow_inf_nan=False)
 range_min:float=Field(default=5,gt=0,le=20000,allow_inf_nan=False)
 range_max:float=Field(default=300,gt=0,le=20000,allow_inf_nan=False)
 condition_limit:float=Field(default=1e10,ge=1000,le=1e12,allow_inf_nan=False)
 negative_tolerance:float=Field(default=1e-10,gt=0,le=1e-8,allow_inf_nan=False)
 @model_validator(mode="after")
 def ordered(self):
  if self.sill_min>=self.sill_max or self.range_min>=self.range_max:raise ValueError("拟合界限须严格有序")
  return self
