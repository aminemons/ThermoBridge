"""Real KLayout captures of routed GDS, not an illustrative chip rendering."""
from pathlib import Path
import json
import pya
ROOT=Path(__file__).resolve().parents[1]
gds=next((ROOT/'results/asic/mag_gds').glob('*.gds'))
out=ROOT/'docs/figures';out.mkdir(parents=True,exist_ok=True)
window=pya.Application.instance().main_window()
window.load_layout(str(gds),1)
view=window.current_view();view.add_missing_layers();view.max_hier();view.zoom_fit()
view.save_image(str(out/'routed_core.png'),1400,1100)
box=view.box()
cx,cy=box.center().x,box.center().y
detail=pya.DBox(cx-box.width()/10,cy-box.height()/10,cx+box.width()/10,cy+box.height()/10)
view.zoom_box(detail)
view.save_image(str(out/'routed_core_detail.png'),1400,1100)
(out/'gds_capture.json').write_text(json.dumps({'source_gds':str(gds.relative_to(ROOT)),'tool':'KLayout 0.30.12','full_view_um':str(box),'detail_view_um':str(detail),'description':'Actual generated layout. Not fabricated silicon.'},indent=2)+'\n')
view.zoom_fit()
