"""Rebuild the real mapped district with architectural facade families (v0.4)."""
import collections
import json
import pathlib
import sys
import bpy
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from whitebox_world.scene import build
from whitebox_world.detail_runtime import update_details
from whitebox_world.export import export_glb
OUT=ROOT/'artifacts/facade_v04';OUT.mkdir(parents=True,exist_ok=True)
config=json.loads((ROOT/'configs/shibuya.json').read_text())
config.update(map_file=str(ROOT/'configs/shibuya.geojson'),lod_mode='ALL')
s=build(config)
s.cycles.samples=96;s.cycles.use_denoising=False
s.render.resolution_x=1600;s.render.resolution_y=1140;s.render.resolution_percentage=100
buildings=[o for o in bpy.data.collections['WW_Buildings'].all_objects if o.get('ww_kind')=='building']
assert len(buildings)==105 and all(o.get('osm_id') for o in buildings)
summary={'building_count':len(buildings),'styles':dict(collections.Counter(o.get('ww_facade_style','unknown') for o in buildings)),
         'style_provenance':dict(collections.Counter(o.get('ww_facade_style_source','unknown') for o in buildings)),
         'openings':sum(o.get('ww_facade_openings',0) for o in buildings),
         'source_attribution':s.get('ww_map_attribution',''),'actors':[o.name for o in s.objects if o.get('ww_actor')]}
(OUT/'shibuya_facade_manifest.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
s.camera.data.type='ORTHO';s.camera.data.ortho_scale=426
s.camera.location=(237,-279,234);s.camera.rotation_euler=(Vector((0,0,3))-s.camera.location).to_track_quat('-Z','Y').to_euler()
s['ww_lod_mode']='ALL';update_details(s)
s.render.filepath=str(OUT/'shibuya_facade_overview.png');bpy.ops.render.render(write_still=True)
s.camera.data.type='PERSP';s.camera.data.lens=27;s.camera.data.clip_start=.1;s.camera.data.clip_end=1200
s.camera.location=(-8,5,7);s.camera.rotation_euler=(Vector((-55,54,14))-s.camera.location).to_track_quat('-Z','Y').to_euler()
s['ww_lod_mode']='COARSE';update_details(s)
s.render.filepath=str(OUT/'shibuya_facade_coarse.png');bpy.ops.render.render(write_still=True)
s['ww_lod_mode']='AUTO';s['ww_lod_distance']=100;update_details(s)
s.render.filepath=str(OUT/'shibuya_facade_street.png');bpy.ops.render.render(write_still=True)
# Portable relative map reference from artifacts/facade_v04 to configs.
config['map_file']='//../../configs/shibuya.geojson';s['ww_config']=json.dumps(config,ensure_ascii=False)
if hasattr(s,'ww_map_file'):s.ww_map_file=config['map_file']
s['ww_export_detail']='ALL';export_glb(str(OUT/'shibuya_facades.glb'),s)
s['ww_export_detail']='CURRENT'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shibuya_facades.blend'),compress=True)
print('SHIBUYA_FACADES_OK',json.dumps(summary))
