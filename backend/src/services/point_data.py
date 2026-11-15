import csv,io,math

def parse_points(text,query=False):
 key="query_id" if query else "point_id";required={key,"x","y"} if query else {key,"x","y","value"}
 rows=list(csv.DictReader(io.StringIO(text)));limit=100 if query else 128
 if not (1 if query else 2)<=len(rows)<=limit or not rows or not required.issubset(rows[0]):raise ValueError("CSV列不完整或点数超限（采样2–128，待估1–100）")
 result=[];ids=set();coords=set()
 for row in rows:
  ident=(row.get(key) or "").strip()
  if not ident or len(ident)>80 or ident in ids:raise ValueError("点ID为空、过长或重复")
  values={}
  for field in ["x","y"]+([] if query else ["value"]):
   try:value=float(row.get(field))
   except Exception:raise ValueError("坐标/含水读数须为数值")
   if not math.isfinite(value):raise ValueError("坐标/含水读数须有限")
   if field in ["x","y"] and abs(value)>10000:raise ValueError("局部平面坐标绝对值须≤10000米")
   if field=="value" and not 0<=value<=100:raise ValueError("含水率输入须在0–100%")
   values[field]=value
  coordinate=(values["x"],values["y"])
  if coordinate in coords:raise ValueError("重复坐标拒绝，不自动平均或抖动")
  ids.add(ident);coords.add(coordinate);result.append({key:ident,**values})
 return result
