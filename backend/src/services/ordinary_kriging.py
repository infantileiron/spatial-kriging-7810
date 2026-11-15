import math
import numpy as np


def covariance(h,sill,range_,nugget=0.):
    if not all(math.isfinite(v) for v in [sill,range_,nugget]) or sill<=0 or range_<=0 or nugget<0:
        raise ValueError('sill/range须为正且nugget非负，参数须有限')
    distance=np.asarray(h,dtype=np.float64)
    if not np.isfinite(distance).all() or (distance<0).any():raise ValueError('距离无效')
    return sill*np.exp(-distance/range_)+np.where(distance==0,nugget,0.)


def ordinary_kriging(points,queries,sill,range_,nugget=0.,condition_limit=1e10,negative_tolerance=1e-10):
    if len(points)<2 or not queries:raise ValueError('至少2个采样点和1个待估点')
    if not math.isfinite(condition_limit) or condition_limit<=1 or not math.isfinite(negative_tolerance) or negative_tolerance<=0 or negative_tolerance>1e-8:
        raise ValueError('条件数阈值或微负方差容差无效')
    coords=np.asarray([[p['x'],p['y']] for p in points],dtype=np.float64)
    values=np.asarray([p['value'] for p in points],dtype=np.float64)
    query_coords=np.asarray([[p['x'],p['y']] for p in queries],dtype=np.float64)
    if not np.isfinite(coords).all() or not np.isfinite(values).all() or not np.isfinite(query_coords).all():raise ValueError('坐标/读数须有限')
    if len(np.unique(coords,axis=0))!=len(coords):raise ValueError('重复采样点导致系统不可识别')
    if len(np.unique(query_coords,axis=0))!=len(query_coords):raise ValueError('待估坐标重复')
    distances=np.linalg.norm(coords[:,None,:]-coords[None,:,:],axis=2)
    C=covariance(distances,sill,range_,nugget)
    A=np.block([[C,np.ones((len(points),1))],[np.ones((1,len(points))),np.zeros((1,1))]])
    condition=float(np.linalg.cond(A))
    if not math.isfinite(condition) or condition>condition_limit:raise ValueError('克里金增广系统奇异或病态，条件数超限')
    cross_distance=np.linalg.norm(coords[:,None,:]-query_coords[None,:,:],axis=2)
    c=covariance(cross_distance,sill,range_,nugget)
    try:solution=np.linalg.solve(A,np.vstack([c,np.ones((1,len(queries)))]))
    except np.linalg.LinAlgError:raise ValueError('克里金增广系统奇异')
    weights=solution[:-1,:];mu=solution[-1,:]
    if not np.isfinite(solution).all() or np.max(np.abs(weights.sum(axis=0)-1))>1e-8:raise ValueError('权重未通过有限性/和为1校验')
    predicted=values@weights
    if not np.isfinite(predicted).all():raise ValueError("预测值非有限")
    C0=sill+nugget
    raw=C0-np.sum(c*weights,axis=0)-mu
    cutoff=negative_tolerance*max(1.,C0)
    if not np.isfinite(raw).all() or np.min(raw)<-cutoff:raise ValueError('预测方差严重为负或非有限，拒绝输出')
    predictions=[]
    for j,query in enumerate(queries):
        variance=max(0.,float(raw[j]))
        predictions.append({'query_id':query['query_id'],'x':float(query['x']),'y':float(query['y']),'prediction':float(predicted[j]),'variance':variance,'raw_variance':float(raw[j]),'standard_deviation':math.sqrt(variance),'variance_clipped':bool(raw[j]<0),'mu':float(mu[j]),'weights':[{'point_id':p['point_id'],'weight':float(weights[i,j])} for i,p in enumerate(points)],'weight_sum':float(weights[:,j].sum())})
    return {'predictions':predictions,'condition_number':condition,'condition_limit':condition_limit,'negative_variance_cutoff':cutoff,'C0':float(C0),'model_variance_note':'给定协方差模型下的空间随机场方差，不是真实预测误差或交叉验证误差。'}
