import bpy,json,os
from .runtime import bake,update_actors

def export_glb(filepath,scene):
    bake(scene)
    bpy.ops.object.select_all(action='DESELECT')
    for o in scene.objects:
        if any(c.name.startswith('WW_') for c in o.users_collection) and not o.hide_render and o.name!='WW_Fog':o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(filepath),export_format='GLB',use_selection=True,export_animations=True,export_animation_mode='ACTIVE_ACTIONS',export_frame_range=True,export_force_sampling=True)


def export_poses(filepath,scene):
    old=scene.frame_current;frames=[]
    for f in range(scene.frame_start,scene.frame_end+1):
        scene.frame_set(f);update_actors(scene)
        frames.append({'frame':f,'time_seconds':(f-scene.frame_start)/(scene.render.fps/scene.render.fps_base),'actors':[{'name':o.name,'kind':o['ww_kind'],'position_m':list(o.location),'heading_radians':o.rotation_euler.z,'speed_mps':o['ww_speed']} for o in scene.objects if o.get('ww_actor')]})
    scene.frame_set(old)
    with open(filepath,'w') as out:json.dump({'units':'meters','up_axis':'Z','frames':frames},out,indent=2)
