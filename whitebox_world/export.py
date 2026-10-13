import bpy,json,os
from .runtime import bake,update_actors

def export_glb(filepath,scene):
    """Export one fixed LOD snapshot, honoring feature and artist visibility.

    glTF has no portable Blender collection/camera-distance visibility driver.
    CURRENT snapshots at the export frame before animation baking changes time.
    """
    from .detail_runtime import update_details, object_render_visible
    old_mode=scene.get('ww_lod_mode','AUTO')
    old_frame=scene.frame_current
    old_selection=list(bpy.context.selected_objects)
    old_active=bpy.context.view_layer.objects.active
    update_details(scene)
    lods=[(c,c.hide_viewport,c.hide_render) for c in bpy.data.collections if c.get('ww_lod')]
    choice=scene.get('ww_export_detail','CURRENT')
    try:
        if choice in ('ALL','COARSE'):
            scene['ww_lod_mode']=choice;update_details(scene)
        scene['ww_lod_mode']='FROZEN'
        bake(scene)
        bpy.ops.object.select_all(action='DESELECT')
        # Temporarily unhide LOD collections in the viewport for selection only.
        # Render visibility remains the export authority.
        for c,_,_ in lods:c.hide_viewport=False
        for o in scene.objects:
            if any(c.name.startswith('WW_') for c in o.users_collection) and object_render_visible(o,scene) and o.name!='WW_Fog':o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=os.path.abspath(filepath),export_format='GLB',use_selection=True,export_extras=True,export_animations=True,export_animation_mode='ACTIVE_ACTIONS',export_frame_range=True,export_force_sampling=True)
    finally:
        scene.frame_set(old_frame)
        for c,viewport,render in lods:c.hide_viewport=viewport;c.hide_render=render
        scene['ww_lod_mode']=old_mode
        bpy.ops.object.select_all(action='DESELECT')
        for o in old_selection:
            if o.name in scene.objects:o.select_set(True)
        bpy.context.view_layer.objects.active=old_active
        update_details(scene)


def export_poses(filepath,scene):
    old=scene.frame_current;frames=[]
    for f in range(scene.frame_start,scene.frame_end+1):
        scene.frame_set(f);update_actors(scene)
        frames.append({'frame':f,'time_seconds':(f-scene.frame_start)/(scene.render.fps/scene.render.fps_base),'actors':[{'name':o.name,'kind':o['ww_kind'],'position_m':list(o.location),'heading_radians':o.rotation_euler.z,'speed_mps':o['ww_speed']} for o in scene.objects if o.get('ww_actor')]})
    scene.frame_set(old)
    with open(filepath,'w') as out:json.dump({'units':'meters','up_axis':'Z','frames':frames},out,indent=2)
