import bpy,json,os
from .runtime import bake,update_actors

def export_glb(filepath,scene):
    """Export exactly one fixed LOD shell, preserving editable scene state.

    glTF has no portable Blender collection/camera-distance visibility driver.
    CURRENT snapshots at the export frame before animation baking changes time.
    Artist object hide flags are never modified, including viewport-only flags.
    """
    from .detail_runtime import (update_details, object_render_visible,
                                 scene_collections, suspend_updates)
    view_layer = bpy.context.view_layer
    old_mode = scene.get('ww_lod_mode','AUTO')
    old_frame = scene.frame_current
    old_subframe = scene.frame_subframe
    old_selection = [obj for obj in view_layer.objects if obj.select_get()]
    old_active = view_layer.objects.active
    update_details(scene)
    collections = [(col, col.hide_viewport, col.hide_render)
                   for col in scene_collections(scene)]

    def layer_collections(layer):
        yield layer
        for child in layer.children:
            yield from layer_collections(child)
    layers = [(layer, layer.hide_viewport)
              for layer in layer_collections(view_layer.layer_collection)]
    choice = scene.get('ww_export_detail','CURRENT')
    try:
        if choice in ('ALL','COARSE'):
            scene['ww_lod_mode'] = choice
            update_details(scene)
        scene['ww_lod_mode'] = 'FROZEN'
        with suspend_updates():
            bake(scene)
            # Resolve render visibility before unlocking viewport collections.
            # This includes paired coarse shells and ancestor feature switches.
            selected = [obj for obj in scene.objects
                        if any(col.name.startswith('WW_') for col in obj.users_collection)
                        and object_render_visible(obj,scene) and obj.name != 'WW_Fog']
            # A render-visible coarse shell can be in a viewport-hidden group.
            # Unhide collections, never object hide_* flags, for selection only.
            # Explicit view-layer exclusions remain respected by membership.
            for col, _, _ in collections: col.hide_viewport = False
            for layer, _ in layers: layer.hide_viewport = False
            view_layer.update()
            for obj in view_layer.objects: obj.select_set(False)
            for obj in selected:
                if obj.name in view_layer.objects: obj.select_set(True)
            result = bpy.ops.export_scene.gltf(filepath=os.path.abspath(filepath),export_format='GLB',use_selection=True,export_extras=True,export_animations=True,export_animation_mode='ACTIVE_ACTIONS',export_frame_range=True,export_force_sampling=True)
            if result != {'FINISHED'}:
                raise RuntimeError('glTF export did not finish: ' + str(result))
    finally:
        with suspend_updates():
            # Restore selection while collections are still accessible, then
            # restore the saved frozen pair state before allowing handlers again.
            for obj in view_layer.objects: obj.select_set(False)
            for obj in old_selection:
                if obj.name in view_layer.objects: obj.select_set(True)
            view_layer.objects.active = old_active
            scene.frame_set(old_frame, subframe=old_subframe)
            scene['ww_lod_mode'] = old_mode
            for col, viewport, render in collections:
                col.hide_viewport = viewport
                col.hide_render = render
            for layer, viewport in layers: layer.hide_viewport = viewport
        update_details(scene)


def export_poses(filepath,scene):
    old=scene.frame_current;frames=[]
    for f in range(scene.frame_start,scene.frame_end+1):
        scene.frame_set(f);update_actors(scene)
        frames.append({'frame':f,'time_seconds':(f-scene.frame_start)/(scene.render.fps/scene.render.fps_base),'actors':[{'name':o.name,'kind':o['ww_kind'],'position_m':list(o.location),'heading_radians':o.rotation_euler.z,'speed_mps':o['ww_speed']} for o in scene.objects if o.get('ww_actor')]})
    scene.frame_set(old)
    with open(filepath,'w') as out:json.dump({'units':'meters','up_axis':'Z','frames':frames},out,indent=2)
