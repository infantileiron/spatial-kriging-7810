import csv,io
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.review import FieldReview
from ..models.run import KrigingRun
from ..models.report import Report

def create(db,body):
 review=db.get(FieldReview,body.review_id)
 if review is None or review.state!="approved":raise HTTPException(409,"报告须关联已批准的空间推断复核")
 existing=db.scalar(select(Report).where(Report.review_id==body.review_id))
 if existing:return existing
 run=db.get(KrigingRun,review.run_id);row=Report(id=str(uuid4()),review_id=review.id,title=body.title,snapshot={"result":run.result,"action":review.action,"reviewer":review.reviewer});db.add(row);db.commit();return row

def export(row):
 result=row.snapshot["result"];model=result["model"];out=io.StringIO();writer=csv.writer(out);writer.writerow(["query_id","x_m","y_m","prediction_percent","field_variance_pp2","field_sd_pp","raw_variance","micro_negative_clipped","weight_sum","mu","sill","range_m","nugget","condition_number","input_sha256"])
 for p in result["kriging"]["predictions"]:writer.writerow([p["query_id"],p["x"],p["y"],p["prediction"],p["variance"],p["standard_deviation"],p["raw_variance"],p["variance_clipped"],p["weight_sum"],p["mu"],model["sill"],model["range"],model["nugget"],result["kriging"]["condition_number"],result["input_sha256"]])
 return "\ufeff"+out.getvalue()
