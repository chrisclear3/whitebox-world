"""Render the editable Shibuya detail comparison from real mapped streets."""
import bpy,sys,pathlib,json
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from whitebox_world.detail_runtime import install,update_details
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'artifacts/shibuya_details.blend'))
s=bpy.context.scene;install();s.cycles.samples=64;s.render.resolution_percentage=100
# Tiny bounded road offsets avoid coplanar z-fighting without burying paint.
for i,o in enumerate(bpy.data.collections['WW_Roads'].objects):o.location.z=.025+.02*i/(1000+i)
s.camera.data.type='ORTHO';s.camera.data.ortho_scale=426
s.camera.location=(237,-279,234);s.camera.rotation_euler=(Vector((0,0,3))-s.camera.location).to_track_quat('-Z','Y').to_euler()
print('DETAIL_COUNTS',s.get('ww_street_details'))
print('OBJECTS',len(s.objects),'MESH_VERTS',sum(len(o.data.vertices) for o in s.objects if o.type=='MESH'))
s['ww_lod_mode']='ALL';update_details(s)
s.render.filepath=str(ROOT/'artifacts/shibuya_details_overview.png');bpy.ops.render.render(write_still=True)
s.camera.data.type='PERSP';s.camera.data.lens=27;s.camera.data.clip_start=.1;s.camera.data.clip_end=1200
s.camera.location=(-8,5,7);s.camera.rotation_euler=(Vector((-55,54,14))-s.camera.location).to_track_quat('-Z','Y').to_euler()
s['ww_lod_mode']='COARSE';update_details(s)
s.render.filepath=str(ROOT/'artifacts/shibuya_street_before.png');bpy.ops.render.render(write_still=True)
s['ww_lod_mode']='AUTO';s['ww_lod_distance']=100;update_details(s)
s.render.filepath=str(ROOT/'artifacts/shibuya_street_details.png');bpy.ops.render.render(write_still=True)
# Save the useful near-street working camera with portable map configuration.
config=json.loads(s['ww_config']);config['map_file']='//../configs/shibuya.geojson';s['ww_config']=json.dumps(config,ensure_ascii=False)
if hasattr(s,'ww_map_file'):s.ww_map_file=config['map_file']
from whitebox_world.export import export_glb
s['ww_export_detail']='ALL';export_glb(str(ROOT/'artifacts/shibuya_details.glb'),s)
s['ww_export_detail']='CURRENT'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'artifacts/shibuya_details.blend'),compress=True)
s.camera.location=(95,-12,7);s.camera.rotation_euler=(Vector((-15,8,12))-s.camera.location).to_track_quat('-Z','Y').to_euler()
s['ww_lod_mode']='ALL';update_details(s)
s.render.filepath=str(ROOT/'artifacts/shibuya_street_props.png');bpy.ops.render.render(write_still=True)
print('DETAIL_RENDERS_OK')
