import csv, json
from pathlib import Path
B=Path(__file__).parent
rows=list(csv.DictReader(open(B/'candidate_component_catalog.csv',encoding='utf-8')))
for r in rows:
    if r['classification']=='DATA_PATH_CANDIDATE':
        print('DATA',r['component_id'],r['family'],'bbox',r['bbox'],'area',r['area'],
              'fill',r['fill_ratio'],'solid',r['solidity'],'skelratio',r['skeleton_to_area'],
              'dir',r['direction_consistency'],'paths',r['path_count'],'endpoint',r['endpoint_count'],
              'junction',r['junction_count'])
print('--- ambiguous with longest bbox')
amb=[r for r in rows if r['classification']=='AMBIGUOUS_REVIEW']
amb.sort(key=lambda r:-(r['width']*r['height']))
for r in amb[:12]:
    print('AMB',r['component_id'],r['family'],r['bbox'],'area',r['area'],'fill',r['fill_ratio'],
          'dir',r['direction_consistency'],'paths',r['path_count'],'rowal',r['row_aligned_neighbours'])
print('--- non-data sample')
nd=[r for r in rows if r['classification']=='NON_DATA_GRAPHIC_CANDIDATE']
for r in nd[:8]:
    print('ND',r['component_id'],r['bbox'],'w/h',r['width'],r['height'],'fill',r['fill_ratio'],
          'solid',r['solidity'],'rect',r['rectangularity'],'rowal',r['row_aligned_neighbours'],r['classification_reasons'])
