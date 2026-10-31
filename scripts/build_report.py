"""Build an eight-page report directly from the archived release evidence."""
from pathlib import Path
import csv, json
from html import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports'; OUT.mkdir(exist_ok=True)
def main():
    snapshot=json.loads((OUT/'release_snapshot.json').read_text())
    physical=json.loads((OUT/'asic/summary.json').read_text())
    rows=list(csv.DictReader((ROOT/'results/processed'/f"experiment_summary_{snapshot['primary_experiment_run']}.csv").open()))
    by={r['controller']:r for r in rows}
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCustom',fontName='Helvetica-Bold',fontSize=28,leading=33,textColor=colors.HexColor('#153943'),spaceAfter=18))
    styles['BodyText'].fontSize=10;styles['BodyText'].leading=14;styles['BodyText'].spaceAfter=10
    styles['Heading1'].textColor=colors.HexColor('#176e7d');styles['Heading1'].spaceAfter=14
    styles.add(ParagraphStyle(name='CaptionCustom',fontSize=8,leading=11,textColor=colors.HexColor('#48555b'),spaceAfter=12))
    story=[];md=['# ThermoBridge technical report','27 October 2026 | conditional research snapshot','']
    def p(text,style='BodyText'):
        story.append(Paragraph(escape(text),styles[style]));md.extend([text,''])
    def title(n,text):
        if n>1:story.append(PageBreak())
        p(f'{n}. {text}','Heading1');md.append('## '+text)
    def fig(name,caption,height=225):
        path=ROOT/'docs/figures'/name; w,h=ImageReader(str(path)).getSize();scale=min(475/w,height/h)
        story.append(Image(str(path),width=w*scale,height=h*scale));story.append(Spacer(1,7));p(caption,'CaptionCustom');md.append(f'![{caption}](../docs/figures/{name})\n')
    def table(data,widths):
        data=[[Paragraph(escape(str(cell)),styles['CaptionCustom']) for cell in row] for row in data]
        t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eef0')),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#176e7d')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8f9')])]))
        story.extend([t,Spacer(1,12)])
    title(1,'Question, scope and evidence')
    p('ThermoBridge','TitleCustom')
    p('Electrothermal modelling and a fixed-point sensor-controller ASIC')
    p('Research question: can a spatially informed feedforward plus PI controller improve microhotplate tracking while retaining a small, verifiable digital implementation? This snapshot builds a traceable path from assumed membrane physics to a routed SKY130 digital core. It does not establish a new control algorithm or experimentally validated sensor performance.')
    table([['Evidence','Observed result'],['Spatial validation','Final mesh peak change 0.55%; held-out compact-model RMSE 0.0443 C'],['Controller verification','25 Python tests and 2 actual cocotb RTL tests passed'],['Routed core','Magic/KLayout DRC and Netgen LVS: zero errors'],['Timing','10 MHz conditional on ADC arrival <=15 ns; setup +1.681 ns'],['Held-out RTL control','2.342 C hold RMSE: <=2 C target missed'],['Broader campaign','20 scenarios x 3 seeds x 9 controller/arithmetic variants = 540 trials']], [158,317])
    p('All material properties and process-independent membrane dimensions are assumptions. The membrane, ADC, differential sensing amplifier and heater switch are external to the digital core. There are no measured silicon, fabricated membranes, gas-selectivity data or certified operating limits. Heater energy is distinct from unestimated digital-core and amplifier power.')
    p('Technical snapshot: 27 October 2026. Project authors: Amine Allab and Ishaq Kolla. The numerical and physical findings are bounded by the documented verification conditions; independent reproduction remains necessary. See docs/CONTRIBUTIONS.md.')
    title(2,'Spatial electrothermal model')
    p('The model solves div(sigma(T) grad(phi))=0 and a thin-film thermal balance C_A dT/dt = div(K_A grad(T)) + q_J - q_loss, with local Joule heating and temperature-dependent resistance. Harmonic face conductance preserves interface fluxes. Anchors are held at ambient; suspended boundaries have zero lateral flux. Boundary loss coefficients and layer properties are declared in configs/materials.json.')
    p('The active membrane is 200 um square with a 40 um extension, 12 um anchors and a heater represented by 8 um traces at 40 um pitch. A 0.15 V heater supply and 25 C ambient define the primary case. Sparse finite-volume systems cover the resolved geometry; steady electrical and thermal solves are iterated to convergence. Transients use an electrically lagged source with implicit thermal integration.')
    fig('physics_temperature.png','Figure 1. Actual 1 um-grid solution at 50% duty. Source: outputs/physics/steady_1um.npz. Assumed geometry, not a foundry MEMS layout.',260)
    p('At 1 um, the active mean is 67.148 C and peak 68.637 C. Terminal power is 0.118094 mW. Electrical and thermal balance residuals are below 1e-8 relative. These are internal conservation checks, not agreement with a physical measurement. Through-thickness gradients, interfacial thermal resistance and independent 3-D validation are absent.')
    title(3,'Numerical validation and compact reduction')
    table([['Check','Result','Scope'],['Rectangular resistor','0.655875 versus 0.6625 ohm','1% discrete/continuum difference'],['4, 2, 1 um peak temperature','67.470, 68.260, 68.637 C','0.55% final refinement change'],['Dominant passive time constant','26.480 ms','Ambient linearized spectral estimate'],['Compact fit','Rth 349137 K/W; Cth 75.895 nJ/K','Primary 4 um mesh; tau 26.498 ms'],['Training / held-out RMSE','0.00773 / 0.04427 C','Separate 50% / 65% duty transients'],['1 ms versus 0.5 ms trajectory','0.385% normalized difference','Time-step refinement']], [144,174,157])
    fig('physics_validation.png','Figure 2. Spatial refinement and a held-out pulse/cooldown. Sources: validation.json and transient_validation.npz under outputs/physics.',215)
    p('The RC model obeys Cth dT/dt = P - (T-Ta)/Rth with P=d V^2/R(T). Positive parameters were fitted to the primary geometry training trajectory, then frozen. Its held-out maximum absolute error is 0.0686 C. Accuracy at another geometry, temperature range or unmodelled loss mechanism is not implied.')
    p('A separate bounded PWM test compares analytic on/off RC phases against period-averaged heating at 39.0625 kHz, for duties 0.25, 0.50 and 0.75 over 800 periods. Maximum endpoint disagreement is 0.00550 C, with maximum intra-period ripple 0.01150 C. This supports averaging in this regime, not a spatial switched-PWM validation. See reports/pwm_validation.json.')
    title(4,'Readout, arithmetic and fault verification')
    p('A nonlinear resistance divider drives a quantized 12-bit ADC. R(T)=R0[1+alpha(T-25 C)]; gain, offset, noise, delayed samples and exact continuous-time two-state RTN are configurable. Samples without a valid powered observation window are invalid. A 1/256 probe at commanded-zero powered samples is included in heater energy. Cooldown remains off. Sensing-source energy is counted separately; amplifier and digital switching energy are unavailable.')
    table([['Implemented contract','Representation / behaviour'],['Temperature and calibration','Signed 16-bit, 6 fractional bits; 18-bit Q14 gain; ties-to-even rounding'],['PI and saturation','18-bit Q14 gains, 24-bit integrator, 26-bit combined sum; explicit saturation and anti-windup'],['Feedforward','16 x 9-bit table; shadow writes and atomic commit'],['Duty and timing','9-bit 0..256 endpoints; 8-bit PWM phase; 10 MHz clock; 1 ms default control period'],['Faults','Stale, overtemperature, calibration, rails and shutdown; latched safe-off and explicit clear']], [155,320])
    p('Tests cover reference rounding/saturation, atomic configuration, PWM endpoints, controller comparisons, reset, fault latching and clearing. The cocotb harness records 271 accepted temperature comparisons and 267 controller comparisons, including a seeded 261-code ADC sequence and directed tests. Both RTL wrappers inspect XML results and fail nonzero when cocotb fails; historical aborted runs are retained as failed evidence.')
    p('These are simulation checks. There is no completed formal proof, post-route gate-level equivalence, physical ADC clock-domain validation or hardware board test. Numeric width variants use the same fractional precision and were not independently routed, so no silicon-area advantage is claimed.')
    title(5,'Held-out actual RTL feedback')
    p('The actual synthesizable controller, executed by Icarus/cocotb, supplies duty at each plant sample; the fitted RC and nonlinear ADC return the next observation. Six actual-RTL training candidates used a 50-to-60 C schedule. Selected KP=1147/16384 and KI=4/16384 per sample were frozen before a 55-to-65 C held-out run. This subset uses an ideal external centered front end (18 mV excitation, 8.6 mV reference, gain 800, calibration at 40/80 C); it is distinct from the broader Python campaign.')
    fig('rtl_closed_loop.png','Figure 3. Real RTL-in-loop trace: results/raw/experiments/rtl-20261027T140947426703Z/trace.csv. The accelerated divider is 32 clocks per plant sample.',260)
    p(f"Held-out hold-window RMSE is {snapshot['rtl_in_loop']['rmse_hold_c']:.4f} C, above the initial <=2 C target. Total heater-terminal energy is 16.683 uJ: warmup 10.764 uJ, hold 5.918 uJ and cooldown zero. Separate sensing-source energy is 0.290 uJ. No powered-phase faults occurred; off-state cooldown eventually latches stale while PWM remains off.")
    p('The test advances physical plant time by 1 ms per accelerated control tick. It is not a full clock-accurate simulation of each physical PWM period. The timebase acceleration, ideal front end and finite held-out subset limit system-level conclusions. No test-window substitution or success claim hides the target miss.')
    title(6,'Paired campaign and negative results')
    p('The frozen manifest spans ambient, thermal resistance/capacitance, heater resistance/TCR, front-end gain/offset, noise, latency and combined cases. Seeds 11, 29 and 47 are paired across controllers. Three separate training scenarios select gains before testing. Each cycle uses 4 tau warmup, 2 tau hold with a midpoint setpoint step, and 3 tau cooldown. Assumed variations are scenarios, not empirical yield distributions.')
    table([['Controller','Trials','Hold RMSE mean / median (C)','Heater energy mean (uJ)','Settling failures'],*[[name.upper(),r['n'],f"{float(r['rmse_mean_c']):.3f} / {float(r['rmse_median_c']):.3f}",f"{1e6*float(r['energy_mean_j']):.3f}",f"{r['failure_count']}/{r['n']}"] for name in ['bangbang','pi','ffpi'] for r in [by[name]]]], [74,42,130,115,114])
    fig('experiment_energy_tracking.png','Figure 4. Each point is a paired scenario/seed trial; crosses identify settling failures. Source: primary campaign metrics.csv. Energy includes heater probe pulses.',245)
    p('Feedforward plus PI improves aggregate tracking relative to this PI tuning but consumes more average heater energy. It does not demonstrate the proposed 5-15% energy saving. Settling failures are common and remain in the table. Fixed-point 16/20/24-bit variants at the same six temperature fractional bits have essentially identical aggregate performance; this does not establish a hardware Pareto frontier. Earlier unrelated 5 V RC experiments are historical, not primary evidence.')
    title(7,'Implemented SKY130 digital core')
    p('The existing installed IIC-OSIC-TOOLS image and SKY130A sky130_fd_sc_hd library were reused. A complete LibreLane flow produced GDS, DEF, LEF, mapped/powered netlists and extracted SPEF. Reported standard-cell area is 69,405.3 um2 and core area 158,379 um2. These include the stated flow conventions, not a packaged die area. No activity-qualified digital-power estimate is available.')
    fig('routed_core.png','Figure 5. KLayout capture of actual generated GDS. View extent and source are recorded in docs/figures/gds_capture.json. No pads, ADC or membrane are present.',255)
    p('Original route checks: zero detailed-route, Magic DRC, KLayout DRC, antenna and Netgen LVS errors. At 100 ns clock with 20 ns ADC input delay, worst setup slack was -3.319 ns. The same geometry was rechecked with an explicit 15 ns ADC code/valid arrival contract; other I/O budgets remain 20 ns. Worst setup is +1.681 ns and hold +0.107 ns across nine installed timing corners. There are no disabled or multicycle timing paths.')
    p('This is a conditional interface qualification. It requires the external source to satisfy the tighter ADC budget and is not a measured maximum frequency. Slew/capacitance warnings and floating-net observations remain in raw reports. Installed open-PDK checks are not foundry-qualified tapeout signoff. Original failing metrics remain archived; the authoritative conditional summary is reports/asic/summary.json.')
    title(8,'Reproduction, limits and next work')
    p('Repository: https://github.com/aminemons/ThermoBridge. Begin with README.md and reports/release_snapshot.json. The latter hashes RTL, constraints and primary numerical/experiment evidence. Every primary run retains configuration, seed, manifest, logs and raw values. Tools/PDK revisions are in reports/environment.json. Histories use ordinary current timestamps, and no unobserved human contributions are assigned.')
    p('Windows with the existing container: python scripts/container.py sync; python scripts/container.py run make test-physics test-rtl; python scripts/container.py run make simulate. Use selective fetch for results. Inside the configured Linux tool environment: make doctor, make test-physics, make test-rtl, make simulate, make figures, make synth, make gds. Full physical design is explicit and expensive; verify-layout audits archived physical evidence without silently rerouting.')
    p('For this archived report on the host: install requirements-report.txt, run python scripts/evidence_figures.py and python scripts/build_report.py. make release-check audits the conditional research snapshot; make release-check with scripts/release_check.py --strict also enforces the missed <=2 C target and returns failure. Geometry optimization via make sweep is explicitly unimplemented and fails nonzero.')
    p('Next work: improve training and sensing calibration on a new held-out protocol; independently reproduce the physical flow; resolve remaining electrical warnings; route arithmetic alternatives and quantify area/timing/activity-based power; implement the transistor readout macro with its own DRC/LVS/extracted simulations; add geometry Pareto studies and independent 3-D or measured validation. None is claimed complete here.')
    p('Primary sources and modest novelty','Heading2')
    for text in ['IIC-OSIC-TOOLS, existing open-source tool distribution: https://github.com/iic-jku/iic-osic-tools', 'SkyWater SKY130 open PDK documentation: https://skywater-pdk.readthedocs.io/', 'LibreLane source and flow implementation: https://github.com/librelane/librelane', 'KLayout documentation: https://www.klayout.de/doc/', 'Cocotb verification documentation: https://docs.cocotb.org/', 'Model assumptions and acceptance criteria: configs/physics.json, configs/evaluation_v1.json and docs/LIMITATIONS.md; code and raw results are retained in the repository.']:
        p(text,'CaptionCustom')
    p('The contribution is an auditable integration exercise connecting conventional electrothermal, compact-model and PI-control methods with fixed-point hardware. A systematic literature survey and independent comparison are still needed before asserting research novelty.')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#b7c9ce'));canvas.line(48,40,547,40)
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#48555b'))
        canvas.drawString(48,27,'ThermoBridge | 27 October 2026 | conditional research snapshot')
        canvas.drawRightString(547,27,str(doc.page))
    doc=SimpleDocTemplate(str(OUT/'technical_report.pdf'),pagesize=(595.28,841.89),rightMargin=56,leftMargin=56,topMargin=43,bottomMargin=54,title='ThermoBridge: conditional research snapshot',author='Amine Allab; Ishaq Kolla')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    (OUT/'technical_report.md').write_text('\n'.join(md),encoding='utf-8')
    print('Created reports/technical_report.pdf and .md from archived evidence.')
if __name__=='__main__':main()
