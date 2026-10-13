import bpy,sys,os,json,math,tempfile
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
import whitebox_world
from whitebox_world.scene import build
from whitebox_world.runtime import update_actors,update_environment,bake
from whitebox_world.export import export_glb,export_poses
whitebox_world.register()
assert hasattr(bpy.types.Scene,'ww_biome')
config={'biome':'mixed','size':80,'duration':3,'fps':24,'actors':[{'name':'TestPerson','kind':'person','speed':2,'loop':False,'path':[[0,0,0],[40,0,0]]},{'name':'TestCar','kind':'vehicle','speed':6,'path':[[0,3,0],[80,3,0]]}]}
s=build(config)
assert s.ww_biome=='mixed' and s.ww_size==80
terrain=bpy.data.objects['Ground'];terrain['custom_edit']='keep'
try:build({'map_file':'/definitely_missing/whitebox.geojson'})
except FileNotFoundError:pass
else:raise AssertionError('Missing map should fail')
assert bpy.data.objects['Ground']['custom_edit']=='keep'
a=bpy.data.objects['TestPerson'];car=bpy.data.objects['TestCar'];s.frame_set(25)
assert abs(a.location.x-2)<1e-5 and abs(car.location.x-6)<1e-5
s.camera.location.x+=20;update_actors(s);assert abs(a.location.x-2)<1e-5
# Two independently editable speeds; baked animation must not override live controls.
bake(s);a['ww_speed']=3;s.frame_set(49);assert abs(a.location.x-6)<1e-5,(a.location.x,'speed after bake');assert abs(car.location.x-12)<1e-5
# Editable path geometry and sun/weather.
p=bpy.data.objects[a['ww_path_name']];p.data.splines[0].points[1].co=(0,40,0,1);update_actors(s);assert abs(a.location.y-6)<1e-5
for weather in ('clear','overcast','fog','rain'):
    s['ww_active_weather']=weather;update_environment(s)
    if weather=='fog':assert bpy.data.objects.get('WW_Fog')
    if weather=='rain':assert len(bpy.data.collections['WW_Weather'].objects)==240
# Preserve unrelated content and deterministic biome builds.
custom=bpy.data.objects.new('User_Content',None);s.collection.objects.link(custom)
for biome in ('city','beach','forest','grassland'):
    s=build({'biome':biome,'size':80,'duration':1,'fps':12});assert bpy.data.objects.get('User_Content')
    assert len(bpy.data.collections['WW_Actors'].objects)>10
s=build(config);out=os.path.join(ROOT,'artifacts','integration');os.makedirs(out,exist_ok=True)
export_glb(out+'/test.glb',s);export_poses(out+'/test.poses.json',s);bake(s);bpy.ops.wm.save_as_mainfile(filepath=out+'/test.blend')
assert os.path.getsize(out+'/test.glb')>1000
poses=json.load(open(out+'/test.poses.json'));assert len(poses['frames'])==72
# Re-import GLB verifies actual exporter structure/animation.
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=out+'/test.glb');assert len(bpy.data.actions)>0;assert bpy.data.objects.get('TestPerson')
whitebox_world.unregister()
print('WHITEBOX_INTEGRATION_OK: all biomes, independent motion, camera invariance, live speed after bake, path edits, 4 weather states, addon registration, GLB reimport, poses')
