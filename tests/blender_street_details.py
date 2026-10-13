"""Run: blender -b --factory-startup --python tests/blender_street_details.py"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bpy
from whitebox_world.street_details import add_street_details
cols={}
for name in ('Trees','RoadMarkings','UtilityPoles','TrafficLights'):
    col=bpy.data.collections.new('TEST_'+name); bpy.context.scene.collection.children.link(col); cols[name]=col
roads=[{'points':[[-80,0],[80,0]],'width':8,'osm_id':'12'}, {'points':[[0,-80],[0,80]],'width':8,'osm_id':'34'}]
meta=add_street_details(roads,[],cols,{'seed':42})
assert meta['counts']['traffic_lights']>0,meta
assert all(o.type=='MESH' for c in cols.values() for o in c.objects)
assert all(o.get('ww_feature') for c in cols.values() for o in c.objects)
assert all(o.get('ww_detail') for o in cols['RoadMarkings'].objects)
assert any(not o.get('ww_detail') for o in cols['Trees'].objects)
assert len({o.data.name for o in cols['Trees'].objects})==1
for c in cols.values():
    for o in c.objects:
        assert len(o.data.vertices)>0
        assert not o.data.validate(verbose=True), o.name
print('STREET_SMOKE_OK',meta)
