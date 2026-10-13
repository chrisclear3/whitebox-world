"""Non-destructive detail visibility: collection LOD never edits artist meshes.

AUTO uses the active scene camera, not the editor view. FROZEN persists the
current per-group selection in the .blend and works without add-on handlers.
"""
import math
import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

FEATURES = {'facades':'Facades', 'trees':'Trees', 'road_markings':'RoadMarkings',
            'utility_poles':'UtilityPoles', 'traffic_lights':'TrafficLights'}
_BUSY = False


def setup(scene, config):
    for key in FEATURES:
        scene['ww_show_'+key] = bool(config.get('show_'+key, True))
    scene['ww_lod_mode'] = config.get('lod_mode', 'AUTO')
    scene['ww_lod_distance'] = float(config.get('lod_distance', 85))
    scene['ww_export_detail'] = config.get('export_detail', 'CURRENT')


def group_details(scene):
    """Put detail-only meshes in per-anchor collections below feature roots."""
    groups = {}
    for obj in list(scene.objects):
        if not obj.get('ww_detail'): continue
        feature = obj.get('ww_feature', 'facades')
        root = bpy.data.collections.get('WW_'+FEATURES.get(feature, 'Facades'))
        if root is None: continue
        anchor = obj.get('ww_lod_parent', '') or (obj.parent.name if obj.parent else obj.name)
        key = (feature, anchor)
        if key not in groups:
            col = bpy.data.collections.new('WW_LOD_'+anchor)
            root.children.link(col)
            col['ww_lod'] = True; col['ww_lod_anchor'] = anchor
            groups[key] = col
        for col in list(obj.users_collection): col.objects.unlink(obj)
        groups[key].objects.link(obj)


def _distance_to_bounds(camera, obj):
    if obj is None: return 0.0
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box] if obj.type == 'MESH' else [obj.matrix_world.translation]
    return math.sqrt(sum(max(min(p[i] for p in corners)-camera[i], 0, camera[i]-max(p[i] for p in corners))**2 for i in range(3)))


def update_details(scene, force=False):
    global _BUSY
    if _BUSY or not scene.get('ww_config'): return
    _BUSY = True
    try:
        for key, name in FEATURES.items():
            col = bpy.data.collections.get('WW_'+name)
            if col:
                hidden = not bool(scene.get('ww_show_'+key, True))
                if col.hide_viewport != hidden: col.hide_viewport = hidden
                if col.hide_render != hidden: col.hide_render = hidden
        mode = scene.get('ww_lod_mode', 'AUTO')
        if mode == 'FROZEN': return
        camera = scene.camera.matrix_world.translation if scene.camera else None
        radius = float(scene.get('ww_lod_distance',85))
        for col in bpy.data.collections:
            if not col.get('ww_lod'): continue
            hidden = mode == 'COARSE'
            if mode == 'AUTO' and camera is not None:
                hidden = _distance_to_bounds(camera, bpy.data.objects.get(col.get('ww_lod_anchor',''))) > radius
            if col.hide_viewport != hidden: col.hide_viewport = hidden
            if col.hide_render != hidden: col.hide_render = hidden
    finally:
        _BUSY = False


def freeze(scene):
    update_details(scene)
    scene['ww_lod_mode'] = 'FROZEN'


def object_render_visible(obj, scene):
    if obj.hide_render: return False
    def visit(col, hidden=False):
        hidden = hidden or col.hide_render
        if obj.name in col.objects and not hidden: return True
        return any(visit(child, hidden) for child in col.children)
    return visit(scene.collection)


@persistent
def details_depsgraph(scene, *args):
    update_details(scene)


@persistent
def details_frame(scene, *args):
    update_details(scene)


@persistent
def details_load(*args):
    update_details(bpy.context.scene)


@persistent
def details_render(scene, *args):
    update_details(scene)


def install():
    for name, fn in [('depsgraph_update_post',details_depsgraph),('frame_change_post',details_frame),('load_post',details_load),('render_pre',details_render)]:
        handlers = getattr(bpy.app.handlers,name)
        for old in list(handlers):
            if old.__module__ == __name__ and old.__name__ == fn.__name__: handlers.remove(old)
        handlers.append(fn)


def uninstall():
    for name in ('depsgraph_update_post','frame_change_post','load_post','render_pre'):
        handlers = getattr(bpy.app.handlers,name)
        for fn in list(handlers):
            if getattr(fn,'__module__','') == __name__: handlers.remove(fn)
