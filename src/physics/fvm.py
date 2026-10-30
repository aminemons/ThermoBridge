"""Sparse 2-D thin-film electrothermal finite-volume solver (assumptions in config)."""
from __future__ import annotations
from dataclasses import dataclass
import json, math
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.sparse.csgraph import connected_components

SIGMA_SB=5.670374419e-8

@dataclass
class Params:
    active_m: float=200e-6
    extension_m: float=40e-6
    anchor_width_m: float=12e-6
    heater_width_m: float=8e-6
    heater_pitch_m: float=40e-6
    cell_m: float=4e-6
    ambient_c: float=25.0
    voltage_v: float=0.15
    membrane_thickness_m: float=0.8e-6
    membrane_rho: float=3100.0
    membrane_cp: float=700.0
    membrane_k: float=3.0
    heater_thickness_m: float=0.2e-6
    heater_rho: float=21450.0
    heater_cp: float=133.0
    heater_k: float=71.6
    resistivity_ref_ohm_m: float=1.06e-7
    tcr_per_k: float=0.0032
    emissivity: float=0.35
    genv_w_m2_k: float=4.0
    valid_min_c: float=20.0
    valid_max_c: float=350.0

    @classmethod
    def from_json(cls, path):
        geo=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        mat=json.loads(Path(path).with_name('materials.json').read_text(encoding='utf-8-sig'))
        return cls(active_m=geo['active_width_m'], extension_m=geo['domain_extension_m'], anchor_width_m=geo['anchor_width_m'], heater_width_m=geo['heater_trace_width_m'], heater_pitch_m=geo['heater_pitch_m'], cell_m=geo['mesh_cell_m'], ambient_c=geo['ambient_c'], voltage_v=geo['heater_voltage_v'], membrane_thickness_m=mat['membrane']['thickness_m'], membrane_rho=mat['membrane']['density_kg_m3'], membrane_cp=mat['membrane']['heat_capacity_j_kg_k'], membrane_k=mat['membrane']['conductivity_w_m_k'], heater_thickness_m=mat['heater']['thickness_m'], heater_rho=mat['heater']['density_kg_m3'], heater_cp=mat['heater']['heat_capacity_j_kg_k'], heater_k=mat['heater']['conductivity_w_m_k'], resistivity_ref_ohm_m=mat['heater']['resistivity_ohm_m'], tcr_per_k=mat['heater']['tcr_per_k'], emissivity=mat['heater']['emissivity'], genv_w_m2_k=mat['environmental_loss_w_m2_k'], valid_min_c=mat['valid_range_c'][0], valid_max_c=mat['valid_range_c'][1])

