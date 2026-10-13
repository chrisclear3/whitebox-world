"""Animation driven by scene time, independently of camera movement."""
import bpy, math
from bpy.app.handlers import persistent
from .core import path_pose


def path_points(obj):
    return [tuple(obj.matrix_world @ p.co.xyz) for p in obj.data.splines[0].points]


def update_actors(scene):
    t=(scene.frame_current-scene.frame_start)/(scene.render.fps/scene.render.fps_base)
    for actor in scene.objects:
        if not actor.get('ww_actor'):continue
        curve=bpy.data.objects.get(actor.get('ww_path_name',''))
        if not curve:continue
        speed=max(0,float(actor.get('ww_speed',1.4)));distance=t*speed+float(actor.get('ww_offset',0))
        try:location,heading=path_pose(path_points(curve),distance,bool(actor.get('ww_loop',True)))
        except (ValueError,IndexError):continue
        actor.location=location;actor.rotation_euler.z=heading
        phase=distance*4.5+float(actor.get('ww_phase',0))
        for child in actor.children:
            if child.get('ww_limb'):child.rotation_euler.y=math.sin(phase)*.43*child['ww_limb'] if speed else 0
            if child.get('ww_wheel'):child.rotation_euler.y=distance/.4


def update_environment(scene):
    sun=bpy.data.objects.get('WW_Sun')
    weather=scene.get('ww_active_weather','clear')
    if sun:
        sun.rotation_euler=(math.radians(90-float(scene.get('ww_sun_elevation',35))),0,math.radians(float(scene.get('ww_sun_azimuth',135))))
        sun.data.energy={'clear':3,'overcast':.6,'fog':1,'rain':.45}.get(weather,3)
        sun.data.angle=math.radians(10 if weather=='clear' else 40)
    if scene.world and scene.world.use_nodes:
        bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.68,.78,.88,1);bg.inputs['Strength'].default_value=.55 if weather=='clear' else .8
    col=bpy.data.collections.get('WW_Weather')
    if not col:return
    for o in list(col.objects):bpy.data.objects.remove(o,do_unlink=True)
    if weather in ('fog','rain'):
        from .scene import cube, material
        import random
        size=json_size(scene)
        if weather=='fog':
            o=cube('WW_Fog',(0,0,20),(size,size,40),'ground',col)
            m=bpy.data.materials.get('WW_FogVolume') or bpy.data.materials.new('WW_FogVolume');m.use_nodes=True;n=m.node_tree.nodes;n.clear();out=n.new('ShaderNodeOutputMaterial');v=n.new('ShaderNodeVolumePrincipled');v.inputs['Density'].default_value=.012;m.node_tree.links.new(v.outputs['Volume'],out.inputs['Volume']);o.data.materials.clear();o.data.materials.append(m);o.display_type='WIRE'
        else:
            # Lightweight geometric rainfall preview. Not fluid simulation.
            rng=random.Random(int(scene.get('ww_seed',42)))
            for i in range(240):
                o=cube('Rain_Streak',(rng.uniform(-size/2,size/2),rng.uniform(-size/2,size/2),rng.uniform(1,22)),(.025,.025,.65),'water',col);o.rotation_euler.y=.18


def json_size(scene):
    import json
    return float(json.loads(scene.get('ww_config','{}')).get('size',160))


@persistent
def frame_update(scene,*args):
    update_actors(scene)


def install_handler():
    for fn in list(bpy.app.handlers.frame_change_post):
        if getattr(fn,'__name__','')=='frame_update' and getattr(fn,'__module__','').startswith('whitebox_world'):
            bpy.app.handlers.frame_change_post.remove(fn)
    bpy.app.handlers.frame_change_post.append(frame_update)
    if load_sync not in bpy.app.handlers.load_post:bpy.app.handlers.load_post.append(load_sync)


def bake(scene):
    actors=[o for o in scene.objects if o.get('ww_actor')]
    objects=actors+[c for a in actors for c in a.children if c.get('ww_limb') or c.get('ww_wheel')]
    frame=scene.frame_current
    for o in objects:o.animation_data_clear()
    for f in range(scene.frame_start,scene.frame_end+1):
        scene.frame_set(f);update_actors(scene)
        for o in objects:
            o.keyframe_insert(data_path='location',frame=f);o.keyframe_insert(data_path='rotation_euler',frame=f)
    for o in objects:
        if o.animation_data and o.animation_data.action:
            for fc in o.animation_data.action.fcurves:
                for point in fc.keyframe_points:point.interpolation='LINEAR'
    scene.frame_set(frame)


def sync_panel(scene):
    if hasattr(scene,'ww_biome'):
        import json
        config=json.loads(scene.get('ww_config','{}'))
        scene.ww_biome=scene.get('ww_active_biome','mixed')
        scene.ww_weather=scene.get('ww_active_weather','clear')
        scene.ww_seed=int(config.get('seed',42));scene.ww_size=float(config.get('size',160))
        scene.ww_elevation=float(scene.get('ww_sun_elevation',35));scene.ww_azimuth=float(scene.get('ww_sun_azimuth',135))
        scene.ww_map_file=config.get('map_file','');scene.ww_coordinates=config.get('coordinate_system','auto')


@persistent
def load_sync(*args):
    sync_panel(bpy.context.scene)
