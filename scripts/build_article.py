"""Render the evidence-backed README and a Times, two-column technical article."""
from pathlib import Path
import csv,hashlib,json,re,sys,textwrap
from html import escape
from urllib.parse import quote
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate,Frame,PageTemplate,Paragraph,Spacer,Image,Table,TableStyle,KeepTogether,NextPageTemplate,Preformatted
ROOT=Path(__file__).resolve().parents[1];FIG=ROOT/'docs/figures';OUT=ROOT/'reports'
sys.path.insert(0,str(ROOT))

def save(fig,name):
    for ext in ['png','svg']:
        path=FIG/f'{name}.{ext}';fig.savefig(path,dpi=300,bbox_inches='tight')
        if ext=='svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
    plt.close(fig)

def figures(rtl,geometry):
    plt.rcParams.update({'font.size':8,'axes.titlesize':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'axes.spines.top':False,'axes.spines.right':False})
    p=np.load(ROOT/'outputs/physics/steady_1um.npz')
    fig,ax=plt.subplots(figsize=(3.5,2.7),layout='constrained')
    im=ax.imshow(np.ma.array(p['temperature_c'],mask=~p['domain_mask'].astype(bool)),origin='lower',extent=[p['x_m'].min()*1e6,p['x_m'].max()*1e6,p['y_m'].min()*1e6,p['y_m'].max()*1e6],cmap='inferno')
    ax.set(xlabel='x (µm)',ylabel='y (µm)');fig.colorbar(im,ax=ax,label='temperature (°C)',shrink=.86);save(fig,'physics_temperature_article')
    z=np.load(ROOT/'outputs/physics/transient_validation.npz');v=json.loads((ROOT/'outputs/physics/validation.json').read_text())
    fig,axes=plt.subplots(2,1,figsize=(3.5,3.65),layout='constrained')
    axes[0].plot([m['cell_m']*1e6 for m in v['meshes']],[m['active_peak_c'] for m in v['meshes']],'-o',color='#174c6b',ms=4)
    axes[0].set(xlabel='mesh cell width (µm)',ylabel='peak temperature (°C)');axes[0].invert_xaxis()
    axes[1].plot(z['heldout_times_s'],z['heldout_mean_c'],label='spatial FVM',color='#174c6b')
    axes[1].plot(z['heldout_times_s'],z['heldout_prediction_c'],'--',label='fitted RC',color='#b34e29')
    axes[1].set(xlabel='time (s)',ylabel='mean temperature (°C)');axes[1].legend(frameon=False)
    for ax in axes:ax.grid(alpha=.2)
    save(fig,'physics_validation_article')
    rows=list(csv.DictReader((ROOT/'results/raw/experiments/exp-20261027T135345Z-7afca8/metrics.csv').open()))
    fig,ax=plt.subplots(figsize=(3.5,2.6),layout='constrained')
    for name,color in [('bangbang','#a84e2b'),('pi','#2c608a'),('ffpi','#168371')]:
        group=[r for r in rows if r['controller']==name]
        for status,marker in [('ok','o'),('failed','x')]:
            r=[p for p in group if (p['status']=='ok')==(status=='ok')]
            ax.scatter([float(p['rmse_c']) for p in r],[float(p['energy_total_j'])*1e6 for p in r],s=14,marker=marker,color=color,alpha=.65)
        ax.scatter([],[],s=14,color=color,label=name.upper())
    ax.set(xlabel='hold RMSE (°C)',ylabel='heater energy (µJ)');ax.legend(frameon=False);ax.grid(alpha=.2);save(fig,'experiment_energy_article')
    cases=list(dict.fromkeys(r['scenario_id'] for r in rtl['evaluation']));x=np.arange(len(cases))
    fig,ax=plt.subplots(figsize=(3.5,2.6),layout='constrained')
    for shift,label,color in [(-.18,'baseline','#8395a5'),(.18,'retuned','#176e7d')]:
        vals=[next(r['rmse_hold_c'] for r in rtl['evaluation'] if r['scenario_id']==c and r['study_label']==label) for c in cases]
        ax.bar(x+shift,vals,.34,label=label,color=color)
    ax.axhline(2,color='#a54c2b',ls='--',lw=1);ax.set_xticks(x,['52→62','57→67','cold52','warm57','old55']);ax.set(ylabel='hold RMSE (°C)',ylim=(0,3.4));ax.legend(frameon=False,ncol=2);ax.grid(axis='y',alpha=.2);save(fig,'rtl_retuning_v2')
    from src.models.geometry_surrogate import geometry_features as features
    run=ROOT/geometry['run'];rows=list(csv.DictReader((run/'steady.csv').open()));coef=np.load(run/'surrogate.npz')['coefficients']
    test=[{k:(v if k in ['id','split'] else float(v)) for k,v in r.items()} for r in rows if r['split']=='test']
    true=[r['mean_c'] for r in test];pred=[float(features(r,r['duty'])@coef[:,0]) for r in test]
    fig,axes=plt.subplots(2,1,figsize=(3.5,3.9),layout='constrained')
    axes[0].scatter(true,pred,s=17,color='#176e7d');lo=min(true+pred);hi=max(true+pred);axes[0].plot([lo,hi],[lo,hi],'--',color='#777',lw=1)
    axes[0].set(xlabel='held-out FVM mean (°C)',ylabel='quadratic prediction (°C)');axes[0].grid(alpha=.2)
    for r in geometry['refined_candidates']:
        if r['status']!='solved':continue
        axes[1].scatter(r['power_w']*1e6,r['roi_std_c'],s=30,color='#176e7d')
        axes[1].annotate(r['id'],(r['power_w']*1e6,r['roi_std_c']),xytext=(4,5),textcoords='offset points',fontsize=8)
    axes[1].set(xlabel='refined power at 55°C mean (µW)',ylabel='central-region std. (°C)');axes[1].margins(.25);axes[1].grid(alpha=.2);save(fig,'geometry_study')

