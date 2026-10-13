"""Editable Blender scene construction. No downloaded meshes or application code."""
import bpy, math, random, json
from mathutils import Vector
from .core import validate_config

PALETTE={'grass':(.43,.55,.34,1),'ground':(.64,.70,.58,1),'building':(.83,.85,.85,1),'road':(.22,.27,.29,1),'line':(.88,.91,.84,1),'tree':(.42,.57,.49,1),'trunk':(.42,.40,.34,1),'sand':(.86,.79,.62,1),'water':(.32,.57,.64,1),'person':(.89,.46,.25,1),'vehicle':(.22,.46,.59,1),'glass':(.12,.22,.28,1),'rock':(.59,.64,.62,1)}


def material(name):
    name='WW_'+name
    if name in bpy.data.materials: return bpy.data.materials[name]
    m=bpy.data.materials.new(name); m.diffuse_color=PALETTE.get(name[3:],(.7,.7,.7,1)); m.use_nodes=True
    bsdf=m.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=m.diffuse_color; bsdf.inputs['Roughness'].default_value=.8
    return m


def collection(name):
    c=bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c); return c


def move(obj,col):
    for c in list(obj.users_collection): c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def cube(name,location,scale,mat,col,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location); o=bpy.context.object; o.name=name; o.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(material(mat)); move(o,col)
    if parent: o.parent=parent
    return o


def ico(name,location,scale,mat,col,parent=None):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=1,location=location); o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(material(mat)); move(o,col)
    if parent: o.parent=parent
    return o


def cylinder(name,location,radius,depth,mat,col,parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=radius,depth=depth,location=location); o=bpy.context.object; o.name=name; o.data.materials.append(material(mat)); move(o,col)
    if parent: o.parent=parent
    return o


def building(name,footprint,height,col,min_height=0):
    pts=footprint[:-1] if footprint[0]==footprint[-1] else footprint
    n=len(pts)
    if n<3:return
    vertices=[(x,y,z) for z in (min_height,height) for x,y in pts]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(vertices,[],faces); mesh.update()
    o=bpy.data.objects.new(name,mesh); col.objects.link(o); o.data.materials.append(material('building'));o['ww_kind']='building'; return o


def road(name,points,width,col):
    for i,(a,b) in enumerate(zip(points,points[1:])):
        d=math.dist(a[:2],b[:2]); o=cube(f'{name}_{i}',((a[0]+b[0])/2,(a[1]+b[1])/2,.025+.02*len(col.objects)/(1000+len(col.objects))),(d,width,.05),'road',col);o.rotation_euler.z=math.atan2(b[1]-a[1],b[0]-a[0])


def tree(x,y,size,col,rng):
    cylinder('Tree_Trunk',(x,y,size*.4),size*.07,size*.8,'trunk',col)
    ico('Tree_Crown',(x,y,size*.92),(size*.45,size*.45,size*.65),'tree',col)


def path(name,points,col):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D'; p=curve.splines.new('POLY');p.points.add(len(points)-1)
    for v,co in zip(p.points,points):v.co=(*co,1)
    o=bpy.data.objects.new(name,curve);col.objects.link(o);o.hide_render=True;o.color=(1,.25,.05,1);o['ww_path']=True
    return o


def actor(spec,col,paths):
    name=spec.get('name',spec.get('kind','person')); kind=spec.get('kind','person')
    root=bpy.data.objects.new(name,None);col.objects.link(root);root.empty_display_type='PLAIN_AXES';root.empty_display_size=1
    root['ww_actor']=True;root['ww_kind']=kind;root['ww_speed']=float(spec.get('speed',1.4 if kind=='person' else 7));root['ww_offset']=float(spec.get('offset',0));root['ww_loop']=bool(spec.get('loop',True));root['ww_phase']=float(spec.get('phase',0))
    pts=spec.get('path',[[-60,-7,0],[60,-7,0]])
    p=path(name+'_Path',[tuple(float(x) for x in (v if len(v)==3 else [*v,0])) for v in pts],paths);root['ww_path_name']=p.name
    if kind=='person':
        cube(name+'_Torso',(0,0,1.13),(.3,.5,.62),'person',col,root)
        ico(name+'_Head',(0,0,1.68),(.19,.19,.23),'person',col,root)
        for side in (-1,1):
            pivot=bpy.data.objects.new(name+('_LeftLeg' if side<0 else '_RightLeg'),None);col.objects.link(pivot);pivot.parent=root;pivot.location=(0,side*.14,.86);pivot['ww_limb']=side
            cube(name+'_Leg',(0,0,-.37),(.18,.18,.74),'person',col,pivot)
            arm=bpy.data.objects.new(name+'_Arm',None);col.objects.link(arm);arm.parent=root;arm.location=(0,side*.34,1.42);arm['ww_limb']=-side
            cube(name+'_ArmMesh',(0,0,-.25),(.14,.14,.56),'person',col,arm)
    else:
        cube(name+'_Body',(0,0,.7),(4.3,1.8,.72),'vehicle',col,root);cube(name+'_Cabin',(-.2,0,1.29),(2.15,1.65,.66),'glass',col,root)
        for x in (-1.3,1.3):
            for y in (-.91,.91):
                w=cylinder(name+'_Wheel',(x,y,.4),.4,.18,'road',col,root);w.rotation_euler.x=math.pi/2;w['ww_wheel']=True
        for y in (-.6,.6): cube(name+'_Light',(2.16,y,.8),(.035,.35,.18),'line',col,root)
    return root


