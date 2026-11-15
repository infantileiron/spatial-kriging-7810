from pydantic import BaseModel,Field,model_validator


class CalibrationCreate(BaseModel):
    zones_csv:str=Field(min_length=10,max_length=300000)
    means_csv:str=Field(default="",max_length=300000)
    note:str=Field(default="",max_length=2000)

    @model_validator(mode="after")
    def inputs(self):
        if not self.zones_csv.strip():raise ValueError("分区权重CSV不能为空")
        return self