def markdown(rtl,geo):
    selection=rtl['selected'];text=(ROOT/'docs/article.template.md').read_text(encoding='utf-8')
    selection_text=f"Training selects Kp={selection['kp_q14']}/16384 and Ki={selection['ki_per_sample_q14']}/16384 per sample, with mean training RMSE {selection['mean_training_rmse_c']:.3f} °C. The original configuration remains archived and unchanged."
    table=['| Case | Baseline RMSE (°C) | Retuned RMSE (°C) | Evaluation role |','|---|---:|---:|---|']
    for case in dict.fromkeys(r['scenario_id'] for r in rtl['evaluation']):
        a,b=[next(r for r in rtl['evaluation'] if r['scenario_id']==case and r['study_label']==label) for label in ['baseline','retuned']]
        table.append(f"| {case.replace('_',' ')} | {a['rmse_hold_c']:.3f} | {b['rmse_hold_c']:.3f} | {'Observed regression' if a['previously_observed'] else 'New evaluation'} |")
    stats=geo['surrogate']['mean_c']
    description=f"All {geo['operating_points']} operating points solved with no recorded solver failures. Maximum electrical and thermal balance residuals are {geo['max_power_balance_rel']:.2e} and {geo['max_thermal_balance_rel']:.2e}. On the nine held-out geometries, temperature prediction has median absolute error {stats['median_abs_error']:.3f} °C and worst absolute error {stats['worst_abs_error']:.3f} °C. This error limits surrogate-only selection; final candidates require direct spatial solves. Two points lie on the discrete training front and are refined."
    gt=['| Candidate (width/pitch/anchor, µm) | Refined mean (°C) | Power (µW) | Central std. (°C) | Warmup to 54°C (ms) |','|---|---:|---:|---:|---:|']
    for r in geo['refined_candidates']:
        if r['status']=='solved':gt.append(f"| {r['id']} ({r['heater_width_um']}/{r['heater_pitch_um']}/{r['anchor_width_um']}) | {r['mean_c']:.3f} | {r['power_w']*1e6:.3f} | {r['roi_std_c']:.4f} | {r['warmup_to_target_minus_1c_s']*1e3:.0f} |")
    for key,value in {'RTL_SELECTION':selection_text,'RTL_TABLE':'\n'.join(table),'GEOMETRY_SUMMARY':description,'GEOMETRY_TABLE':'\n'.join(gt),'GEOMETRY_RUN':geo['run']}.items():text=text.replace('{{'+key+'}}',value)
    assert '{{' not in text,'Unresolved article field'
    (ROOT/'README.md').write_text(text,encoding='utf-8',newline='\n')
    article_text=re.sub(r'\]\((?!https?://|#)([^)]+)\)',lambda m: '](../'+m.group(1)+')',text)
    (OUT/'thermobridge_article.md').write_text(article_text,encoding='utf-8')
    return text

