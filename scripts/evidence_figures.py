"""Render scientific figures from archived NPZ/CSV data, without rerunning models."""
from pathlib import Path
import csv, hashlib, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/figures'; OUT.mkdir(exist_ok=True,parents=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
    for ext in ['png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)
def main():
    raw=ROOT/'outputs/physics/steady_1um.npz'; p=np.load(raw)
    fig,ax=plt.subplots(figsize=(7,5.1),layout='constrained')
    t=np.ma.array(p['temperature_c'],mask=~p['domain_mask'].astype(bool))
    im=ax.imshow(t,origin='lower',extent=[p['x_m'].min()*1e6,p['x_m'].max()*1e6,p['y_m'].min()*1e6,p['y_m'].max()*1e6],cmap='inferno')
    ax.set(xlabel='x (um)',ylabel='y (um)',title='Assumed microhotplate: 1 um spatial mesh, 50% duty')
    fig.colorbar(im,ax=ax,label='temperature (C)');save(fig,'physics_temperature')
    transient=ROOT/'outputs/physics/transient_validation.npz'; z=np.load(transient)
    v=json.loads((ROOT/'outputs/physics/validation.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(10.8,4.2),layout='constrained')
    axes[0].plot([m['cell_m']*1e6 for m in v['meshes']],[m['active_peak_c'] for m in v['meshes']],'-o',color='#176e7d')
    axes[0].set(xlabel='cell width (um)',ylabel='active peak temperature (C)',title='Spatial refinement');axes[0].invert_xaxis()
    axes[1].plot(z['heldout_times_s'],z['heldout_mean_c'],label='spatial FVM',color='#176e7d')
    axes[1].plot(z['heldout_times_s'],z['heldout_prediction_c'],'--',label='fitted RC',color='#b45b37')
    axes[1].set(xlabel='time (s)',ylabel='active mean temperature (C)',title='Held-out 65% duty pulse');axes[1].legend(frameon=False)
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'physics_validation')
    trace=ROOT/'results/raw/experiments/rtl-20261027T140947426703Z/trace.csv'
    rows=list(csv.DictReader(trace.open()));ts=[float(r['t_s']) for r in rows]
    fig,axes=plt.subplots(2,1,figsize=(9.5,5.6),sharex=True,layout='constrained')
    axes[0].plot(ts,[float(r['temp_c']) for r in rows],label='RC plant driven by actual RTL',color='#176e7d')
    axes[0].step(ts,[float(r['setpoint_c']) if r['phase']!='cooldown' else float('nan') for r in rows],where='post',ls='--',color='#b45b37',label='powered-phase setpoint')
    axes[0].set(ylabel='temperature (C)',title='Held-out RTL-in-loop: hold RMSE 2.342 C (target <=2 C missed)');axes[0].legend(frameon=False)
    axes[1].step(ts,[float(r['duty_q8'])/256 for r in rows],where='post',color='#176e7d')
    axes[1].set(xlabel='plant time (s)',ylabel='RTL duty fraction',ylim=(-.04,1.04))
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'rtl_closed_loop')
    files=[raw,transient,trace,ROOT/'outputs/physics/validation.json']
    (OUT/'evidence_figures.json').write_text(json.dumps({'sources':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'method':'render archived numeric data; actual GDS captures are separate'},indent=2)+'\n')
if __name__=='__main__':main()
