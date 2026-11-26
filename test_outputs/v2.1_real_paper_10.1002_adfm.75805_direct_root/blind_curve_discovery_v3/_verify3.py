import json, csv, re, pathlib
from PIL import Image
B=pathlib.Path(__file__).parent
d=json.load(open(B/'discovery_diagnostics.json',encoding='utf-8'))
print('counts',d['classification_counts'],'fragments',d['fragment_count'],'edges',d['association_edge_count'])
print('global',{k:v for k,v in d['global_solution'].items() if k!='chains'})
for ch in d['global_solution']['chains']:
    if len(ch)>1: print('  linked chain',ch)
print('competing:')
for r in d['competing_solutions']:
    print('  ',r['solution_id'],'raw',r['total_cost'],'flow',r['flow_objective'],'margin',r['margin_vs_base'],r['confidence'],r['constraint'])
print('junction hypotheses',len(d['junction_hypotheses']))
for j in d['junction_hypotheses'][:5]: print('  ',j['hypothesis_id'],j.get('port_count'),j.get('best_pairing_cost'),j.get('competing_margin'),j['confidence'])
print('audit',{k:v for k,v in d['source_pixel_audit'].items() if k!='excluded_coordinates'})
for f in ('candidate_component_catalog.csv','non_data_graphic_candidates.csv','trajectory_hypotheses.csv','global_assignment.csv','competing_assignments.csv','source_pixel_audit.csv','discovered_points.csv'):
    rows=list(csv.DictReader(open(B/f,encoding='utf-8')))
    print(f,len(rows),'rows')
t=(B/'index.html').read_text(encoding='utf-8')
print('external refs',re.findall(r'https?://[^"\' ]+',t)[:3],'scripts',t.count('<script'),'images',t.count('data:image/png;base64,'))
for p in sorted(B.glob('*.png')):
    im=Image.open(p); print(p.name,im.size,im.mode)