def pdf(text):
    font_dir=Path('C:/Windows/Fonts')
    if not font_dir.exists():
        import matplotlib.font_manager as fm
        serif=Path(fm.findfont('DejaVu Serif'));font_dir=serif.parent
        paths=[serif,font_dir/'DejaVuSerif-Bold.ttf',font_dir/'DejaVuSerif-Italic.ttf',font_dir/'DejaVuSerif-BoldItalic.ttf']
    else:paths=[font_dir/n for n in ['times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf']]
    for name,path in zip(['Article','Article-Bold','Article-Italic','Article-BoldItalic'],paths):pdfmetrics.registerFont(TTFont(name,str(path)))
    pdfmetrics.registerFontFamily('Article',normal='Article',bold='Article-Bold',italic='Article-Italic',boldItalic='Article-BoldItalic')
    width=250.;styles={
        'body':ParagraphStyle('body',fontName='Article',fontSize=9.8,leading=11.5,spaceAfter=5,alignment=4,splitLongWords=1),
        'h1':ParagraphStyle('h1',fontName='Article',fontSize=10,leading=12.2,spaceBefore=10,spaceAfter=7,alignment=1,keepWithNext=True),
        'h2':ParagraphStyle('h2',fontName='Article-Italic',fontSize=10,leading=12,spaceBefore=6,spaceAfter=5,keepWithNext=True),
        'small':ParagraphStyle('small',fontName='Article',fontSize=8.3,leading=10,spaceAfter=5,splitLongWords=1),
        'caption':ParagraphStyle('caption',fontName='Article',fontSize=8.4,leading=10,spaceAfter=8),
        'tablecaption':ParagraphStyle('tablecaption',fontName='Article',fontSize=8.4,leading=10,spaceAfter=5,keepWithNext=True),
        'code':ParagraphStyle('code',fontName='Courier',fontSize=6.8,leading=8.3,spaceBefore=4,spaceAfter=7),
    }
    def inline(s):
        s=escape(s.replace('—','-').replace('–','-').replace('−','-'))
        def link(m):
            label,target=m.groups();url=target if target.startswith('http') else 'https://github.com/aminemons/ThermoBridge/blob/main/'+quote(target)
            return '<a href="'+escape(url,quote=True)+'" color="#111111">'+label+'</a>'
        s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,s)
        s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s);s=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',s)
        s=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8">\1</font>',s)
        return s
    story=[NextPageTemplate('body')];lines=text.splitlines();i=0;pending_caption=None
    while i<len(lines):
        line=lines[i].strip()
        if line.startswith('<details>'):break
        if not line or line.startswith('# ') or line.startswith('**Technical report') or line.startswith('**Authors:**') or line.startswith('[Two-column article]') or line.startswith('Editorial structure follows'):
            i+=1;continue
        if line.startswith('## '):story.append(Paragraph(inline(line[3:]).upper(),styles['h1']));i+=1;continue
        if line.startswith('### '):story.append(Paragraph(inline(line[4:]),styles['h2']));i+=1;continue
        if line.startswith('$$'):
            equation_lines=[]
            if line=='$$':
                i+=1
                while i<len(lines) and lines[i].strip()!='$$':
                    equation_lines.append(lines[i].strip());i+=1
                if i>=len(lines):raise ValueError('Unclosed display equation')
                i+=1
            elif line.endswith('$$') and len(line)>4:
                equation_lines.append(line[2:-2]);i+=1
            else:
                equation_lines.append(line[2:]);i+=1
                while i<len(lines):
                    part=lines[i].strip();i+=1
                    if part.endswith('$$'):
                        equation_lines.append(part[:-2]);break
                    equation_lines.append(part)
                else:raise ValueError('Unclosed display equation')
            markup=' '.join(equation_lines).strip()
            match=re.search(r'\\text\{\((\d+)\)\}',markup)
            if not match:match=re.search(r'\\tag\{(\d+)\}',markup)
            number=match.group(1) if match else ''
            equation=re.sub(r'\\tag\{\d+\}','',markup)
            equation=re.sub(r'^\\begin\{array\}\{lr\}\s*\\displaystyle\s*','',equation)
            equation=re.sub(r'\s*&\s*\\text\{\(\d+\)\}\s*\\end\{array\}\s*
            fig=plt.figure(figsize=(3.8,.55));fig.text(.01,.5,'$'+equation+'$',fontsize=9.5,va='center')
            temp=ROOT/'tmp/article';temp.mkdir(parents=True,exist_ok=True);path=temp/f'equation-{number or i}.png'
            fig.savefig(path,dpi=300,bbox_inches='tight',transparent=False);plt.close(fig)
            w,h=ImageReader(str(path)).getSize();scale=min((width-22)/w,40/h)
            table=Table([[Image(str(path),width=w*scale,height=h*scale),Paragraph('('+number+')' if number else '',styles['small'])]],colWidths=[width-22,22])
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            story.extend([table,Spacer(1,7)]);continue
        if line.startswith('!['):
            match=re.match(r'!\[(.*?)\]\((.*?)\)',line);path=ROOT/match.group(2);w,h=ImageReader(str(path)).getSize();scale=min(width/w,260/h)
            block=[Image(str(path),width=w*scale,height=h*scale),Spacer(1,4)];i+=1
            while i<len(lines) and not lines[i].strip():i+=1
            if i<len(lines) and lines[i].startswith('**Fig.'):
                block.append(Paragraph(inline(lines[i]),styles['caption']));i+=1
            story.append(KeepTogether(block));continue
        if line.startswith('|'):
            data=[]
            while i<len(lines) and lines[i].startswith('|'):
                row=[s.strip() for s in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',s.replace(' ','')) for s in row):data.append(row)
                i+=1
            cells=[[Paragraph(inline(s),styles['small']) for s in row] for row in data]
            count=len(data[0]);widths=[width/count]*count
            if count>=4:widths=[width*.31]+[width*.69/(count-1)]*(count-1)
            t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.6,colors.black),('LINEBELOW',(0,0),(-1,0),.4,colors.black),('LINEBELOW',(0,-1),(-1,-1),.6,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
            block=[t,Spacer(1,7)]
            if pending_caption is not None:
                block.insert(0,pending_caption);pending_caption=None
                while story and isinstance(story[-1],Paragraph) and story[-1].style.name in ['h1','h2']:
                    block.insert(0,story.pop())
            story.append(KeepTogether(block));continue
        if line.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.extend(textwrap.wrap(lines[i],width=57,replace_whitespace=False) or ['']);i+=1
            i+=1;story.append(Preformatted('\n'.join(code),styles['code']));continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','![','|','```','$$','<details>')):
            paragraph.append(lines[i].strip());i+=1
        value=' '.join(paragraph);style=styles['small'] if re.match(r'^\[\d+\]',value) else styles['body']
        if value.startswith('**Table '):
            pending_caption=Paragraph(inline(value),styles['tablecaption']);continue
        story.append(Paragraph(inline(value),style))
    def header(canvas,doc):
        canvas.setFont('Article',8);canvas.drawString(48,764,'THERMOBRIDGE - TECHNICAL REPORT, REVISION 2, OCTOBER 2026');canvas.drawRightString(564,29,str(doc.page))
    def first(canvas,doc):
        header(canvas,doc)
        title=Paragraph('ThermoBridge: Electrothermal Modelling and<br/>Fixed-Point Control of a Microhotplate',ParagraphStyle('title',fontName='Article',fontSize=21,leading=24,alignment=1))
        title.wrap(516,80);title.drawOn(canvas,48,695)
        canvas.setFont('Article',10);canvas.drawCentredString(306,677,'Amine Allab  |  Ishaq Kolla');canvas.setFont('Article-Italic',9);canvas.drawCentredString(306,663,'Research technical report | Not peer reviewed | 30 October 2026')
    doc=BaseDocTemplate(str(OUT/'thermobridge_article.pdf'),pagesize=(612,792),leftMargin=48,rightMargin=48,topMargin=50,bottomMargin=42,title='ThermoBridge: Electrothermal Modelling and Fixed-Point Control of a Microhotplate',author='Amine Allab; Ishaq Kolla')
    frames=lambda top:[Frame(48,42,width,top-42,id='left',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),Frame(314,42,width,top-42,id='right',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]
    doc.addPageTemplates([PageTemplate(id='first',frames=frames(643),onPage=first),PageTemplate(id='body',frames=frames(744),onPage=header)])
    doc.build(story)

def main():
    FIG.mkdir(parents=True,exist_ok=True);OUT.mkdir(exist_ok=True)
    rtl=json.loads((OUT/'rtl_study_v2.json').read_text());geometry=json.loads((OUT/'geometry_study.json').read_text())
    figures(rtl,geometry);text=markdown(rtl,geometry);pdf(text)
    paths=[ROOT/'docs/article.template.md',OUT/'rtl_study_v2.json',OUT/'geometry_study.json',ROOT/'outputs/physics/validation.json',OUT/'asic/summary.json',ROOT/'outputs/physics/steady_1um.npz',ROOT/'outputs/physics/transient_validation.npz',ROOT/'results/raw/experiments/exp-20261027T135345Z-7afca8/metrics.csv',ROOT/geometry['run']/'steady.csv',ROOT/geometry['run']/'surrogate.npz']
    images=[ROOT/p for p in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text)]
    (OUT/'article_manifest.json').write_text(json.dumps({'inputs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'outputs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'README.md',OUT/'thermobridge_article.pdf',*images]},'format':'Two-column technical report; IEEE-style structure, Times fonts and numbered references; not an IEEE publication'},indent=2)+'\n')
    print('Built README.md, article figures and reports/thermobridge_article.pdf')
if __name__=='__main__':main()
,'',equation)
            equation=equation.strip().rstrip('.')
            fig=plt.figure(figsize=(3.8,.55));fig.text(.01,.5,'$'+equation+'$',fontsize=9.5,va='center')
            temp=ROOT/'tmp/article';temp.mkdir(parents=True,exist_ok=True);path=temp/f'equation-{number or i}.png'
            fig.savefig(path,dpi=300,bbox_inches='tight',transparent=False);plt.close(fig)
            w,h=ImageReader(str(path)).getSize();scale=min((width-22)/w,40/h)
            table=Table([[Image(str(path),width=w*scale,height=h*scale),Paragraph('('+number+')' if number else '',styles['small'])]],colWidths=[width-22,22])
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            story.extend([table,Spacer(1,7)]);continue
        if line.startswith('!['):
            match=re.match(r'!\[(.*?)\]\((.*?)\)',line);path=ROOT/match.group(2);w,h=ImageReader(str(path)).getSize();scale=min(width/w,260/h)
            block=[Image(str(path),width=w*scale,height=h*scale),Spacer(1,4)];i+=1
            while i<len(lines) and not lines[i].strip():i+=1
            if i<len(lines) and lines[i].startswith('**Fig.'):
                block.append(Paragraph(inline(lines[i]),styles['caption']));i+=1
            story.append(KeepTogether(block));continue
        if line.startswith('|'):
            data=[]
            while i<len(lines) and lines[i].startswith('|'):
                row=[s.strip() for s in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',s.replace(' ','')) for s in row):data.append(row)
                i+=1
            cells=[[Paragraph(inline(s),styles['small']) for s in row] for row in data]
            count=len(data[0]);widths=[width/count]*count
            if count>=4:widths=[width*.31]+[width*.69/(count-1)]*(count-1)
            t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.6,colors.black),('LINEBELOW',(0,0),(-1,0),.4,colors.black),('LINEBELOW',(0,-1),(-1,-1),.6,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
            block=[t,Spacer(1,7)]
            if pending_caption is not None:
                block.insert(0,pending_caption);pending_caption=None
                while story and isinstance(story[-1],Paragraph) and story[-1].style.name in ['h1','h2']:
                    block.insert(0,story.pop())
            story.append(KeepTogether(block));continue
        if line.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.extend(textwrap.wrap(lines[i],width=57,replace_whitespace=False) or ['']);i+=1
            i+=1;story.append(Preformatted('\n'.join(code),styles['code']));continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','![','|','```','$$','<details>')):
            paragraph.append(lines[i].strip());i+=1
        value=' '.join(paragraph);style=styles['small'] if re.match(r'^\[\d+\]',value) else styles['body']
        if value.startswith('**Table '):
            pending_caption=Paragraph(inline(value),styles['tablecaption']);continue
        story.append(Paragraph(inline(value),style))
    def header(canvas,doc):
        canvas.setFont('Article',8);canvas.drawString(48,764,'THERMOBRIDGE - TECHNICAL REPORT, REVISION 2, OCTOBER 2026');canvas.drawRightString(564,29,str(doc.page))
    def first(canvas,doc):
        header(canvas,doc)
        title=Paragraph('ThermoBridge: Electrothermal Modelling and<br/>Fixed-Point Control of a Microhotplate',ParagraphStyle('title',fontName='Article',fontSize=21,leading=24,alignment=1))
        title.wrap(516,80);title.drawOn(canvas,48,695)
        canvas.setFont('Article',10);canvas.drawCentredString(306,677,'Amine Allab  |  Ishaq Kolla');canvas.setFont('Article-Italic',9);canvas.drawCentredString(306,663,'Research technical report | Not peer reviewed | 30 October 2026')
    doc=BaseDocTemplate(str(OUT/'thermobridge_article.pdf'),pagesize=(612,792),leftMargin=48,rightMargin=48,topMargin=50,bottomMargin=42,title='ThermoBridge: Electrothermal Modelling and Fixed-Point Control of a Microhotplate',author='Amine Allab; Ishaq Kolla')
    frames=lambda top:[Frame(48,42,width,top-42,id='left',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),Frame(314,42,width,top-42,id='right',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]
    doc.addPageTemplates([PageTemplate(id='first',frames=frames(643),onPage=first),PageTemplate(id='body',frames=frames(744),onPage=header)])
    doc.build(story)

def main():
    FIG.mkdir(parents=True,exist_ok=True);OUT.mkdir(exist_ok=True)
    rtl=json.loads((OUT/'rtl_study_v2.json').read_text());geometry=json.loads((OUT/'geometry_study.json').read_text())
    figures(rtl,geometry);text=markdown(rtl,geometry);pdf(text)
    paths=[ROOT/'docs/article.template.md',OUT/'rtl_study_v2.json',OUT/'geometry_study.json',ROOT/'outputs/physics/validation.json',OUT/'asic/summary.json',ROOT/'outputs/physics/steady_1um.npz',ROOT/'outputs/physics/transient_validation.npz',ROOT/'results/raw/experiments/exp-20261027T135345Z-7afca8/metrics.csv',ROOT/geometry['run']/'steady.csv',ROOT/geometry['run']/'surrogate.npz']
    images=[ROOT/p for p in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text)]
    (OUT/'article_manifest.json').write_text(json.dumps({'inputs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'outputs':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'README.md',OUT/'thermobridge_article.pdf',*images]},'format':'Two-column technical report; IEEE-style structure, Times fonts and numbered references; not an IEEE publication'},indent=2)+'\n')
    print('Built README.md, article figures and reports/thermobridge_article.pdf')
if __name__=='__main__':main()