def build(config):
    validate_config(config)
    map_data=None
    if config.get('map_file'):
        from .geo import load_map
        map_data=load_map(config['map_file'],config.get('coordinate_system','auto'),config.get('origin'))
    if map_data is not None and 'actors' not in config:
        from .geo import mapped_actors
        config={**config,'actors':mapped_actors(map_data)}
    if config.get('require_real_map'):
        if not map_data or not map_data['buildings'] or not map_data['roads'] or not map_data.get('provenance'):
            raise ValueError('Real-map config requires a nonempty map with provenance; no synthetic fallback')
        if any(not item.get('osm_id') for kind in ('buildings','roads') for item in map_data[kind]):
            raise ValueError('Real-map feature lacks an OSM source ID')
        if not config.get('actors'):
            raise ValueError('Real-map config requires explicit geographically aligned actor paths')
    # Only replace generated collections; retain unrelated user objects.
    for c in list(bpy.data.collections):
        if c.name.startswith('WW_'):
            for o in list(c.objects):bpy.data.objects.remove(o,do_unlink=True)
            bpy.data.collections.remove(c)
    cols={n:collection('WW_'+n) for n in ('Terrain','Buildings','Vegetation','Roads','Actors','Paths','Lighting','Cameras','Weather','Facades','Trees','RoadMarkings','UtilityPoles','TrafficLights')}
    s=bpy.context.scene; s.unit_settings.system='METRIC';s.unit_settings.scale_length=1;s.render.fps=int(config.get('fps',24));s.frame_start=1;s.frame_end=round(float(config.get('duration',12))*s.render.fps)
    s['ww_seed']=int(config.get('seed',42));s['ww_active_biome']=config.get('biome','city');s['ww_sun_elevation']=float(config.get('sun_elevation',35));s['ww_sun_azimuth']=float(config.get('sun_azimuth',135));s['ww_active_weather']=config.get('weather','clear');s['ww_config']=json.dumps(config,ensure_ascii=False)
    from .detail_runtime import setup
    setup(s, config)
    detail_roads=[];detail_buildings=[]
    rng=random.Random(s['ww_seed']);size=float(config.get('size',160));h=size/2;biome=s['ww_active_biome']
    cube('Ground',(0,0,-.22),(size,size,.4),'sand' if biome=='beach' else 'ground',cols['Terrain'])
    if biome in ('city','mixed') and map_data is None:
        road('Main_Road',[[-h,0],[h*.45 if biome=='mixed' else h,0]],10,cols['Roads']);road('Cross_Road',[[0,-h],[0,h]],10,cols['Roads'])
        detail_roads=[{'points':[[-h,0],[h*.45 if biome=='mixed' else h,0]],'width':10}, {'points':[[0,-h],[0,h]],'width':10}]
        for x in range(-int(h)+12,int(h)-8,19):
            for y in range(-int(h)+12,int(h)-8,19):
                if abs(x)<13 or abs(y)<13 or (biome=='mixed' and x>15):continue
                w=rng.uniform(9,14);d=rng.uniform(9,14);height=rng.uniform(8,34)
                building('Block_Building',[[x-w/2,y-d/2],[x+w/2,y-d/2],[x+w/2,y+d/2],[x-w/2,y+d/2]],height,cols['Buildings'])
    if biome in ('beach','mixed'):
        beach_x=h*.65 if biome=='mixed' else h*.25
        cube('Ocean',((h+beach_x)/2,0,-.02),(h-beach_x,size,.12),'water',cols['Terrain']);cube('Beach_Sand',(beach_x-h*.1,0,-.005),(h*.3,size,.1),'sand',cols['Terrain'])
        for i in range(8):cube('Shore_Ripple',(beach_x+h*.015*i,0,.055),(.13,size,.015),'line',cols['Terrain'])
    if biome!='city':
        for i in range(int(config.get('trees',90 if biome=='forest' else 28))):
            x,y=rng.uniform(-h+5,h-5),rng.uniform(-h+5,h-5)
            if abs(y)<10 or (biome=='mixed' and (x<12 or x>h*.42)) or (biome=='beach' and x>0):continue
            tree(x,y,rng.uniform(3,8),cols['Trees'],rng)
        for i in range(24):
            x,y=rng.uniform(-h,h),rng.uniform(-h,h)
            if abs(y)<9 or (biome in ('mixed','beach') and x>h*.4):continue
            ico('Boulder',(x,y,.35),(rng.uniform(.4,1.2),rng.uniform(.4,1.4),rng.uniform(.3,.8)),'rock',cols['Vegetation'])
        if biome!='mixed':road('Trail',[[-h,-5],[h*.15 if biome=='beach' else h,-5]],4,cols['Roads'])
    if biome in ('grassland','forest'):
        verts=[];faces=[]
        for i in range(800 if biome=='grassland' else 300):
            x,y=rng.uniform(-h,h),rng.uniform(-h,h)
            if abs(y+5)<4:continue
            z=rng.uniform(.25,.7);w=z*.22;n=len(verts)
            verts.extend([(x-w,y,0),(x+w,y,0),(x+.1,y,z),(x,y-w,0),(x,y+w,0),(x,y+.1,z)])
            faces.extend([(n,n+1,n+2),(n+3,n+4,n+5)])
        mesh=bpy.data.meshes.new('Grass_Tufts');mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new('Grass_Tufts',mesh);cols['Vegetation'].objects.link(o);o.data.materials.append(material('grass'))
    if config.get('map_file'):
        from .geo import load_map
        data=map_data
        # Imported map replaces demo city geometry/roads, not terrain.
        for key in ('Buildings','Roads'):
            for o in list(cols[key].objects):bpy.data.objects.remove(o,do_unlink=True)
        for b in data['buildings']:
            o=building(b['name'],b['footprint'],b['height'],cols['Buildings'],b.get('min_height',0))
            if o:o['ww_source_tags']=json.dumps(b.get('tags',{}))
            if o and b.get('osm_id'):
                o['osm_id']=str(b['osm_id']);o['height_source']=b.get('height_source','unspecified')
        for r in data['roads']:road(r['name'],r['points'],r['width'],cols['Roads'])
        detail_roads=data['roads'];detail_buildings=data['buildings']
        s['ww_map_provenance']=json.dumps(data.get('provenance',{}),ensure_ascii=False);s['ww_map_limitations']=json.dumps(data.get('limitations',{}),ensure_ascii=False)
        import pathlib
        txt=bpy.data.texts.get('WW_MapSource.geojson') or bpy.data.texts.new('WW_MapSource.geojson');txt.clear();txt.write(pathlib.Path(config['map_file']).read_text())
        bpy.data.objects['Ground']['map_attribution']=data.get('attribution','');bpy.data.objects['Ground']['map_license']='https://opendatacommons.org/licenses/odbl/1-0/';bpy.data.objects['Ground']['map_limitations']=s['ww_map_limitations']
        s['ww_map_attribution']=data.get('attribution','');s['ww_map_warnings']=json.dumps(data.get('warnings',[]))
    # Native editable detail layers. Imported OSM metadata is kept on shells.
    if not detail_buildings:
        detail_buildings=[{'footprint':[(v.co.x,v.co.y) for v in o.data.vertices[:len(o.data.vertices)//2]],'height':max(v.co.z for v in o.data.vertices)} for o in cols['Buildings'].objects]
    from .facades import add_facades
    from .street_details import add_street_details
    details_config={**config,'_detail_roads':detail_roads}
    add_facades(list(cols['Buildings'].objects),cols['Facades'],details_config)
    if detail_roads:
        metadata=add_street_details(detail_roads,detail_buildings,cols,config,(map_data or {}).get('street_features',[]))
        s['ww_street_details']=json.dumps(metadata,ensure_ascii=False)
    for o in cols['Trees'].objects:
        if not o.get('ww_feature'):o['ww_feature']='trees'
    from .detail_runtime import group_details
    group_details(s)
    actors=config.get('actors',[{'name':'Walker_A','kind':'person','speed':1.4,'path':[[-h*.7,-8,0],[h*.4 if biome=='mixed' else h*.15 if biome=='beach' else h*.7,-8,0]]},{'name':'Walker_B','kind':'person','speed':2.1,'offset':18,'path':[[-h*.7,-9,0],[h*.4 if biome=='mixed' else h*.15 if biome=='beach' else h*.7,-9,0]]},{'name':'Car_A','kind':'vehicle','speed':6,'path':[[-h*.75,-2.5,0],[h*.4 if biome=='mixed' else h*.15 if biome=='beach' else h*.75,-2.5,0]]}])
    for spec in actors:actor(spec,cols['Actors'],cols['Paths'])
    light=bpy.data.lights.new('WW_Sun','SUN');o=bpy.data.objects.new('WW_Sun',light);cols['Lighting'].objects.link(o);light.angle=math.radians(12)
    camera=bpy.data.cameras.new('WW_Camera');o=bpy.data.objects.new('WW_Camera',camera);cols['Cameras'].objects.link(o);o.location=(size*.79,-size*.93,size*.78);o.rotation_euler=(Vector((0,0,3))-o.location).to_track_quat('-Z','Y').to_euler();camera.type='ORTHO';camera.ortho_scale=size*1.42;s.camera=o
    s.render.engine='CYCLES';s.cycles.samples=64;s.cycles.use_denoising=False;s.render.resolution_x=1400;s.render.resolution_y=1000;s.render.resolution_percentage=100
    s.world=bpy.data.worlds.new('WW_World');s.world.use_nodes=True;s.view_settings.view_transform='AgX'
    from .runtime import update_environment,update_actors,install_handler,sync_panel
    sync_panel(s);update_environment(s);install_handler();update_actors(s);s.frame_set(1)
    from .detail_runtime import install,update_details
    install();update_details(s)
    return s
