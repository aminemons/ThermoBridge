"""Data-first figures; every plot is generated from a saved simulation artifact."""
from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def generate(root:Path=ROOT)->list[str]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    out=root/'release_out'/'figures';out.mkdir(parents=True,exist_ok=True)
    inputs=root/'release_out'/'experiments'
    with (inputs/'traces.csv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    with (inputs/'metrics.csv').open(newline='',encoding='utf-8') as f:
        metrics=list(csv.DictReader(f))
    paths=[]
    def save(fig,name):
        fig.tight_layout()
        for ext in ('png','svg'):
            p=out/(name+'.'+ext)
            fig.savefig(p,dpi=170)
            paths.append(str(p.relative_to(root)))
        plt.close(fig)
    nominal=[r for r in rows if int(r['scenario'])==0]
    fig,ax=plt.subplots(figsize=(9.2,4.6))
    for name in ('bangbang','pi_float','pi_fixed','ffpi_fixed'):
        d=[r for r in nominal if r['controller']==name]
        ax.plot([float(x['time_s']) for x in d],[float(x['temperature_c']) for x in d],label=name)
    ax.plot([float(x['time_s']) for x in nominal if x['controller']=='pi_fixed'],
            [float(x['setpoint_c']) if x['setpoint_c'] else np.nan for x in nominal if x['controller']=='pi_fixed'],
            color='black',ls='--',lw=1.4,label='setpoint')
    ax.set(xlabel='Time (s)',ylabel='Membrane ROM temperature (°C)',title='Nominal paired controller simulations (assumed plant)')
    ax.grid(alpha=.2);ax.legend(ncol=3,fontsize=8)
    save(fig,'01_temperature')
    fig,ax=plt.subplots(figsize=(9.2,3.8))
    for name in ('bangbang','pi_float','pi_fixed','ffpi_fixed'):
        d=[r for r in nominal if r['controller']==name]
        ax.plot([float(x['time_s']) for x in d],[float(x['duty_q8'])/256 for x in d],label=name)
    ax.set(xlabel='Time (s)',ylabel='PWM duty (0–1)',title='Behavioural control outputs, not captured RTL waveforms')
    ax.grid(alpha=.2);ax.legend(ncol=4,fontsize=8)
    save(fig,'02_duty')
    fig,ax=plt.subplots(figsize=(7.8,4.6))
    for name in sorted(set(r['controller'] for r in metrics)):
        d=[r for r in metrics if r['controller']==name]
        ax.scatter([float(x['hold_rmse_c']) for x in d], [float(x['heater_energy_mj']) for x in d],
                   label=name,s=13,alpha=.6)
    ax.set(xlabel='Hold RMSE (°C)',ylabel='Heater energy (mJ)',title='Paired 24-case robustness and quality/energy tradeoff')
    ax.grid(alpha=.2);ax.legend(fontsize=8)
    save(fig,'03_energy_vs_tracking')
    fig,ax=plt.subplots(figsize=(9,4.4))
    names=['bangbang','pi_float','pi_fixed','ffpi_fixed','pi_compact','pi_wide']
    samples=[[float(x['hold_rmse_c']) for x in metrics if x['controller']==name] for name in names]
    ax.boxplot(samples,tick_labels=names,showfliers=True)
    ax.set(xlabel='Algorithm / model precision',ylabel='Hold RMSE (°C)',title='Scenario variation: results include unsuccessful cases')
    ax.grid(axis='y',alpha=.2);ax.tick_params(axis='x',labelrotation=16)
    save(fig,'04_robustness')
    raw=root/'outputs'/'physics'/'steady_4um.npz'
    if raw.is_file():
        data=np.load(raw)
        temp=np.where(data['domain_mask'].astype(bool),data['temperature_c'],np.nan)
        fig,ax=plt.subplots(figsize=(6,5.3))
        picture=ax.imshow(temp,origin='lower',extent=[min(data['x_m'])*1e6,max(data['x_m'])*1e6,
                                                       min(data['y_m'])*1e6,max(data['y_m'])*1e6])
        fig.colorbar(picture,ax=ax,label='Temperature (°C)')
        ax.set(xlabel='x (µm)',ylabel='y (µm)',title='4 µm grid spatial FVM, half-duty (assumed geometry)')
        save(fig,'05_spatial_temperature')
    physics=root/'outputs'/'physics'/'validation.json'
    if physics.is_file():
        validation=json.loads(physics.read_text())
        mesh=validation['meshes']
        fig,ax=plt.subplots(figsize=(6.4,4.1))
        ax.plot([m['cell_m']*1e6 for m in mesh],[m['active_peak_c'] for m in mesh],'-o')
        ax.invert_xaxis();ax.set(xlabel='Cell width (µm), finer to the right',ylabel='Peak active temperature (°C)',title='Mesh refinement from saved spatial FVM')
        ax.grid(alpha=.2)
        save(fig,'06_mesh_convergence')
    manifest={'plots':paths,'source':['release_out/experiments/traces.csv',
                                      'release_out/experiments/metrics.csv',
                                      'outputs/physics/validation.json',
                                      'outputs/physics/steady_4um.npz'],
              'no_chip_photo':True,
              'note':'GDS view intentionally absent until a real routed GDS exists.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return paths

if __name__=='__main__':
    print('\n'.join(generate()))
