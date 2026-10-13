import bpy,sys,os
from mathutils import Vector
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
from whitebox_world.scene import build
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
# Close-up verifies editable segmented actors visually, without buildings occluding them.
s=build({'biome':'grassland','size':40,'trees':0,'actors':[{'name':'Walker','kind':'person','speed':1.4,'offset':8,'path':[[-10,-4,0],[10,-4,0]]},{'name':'Walker_Fast','kind':'person','speed':2.2,'offset':14,'path':[[-10,-4,0],[10,-4,0]]},{'name':'Car','kind':'vehicle','speed':6,'offset':10,'path':[[-10,0,0],[10,0,0]]}]})
s.camera.location=(11,-19,12);s.camera.rotation_euler=(Vector((0,-2,1))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.ortho_scale=16
s.cycles.samples=64;s.render.resolution_x=1100;s.render.resolution_y=700;s.render.filepath=ROOT+'/artifacts/actors_detail.png';bpy.ops.render.render(write_still=True)
print('WHITEBOX_VARIANTS_OK')