class ElectroThermalFVM:
    def __init__(self,p:Params):
        self.p=p
        ratio=p.active_m/p.cell_m
        if abs(ratio-round(ratio))>1e-8 or abs(p.extension_m/p.cell_m-round(p.extension_m/p.cell_m))>1e-8: raise ValueError('cell size must divide active width and extension')
        self.n=int(round((p.active_m+2*p.extension_m)/p.cell_m)); self.dx=self.dy=p.cell_m; self.area=self.dx*self.dy
        if p.heater_width_m/self.dx < 2 or p.anchor_width_m/self.dx < 2: raise ValueError('heater/anchor widths unresolved: require at least 2 cells')
        self.x=(np.arange(self.n)+.5)*self.dx-(self.n*self.dx)/2
        self.y=(np.arange(self.n)+.5)*self.dy-(self.n*self.dy)/2
        X,Y=np.meshgrid(self.x,self.y)
        h=p.active_m/2; e=p.extension_m; a=p.anchor_width_m/2
        self.domain=(np.abs(X)<=h)&(np.abs(Y)<=h)
        # Four narrow supports reach the outer boundary from the active perimeter.
        self.domain |= (np.abs(Y)<=a)&(np.abs(X)>=h)&(np.abs(X)<=h+e)
        self.domain |= (np.abs(X)<=a)&(np.abs(Y)>=h)&(np.abs(Y)<=h+e)
        self.active=(np.abs(X)<=h)&(np.abs(Y)<=h)
        edge=(np.isclose(np.abs(X),h+e-self.dx/2,atol=self.dx*0.1)&(np.abs(Y)<=a)) | (np.isclose(np.abs(Y),h+e-self.dy/2,atol=self.dy*0.1)&(np.abs(X)<=a))
        self.anchor=self.domain&edge
        self.heater=self._heater_mask()
        self.thermal_ids=np.full((self.n,self.n),-1,int); self.thermal_ids[self.domain]=np.arange(self.domain.sum())
        self.ids=self.thermal_ids
        self._build_thermal()
        self._check_electrical_connectivity()

    def _heater_mask(self):
        p=self.p; h=p.active_m/2; pitch=p.heater_pitch_m
        # Odd number of horizontal legs connects opposite side terminals.
        count=int(math.floor((p.active_m-pitch/2)/pitch))+1
        ys=np.linspace(-h+pitch/2,h-pitch/2,count)
        points=[]
        side=0
        points.append(((-h,ys[0]),(h,ys[0])))
        for i in range(1,count):
            x=h if (i%2==1) else -h
            points.append(((x,ys[i-1]),(x,ys[i])))
            points.append(((x,ys[i]),(-x,ys[i])))
        X,Y=np.meshgrid(self.x,self.y); mask=np.zeros_like(X,dtype=bool)
        for (x0,y0),(x1,y1) in points:
            if abs(x0-x1)<1e-15: d=np.abs(X-x0); ok=(Y>=min(y0,y1)-p.heater_width_m/2)&(Y<=max(y0,y1)+p.heater_width_m/2)
            else: d=np.abs(Y-y0); ok=(X>=min(x0,x1)-p.heater_width_m/2)&(X<=max(x0,x1)+p.heater_width_m/2)
            mask |= ok&(d<=p.heater_width_m/2)
        # End terminals are cells on the terminal end of the serpentine.
        mask &= self.active
        self.terminal0=mask&(X<=-h+self.dx*1.1)&(np.abs(Y-ys[0])<=p.heater_width_m/2+self.dy/2)
        ex=h if count%2==1 else -h
        ey=ys[-1]
        self.terminal1=mask&(X>=h-self.dx*1.1 if ex>0 else X<=-h+self.dx*1.1)&(np.abs(Y-ey)<=p.heater_width_m/2+self.dy/2)
        if not self.terminal0.any() or not self.terminal1.any(): raise ValueError('heater terminal mask empty; refine or adjust geometry')
        return mask

    def _check_electrical_connectivity(self):
        ids=np.full((self.n,self.n),-1,int); ids[self.heater]=np.arange(self.heater.sum())
        rr=[]; cc=[]
        for dy,dx in ((0,1),(1,0)):
            a=self.heater[:self.n-dy or None,:self.n-dx or None]; b=self.heater[dy:,dx:]
            ia=ids[:self.n-dy or None,:self.n-dx or None][a&b]; ib=ids[dy:,dx:][a&b]
            rr.extend(ia); cc.extend(ib)
        adj=sparse.coo_matrix((np.ones(2*len(rr)),(rr+cc,cc+rr)),shape=(self.heater.sum(),)*2).tocsr()
        ncomp, labels=connected_components(adj,directed=False)
        labels0=set(labels[ids[self.terminal0]]); labels1=set(labels[ids[self.terminal1]])
        if len(labels0 & labels1)==0: raise ValueError('heater terminals are electrically disconnected on this mesh')
        # Disconnected nonterminal islands are rejected, not hidden with regularization.
        useful=labels0|labels1
        if len(useful)<ncomp: raise ValueError('heater mask contains electrically disconnected component(s)')

    def _build_thermal(self):
        nvar=self.domain.sum(); ids=self.ids
        # Sheet conductance K_s; heater layer contributes only under heater cells.
        self.K=np.full((self.n,self.n),self.p.membrane_k*self.p.membrane_thickness_m)
        self.K[self.heater]+=self.p.heater_k*self.p.heater_thickness_m
        self.C=np.full((self.n,self.n),self.p.membrane_rho*self.p.membrane_cp*self.p.membrane_thickness_m)
        self.C[self.heater]+=self.p.heater_rho*self.p.heater_cp*self.p.heater_thickness_m
        rr=[];cc=[];vv=[]; diag=np.zeros(nvar)
        for di,dj,flen,dist in ((0,1,self.dy,self.dx),(1,0,self.dx,self.dy)):
            for iy,ix in zip(*np.where(self.domain & np.roll(self.domain,(-di,-dj),(0,1)))):
                jy,jx=iy+di,ix+dj
                if jy>=self.n or jx>=self.n or not self.domain[jy,jx]: continue
                k1=self.K[iy,ix]; k2=self.K[jy,jx]; kh=2*k1*k2/(k1+k2)
                g=kh*flen/dist; a=ids[iy,ix]; b=ids[jy,jx]
                rr.extend((a,a,b,b));cc.extend((a,b,a,b));vv.extend((g,-g,-g,g));diag[a]+=0;diag[b]+=0
        self.L=sparse.coo_matrix((vv,(rr,cc)),shape=(nvar,nvar)).tocsr()
        self.domain_flat=np.flatnonzero(self.domain); self.anchor_flat=np.flatnonzero(self.anchor)
        self.anchor_ids=ids[self.anchor]; self.free_mask=~self.anchor.ravel()[self.domain_flat]
        self.free_ids=np.flatnonzero(self.free_mask)
        self.free_domain_flat=self.domain_flat[self.free_mask]
        self.Lff=self.L[self.free_ids][:,self.free_ids].tocsr(); self.Lfa=self.L[self.free_ids][:,self.anchor_ids].tocsr()
        if self.free_ids.size==0: raise ValueError('thermal domain has no free cells')

    def electrical(self,T_c):
        p=self.p
        bad=(T_c[self.heater]<p.valid_min_c)|(T_c[self.heater]>p.valid_max_c)
        if bad.any(): raise ValueError('heater temperature outside documented resistivity range')
        rho=p.resistivity_ref_ohm_m*(1+p.tcr_per_k*(T_c-p.ambient_c))
        if np.any(rho[self.heater]<=0): raise ValueError('non-positive resistivity')
        G=p.heater_thickness_m/rho
        ids=np.full((self.n,self.n),-1,int); ids[self.heater]=np.arange(self.heater.sum())
        term=self.terminal0|self.terminal1; v=np.zeros(self.heater.sum()); v[ids[self.terminal1]]=p.voltage_v
        unknown=~term[self.heater]; uids=np.flatnonzero(unknown); pos=np.full(self.heater.sum(),-1,int); pos[uids]=np.arange(len(uids))
        rr=[];cc=[];vv=[];rhs=np.zeros(len(uids))
        for dy,dx,flen,dist in ((0,1,self.dy,self.dx),(1,0,self.dx,self.dy)):
            a_mask=self.heater[:self.n-dy or None,:self.n-dx or None]; b_mask=self.heater[dy:,dx:]; both=a_mask&b_mask
            ay,ax=np.where(both); by=ay+dy; bx=ax+dx
            for y1,x1,y2,x2 in zip(ay,ax,by,bx):
                i=ids[y1,x1];j=ids[y2,x2]; g=2*G[y1,x1]*G[y2,x2]/(G[y1,x1]+G[y2,x2])*flen/dist
                if unknown[i]:
                    a=pos[i];rr.append(a);cc.append(a);vv.append(g)
                    if unknown[j]:rr.append(a);cc.append(pos[j]);vv.append(-g)
                    else:rhs[a]+=g*v[j]
                if unknown[j]:
                    b=pos[j];rr.append(b);cc.append(b);vv.append(g)
                    if unknown[i]:rr.append(b);cc.append(pos[i]);vv.append(-g)
                    else:rhs[b]+=g*v[i]
        A=sparse.coo_matrix((vv,(rr,cc)),shape=(len(uids),len(uids))).tocsr()
        phi=v.copy(); phi[uids]=spsolve(A,rhs)
        if not np.all(np.isfinite(phi)): raise RuntimeError('electrical solve non-finite')
        power=np.zeros((self.n,self.n)); current=0.0
        for dy,dx,flen,dist in ((0,1,self.dy,self.dx),(1,0,self.dx,self.dy)):
            a_mask=self.heater[:self.n-dy or None,:self.n-dx or None]; b_mask=self.heater[dy:,dx:]; both=a_mask&b_mask
            ay,ax=np.where(both); by=ay+dy; bx=ax+dx
            for y1,x1,y2,x2 in zip(ay,ax,by,bx):
                i=ids[y1,x1]; j=ids[y2,x2]; g=2*G[y1,x1]*G[y2,x2]/(G[y1,x1]+G[y2,x2])*flen/dist
                pw=g*(phi[i]-phi[j])**2/2
                power[y1,x1]+=pw;power[y2,x2]+=pw
        # Terminal current from all edges incident on source cells.
        current=0.0
        for dy,dx,flen,dist in ((0,1,self.dy,self.dx),(1,0,self.dx,self.dy)):
            a_mask=self.heater[:self.n-dy or None,:self.n-dx or None]; b_mask=self.heater[dy:,dx:]; both=a_mask&b_mask
            ay,ax=np.where(both);by=ay+dy;bx=ax+dx
            for y1,x1,y2,x2 in zip(ay,ax,by,bx):
                i=ids[y1,x1];j=ids[y2,x2]
                if self.terminal0[y1,x1] or self.terminal0[y2,x2]:
                    g=2*G[y1,x1]*G[y2,x2]/(G[y1,x1]+G[y2,x2])*flen/dist
                    if self.terminal0[y1,x1]: current+=g*(0-phi[j])
                    if self.terminal0[y2,x2]: current+=g*(0-phi[i])
        # Current is signed into the zero volt terminal; use magnitude.
        current=abs(current)
        V=np.full((self.n,self.n),np.nan); V[self.heater]=phi
        return V,power,current,p.voltage_v*current

    def thermal_step(self,T_c,power_cell_w,dt_s,max_iter=30,tol_k=1e-7):
        p=self.p; ta=p.ambient_c+273.15; old=T_c[self.domain].copy()+273.15
        q=power_cell_w[self.domain]/self.area
        C=self.C[self.domain]; cap=C*self.area/dt_s; env=p.genv_w_m2_k*self.area
        T=old.copy(); anchors=np.full(len(self.anchor_ids),ta)
        free=self.free_ids; act=np.flatnonzero(self.free_mask)
        oldf=old[act]; qf=q[act]; Cf=C[act]
        for _ in range(max_iter):
            guess=T[act]
            rad_d=4*p.emissivity*SIGMA_SB*self.area*np.maximum(guess,1.0)**3
            diag=cap[act]+env+rad_d
            A=self.Lff+sparse.diags(diag)
            rhs=cap[act]*oldf+qf*self.area+env*ta+p.emissivity*SIGMA_SB*self.area*(ta**4+3*guess**4)
            # anchors fixed at ambient
            rhs-=self.Lfa@anchors
            new=spsolve(A,rhs)
            if np.max(np.abs(new-guess))<tol_k:
                T[act]=new; break
            T[act]=new
        else: raise RuntimeError('thermal radiation iteration did not converge')
        out=T_c.copy();out[self.domain]=T-273.15;out[self.anchor]=p.ambient_c
        return out

    def simulate_transient(self, duties, times_s, initial_c=None, coupling_tol_k=2e-5, max_coupling_iter=20):
        """Implicit thermal transient with electrically lagged sources per interval."""
        times=np.asarray(times_s,float); ds=np.asarray(duties,float)
        if times.ndim!=1 or ds.shape!=times.shape or len(times)<2 or times[0]!=0 or np.any(np.diff(times)<=0): raise ValueError('times must start at zero and strictly increase; duty must match')
        if np.any((ds<0)|(ds>1)): raise ValueError('duty must be in [0,1]')
        T=np.full((self.n,self.n),self.p.ambient_c if initial_c is None else initial_c); out=[T.copy()]; powers=[0.0]
        for k in range(1,len(times)):
            old=T.copy(); guess=old.copy(); dt=times[k]-times[k-1]; d=ds[k-1]
            for _ in range(max_coupling_iter):
                phi,pw,current,pinst=self.electrical(guess); pw*=d
                nxt=self.thermal_step(old,pw,dt)
                if np.max(np.abs(nxt[self.heater]-guess[self.heater]))<coupling_tol_k:
                    guess=nxt; break
                guess=nxt
            else: raise RuntimeError(f'electrothermal transient coupling failed at sample {k}')
            T=guess; out.append(T.copy()); powers.append(float(pw.sum()))
        return {'times_s':times,'temperature_c':np.asarray(out),'joule_power_w':np.asarray(powers),'interval_power_w':np.asarray(powers[1:]),'active_mean_c':np.asarray([q[self.active].mean() for q in out]),'active_peak_c':np.asarray([q[self.active].max() for q in out])}

    def solve_steady(self,duty=1.0,max_iter=80,tol_k=1e-5):
        p=self.p; temp=np.full((self.n,self.n),p.ambient_c); pwr=None
        for it in range(max_iter):
            phi,pwr,current,input_w=self.electrical(temp)
            pwr*=duty
            nxt=self.thermal_step(temp,pwr,dt_s=1e5)
            err=np.max(np.abs(nxt[self.domain]-temp[self.domain]))
            temp=nxt
            if err<tol_k: break
        else: raise RuntimeError('coupled electrothermal iteration did not converge')
        phi,pwr,current,input_w=self.electrical(temp); pwr*=duty; input_w*=duty
        gen=pwr.sum(); balance=abs(input_w-gen)/max(abs(input_w),1e-15)
        roi=self.active & (np.abs(self.x[None,:])<p.active_m*.25)&(np.abs(self.y[:,None])<p.active_m*.25)
        tkel=temp[self.domain]+273.15; ta=p.ambient_c+273.15
        env_loss=float((p.genv_w_m2_k*self.area*(tkel-ta)).sum())
        rad_loss=float((p.emissivity*SIGMA_SB*self.area*(tkel**4-ta**4)).sum())
        full_t=np.zeros((self.n,self.n)); full_t[self.domain]=temp[self.domain]+273.15
        anchor_sink=float(-np.asarray(self.L@full_t[self.domain]).ravel()[self.anchor_ids].sum())
        thermal_res=abs(input_w-env_loss-rad_loss-anchor_sink)/max(abs(input_w),1e-15)
        return {'temperature_c':temp,'potential_v':phi,'joule_w':pwr,'current_a':current*duty,'input_power_w':input_w,'joule_power_w':gen,'power_balance_rel':balance,'thermal_balance_rel':thermal_res,'environment_loss_w':env_loss,'radiation_loss_w':rad_loss,'anchor_loss_w':anchor_sink,'active_mean_c':float(temp[self.active].mean()),'active_peak_c':float(temp[self.active].max()),'roi_std_c':float(temp[roi].std()),'roi_peak_minus_mean_c':float(temp[roi].max()-temp[roi].mean()),'iterations':it+1}



