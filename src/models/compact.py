"""Positive-parameter lumped RC fitting helpers."""
import numpy as np
from scipy.optimize import least_squares

def rc_response(times_s,power_w,ambient_c,rth_k_per_w,cth_j_per_k,initial_c=None):
    t=np.asarray(times_s,float);p=np.asarray(power_w,float)
    if t.shape!=p.shape or len(t)<2 or t[0]!=0 or np.any(np.diff(t)<=0): raise ValueError('invalid time/power vectors')
    T=np.empty_like(t); T[0]=ambient_c if initial_c is None else initial_c
    tau=rth_k_per_w*cth_j_per_k
    for i in range(1,len(t)):
        dt=t[i]-t[i-1]; eq=ambient_c+rth_k_per_w*p[i-1]
        T[i]=eq+(T[i-1]-eq)*np.exp(-dt/tau)
    return T

def fit_positive_rc(times_s,power_w,temperature_c,ambient_c):
    """Fit only training response samples; return a reproducible residual summary."""
    t=np.asarray(times_s,float);p=np.asarray(power_w,float);y=np.asarray(temperature_c,float)
    if not (t.shape==p.shape==y.shape): raise ValueError('vectors must have same shape')
    scale=max(float(np.ptp(y)),1.0)
    def residual(logpars): return (rc_response(t,p,ambient_c,*np.exp(logpars))-y)/scale
    fit=least_squares(residual,np.log([1e5,1e-4]),bounds=(np.log([1.,1e-10]),np.log([1e9,1e3])),max_nfev=500)
    pred=rc_response(t,p,ambient_c,*np.exp(fit.x))
    return {'r_th_k_per_w':float(np.exp(fit.x[0])),'c_th_j_per_k':float(np.exp(fit.x[1])),'rmse_c':float(np.sqrt(np.mean((pred-y)**2))),'max_abs_c':float(np.max(np.abs(pred-y))),'converged':bool(fit.success),'nfev':int(fit.nfev),'prediction_c':pred}
