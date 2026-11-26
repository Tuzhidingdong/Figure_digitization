import csv
from pathlib import Path
B=Path(__file__).parent
rows={r['component_id']:r for r in csv.DictReader(open(B/'candidate_component_catalog.csv',encoding='utf-8'))}
for cid in ('F001','F005','F008','F015','F020','F062'):
    r=rows.get(cid)
    if not r: continue
    print(cid,r['classification'],r['family'],'bbox',r['bbox'],'area',r['area'],'paths',r['path_count'],
          'junction',r['junction_count'],'reasons',r['classification_reasons'])