def rectangular_resistor(length_m=100e-6,width_m=80e-6,thickness_m=0.2e-6,resistivity_ohm_m=1.06e-7,cell_m=2e-6):
    """FV benchmark for a uniform rectangular sheet with full-width end electrodes."""
    nx=int(round(length_m/cell_m)); ny=int(round(width_m/cell_m))
    if min(nx,ny)<2 or abs(nx*cell_m-length_m)>1e-12 or abs(ny*cell_m-width_m)>1e-12: raise ValueError('cell size must divide rectangle and leave at least 2 cells per direction')
    n=nx*ny; sheet=thickness_m/resistivity_ohm_m; dx=cell_m;dy=cell_m
    # End columns are equipotential. Unknown cells span columns 1..nx-2.
    uid=np.full((ny,nx),-1,int); unknown=np.ones((ny,nx),bool);unknown[:,0]=False;unknown[:,-1]=False;uid[unknown]=np.arange(unknown.sum())
    rr=[];cc=[];vv=[];rhs=np.zeros(unknown.sum());v0=0.;v1=1.
    for y in range(ny):
      for x in range(nx):
        for yy,xx,flen,dist in ((y,x+1,dy,dx),(y+1,x,dx,dy)):
          if yy>=ny or xx>=nx: continue
          g=sheet*flen/dist;i=uid[y,x];j=uid[yy,xx]
          if unknown[y,x]:
            rr.append(i);cc.append(i);vv.append(g)
            if unknown[yy,xx]:rr.append(i);cc.append(j);vv.append(-g)
            else:rhs[i]+=g*(v0 if xx==0 else v1)
          if unknown[yy,xx]:
            rr.append(j);cc.append(j);vv.append(g)
            if unknown[y,x]:rr.append(j);cc.append(i);vv.append(-g)
            else:rhs[j]+=g*(v0 if x==0 else v1)
    A=sparse.coo_matrix((vv,(rr,cc)),shape=(len(rhs),len(rhs))).tocsr();u=spsolve(A,rhs)
    phi=np.empty((ny,nx));phi[:,0]=v0;phi[:,-1]=v1;phi[unknown]=u
    g=sheet*dy/dx; current=float(np.sum(g*(phi[:,-1]-phi[:,-2])))
    return {'resistance_ohm':1/current,'analytic_ohm':resistivity_ohm_m*length_m/(width_m*thickness_m),'discrete_analytic_ohm':resistivity_ohm_m*(nx-1)*dx/(width_m*thickness_m),'current_a':current,'potential_v':phi}
