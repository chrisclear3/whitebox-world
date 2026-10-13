"""Verify a real Shibuya artifact, strict import failure, animation and GLB round-trip."""
import bpy,sys,json,pathlib,struct,math
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from whitebox_world.scene import build
from whitebox_world.export import export_glb
from whitebox_world.runtime import install_handler,update_actors
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'artifacts/shibuya.blend'))
s=bpy.context.scene;install_handler()
assert len(bpy.data.collections['WW_Buildings'].objects)==105
assert all(o.get('osm_id') for o in bpy.data.collections['WW_Buildings'].objects)
assert not bpy.data.objects.get('Block_Building') and not bpy.data.objects.get('Main_Road_0')
assert 'OpenStreetMap' in s['ww_map_attribution']
assert bpy.data.texts.get('WW_MapSource.geojson')
for cfg in ({'require_real_map':True},{'require_real_map':True,'map_file':str(ROOT/'configs/demo_city.geojson'),'coordinate_system':'local'}):
    try:build(cfg)
    except ValueError:pass
    else:raise AssertionError('Strict real map accepted absent/synthetic source')
assert len(bpy.data.collections['WW_Buildings'].objects)==105
actors=[o for o in s.objects if o.get('ww_actor')];assert len(actors)==2
s.frame_set(1);p={o.name:o.location.copy() for o in actors};s.frame_set(25)
assert all((o.location-p[o.name]).length>1 for o in actors)
s.frame_set(1)
g=bpy.data.objects['Ground'];g['map_attribution']=s['ww_map_attribution'];g['map_license']='https://opendatacommons.org/licenses/odbl/1-0/';g['map_limitations']=s['ww_map_limitations']
export_glb(str(ROOT/'artifacts/shibuya.glb'),s)
s.render.resolution_percentage=100;s.cycles.samples=64;s.render.filepath=str(ROOT/'artifacts/shibuya.png')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'artifacts/shibuya.blend'))
bpy.ops.render.render(write_still=True)
raw=(ROOT/'artifacts/shibuya.glb').read_bytes();length,kind=struct.unpack_from('<II',raw,12);gltf=json.loads(raw[20:20+length])
assert any('OpenStreetMap' in n.get('extras',{}).get('map_attribution','') for n in gltf['nodes'])
assert gltf.get('animations')
animated={gltf['nodes'][c['target']['node']]['name'] for a in gltf['animations'] for c in a['channels']}
assert {'Shibuya_Walker','Shibuya_Car'} <= animated
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(ROOT/'artifacts/shibuya.glb'))
assert len(bpy.data.actions)>=1
s=bpy.context.scene;s.frame_set(1);before={name:bpy.data.objects[name].location.copy() for name in ('Shibuya_Walker','Shibuya_Car')};s.frame_set(25)
assert all((bpy.data.objects[name].location-position).length>1 for name,position in before.items())
print('SHIBUYA_INTEGRATION_OK: 105 real buildings, provenance, strict failure before deletion, actor motion, attributed GLB, reimport')
