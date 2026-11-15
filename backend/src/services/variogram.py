import math
import numpy as np
from scipy.optimize import least_squares


def semivariance(h,sill,range_,nugget=0.):
    if not all(math.isfinite(v) for v in [sill,range_,nugget]) or sill<=0 or range_<=0 or nugget<0:
        raise ValueError('sill/range须为正且nugget非负，参数均须有限')
    distance=np.asarray(h,dtype=np.float64)
    if not np.isfinite(distance).all() or (distance<0).any():
        raise ValueError('距离须为非负有限米值')
    return np.where(distance==0,0.,nugget+sill*(-np.expm1(-distance/range_)))


def empirical_variogram(points,bins=8,max_distance=200.,min_pairs=3):
    if not isinstance(bins,int) or bins<2 or bins>30 or not math.isfinite(max_distance) or max_distance<=0 or min_pairs<1:
        raise ValueError('分箱参数无效')
    if len(points)<2:
        raise ValueError('至少需要两个采样点')
    coords=np.array([[p['x'],p['y']] for p in points],dtype=np.float64)
    values=np.array([p['value'] for p in points],dtype=np.float64)
    if not np.isfinite(coords).all() or not np.isfinite(values).all():
        raise ValueError('坐标与含水读数须有限')
    if len(np.unique(coords,axis=0))!=len(coords):
        raise ValueError('重复采样坐标不能计算半变异函数')
    i,j=np.triu_indices(len(points),k=1)
    distances=np.linalg.norm(coords[i]-coords[j],axis=1)
    gamma=.5*(values[i]-values[j])**2
    edges=np.linspace(0.,max_distance,bins+1,dtype=np.float64)
    records=[]
    for k in range(bins):
        mask=(distances>edges[k])&(distances<=edges[k+1])
        # Each positive-distance pair belongs to exactly one right-closed bin.
        count=int(mask.sum())
        records.append({'index':k,'lower':float(edges[k]),'upper':float(edges[k+1]),'distance':float(distances[mask].mean()) if count else None,'semivariance':float(gamma[mask].mean()) if count else None,'count':count,'used':count>=min_pairs})
    return {'bins':records,'pair_count':len(distances),'included_pairs':sum(r['count'] for r in records),'excluded_pairs':int((distances>max_distance).sum()),'max_distance':float(max_distance),'min_pairs':min_pairs}


def fit_exponential(empirical,nugget=0.,sill_bounds=(1e-6,1000.),range_bounds=(1.,1000.)):
    if not math.isfinite(nugget) or nugget<0:
        raise ValueError('固定nugget须非负且有限')
    bounds=np.asarray([sill_bounds,range_bounds],dtype=np.float64)
    if bounds.shape!=(2,2) or not np.isfinite(bounds).all() or (bounds[:,0]<=0).any() or (bounds[:,1]<=bounds[:,0]).any():
        raise ValueError('sill/range拟合界限须正且有序')
    active=[r for r in empirical['bins'] if r.get('used',True) and r['count']>0 and r['distance'] is not None]
    if len(active)<3:
        raise ValueError('至少3个满足计数门槛的距离箱才可拟合；可改用有依据的固定参数模式')
    h=np.array([r['distance'] for r in active],dtype=np.float64)
    g=np.array([r['semivariance'] for r in active],dtype=np.float64)
    counts=np.array([r['count'] for r in active],dtype=np.float64)
    if not np.isfinite(g).all() or np.max(g)<=0:
        raise ValueError('经验半方差全为零，正sill/range不可识别')
    lower=bounds[:,0];upper=bounds[:,1]
    initial=np.array([max(float(np.average(g,weights=counts))-nugget,lower[0]),float(np.average(h,weights=counts))],dtype=np.float64)
    initial=np.clip(initial,lower,upper)
    def residual(p):return np.sqrt(counts)*(semivariance(h,p[0],p[1],nugget)-g)
    fitted=least_squares(residual,initial,bounds=(lower,upper),x_scale='jac',max_nfev=2000)
    if not fitted.success or not np.isfinite(fitted.x).all():
        raise ValueError('指数变异函数拟合未收敛')
    touches=[name for k,name in enumerate(['sill','range']) if np.isclose(fitted.x[k],lower[k],rtol=1e-4,atol=1e-7) or np.isclose(fitted.x[k],upper[k],rtol=1e-4,atol=1e-7)]
    return {'mode':'fit','sill':float(fitted.x[0]),'range':float(fitted.x[1]),'nugget':float(nugget),'weighted_sse':float(np.dot(residual(fitted.x),residual(fitted.x))),'active_bins':len(active),'at_boundary':bool(touches),'warnings':['拟合参数接近或触及边界：'+', '.join(touches)] if touches else [],'weight_definition':'sum(bin_pair_count * squared residual)','sill_bounds':list(map(float,sill_bounds)),'range_bounds':list(map(float,range_bounds))}
