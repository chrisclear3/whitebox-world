"""blender -b --python scripts/build_scene.py -- --config configs/mixed.json --output artifacts/mixed.blend --render --glb --poses"""
import sys,os,json,argparse
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
import bpy
from whitebox_world.scene import build
from whitebox_world.runtime import bake
from whitebox_world.export import export_glb,export_poses
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);p.add_argument('--render',action='store_true');p.add_argument('--glb',action='store_true');p.add_argument('--poses',action='store_true');p.add_argument('--quick',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);config=json.load(open(a.config))
if config.get('map_file') and not os.path.isabs(config['map_file']):config['map_file']=os.path.abspath(os.path.join(os.path.dirname(a.config),config['map_file']))
# Factory objects are removed only by CLI. Add-on preserves non-generated user objects.
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
s=build(config);base=os.path.splitext(os.path.abspath(a.output))[0];os.makedirs(os.path.dirname(base),exist_ok=True)
bake(s)
if a.glb:export_glb(base+'.glb',s)
if a.poses:export_poses(base+'.poses.json',s)
if a.quick:s.render.resolution_percentage=60;s.cycles.samples=12
bpy.ops.wm.save_as_mainfile(filepath=base+'.blend')
if a.render:s.render.filepath=base+'.png';bpy.ops.render.render(write_still=True)
print('WHITEBOX_BUILD_OK',base)
