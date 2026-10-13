"""Original, editable facade geometry, with a Blender-independent layout planner.

Detail is intentionally inferred rather than survey-accurate. No textures, downloaded
assets, booleans, or per-window objects are needed. Each building has at most four
semantic mesh children. Coordinates in the pure planner are meters.
"""
import hashlib
import json
import math
import random


COLORS = {
    'glazing': (.10, .19, .24, 1),
    'frames': (.67, .70, .69, 1),
    'balconies': (.43, .47, .47, 1),
    'shopfronts': (.25, .40, .40, 1),
}


def residential_type(tags):
    """Honor known mapped use; leave genuinely unknown use to seeded variation."""
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (ValueError, TypeError):
            return None
    if not isinstance(tags, dict):
        return None
    kind = str(tags.get('building', '')).lower()
    use = str(tags.get('building:use', '')).lower()
    residential = {'apartments', 'residential', 'house', 'detached', 'semidetached_house',
                   'terrace', 'dormitory', 'bungalow', 'cabin', 'hotel'}
    nonresidential = {'commercial', 'office', 'retail', 'industrial', 'warehouse',
                      'school', 'university', 'hospital', 'church', 'station',
                      'train_station', 'transportation', 'parking', 'garage',
                      'garages', 'civic', 'public', 'construction', 'roof'}
    if use in residential:
        return True
    if use in nonresidential:
        return False
    if kind in residential:
        return True
    if kind in nonresidential or tags.get('office'):
        return False
    return None


def _ring(points):
    points = [tuple(p[:2]) for p in points]
    if points and points[0] == points[-1]:
        points.pop()
    return points


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _inside(p, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                inside = not inside
    return inside


def _intersects(a, b, c, d):
    # Include touching: no detail should bridge a neighboring building wall.
    values = (_cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b))
    if values[0]*values[1] < 0 and values[2]*values[3] < 0:
        return True
    for v, p, x, y in ((values[0],c,a,b),(values[1],d,a,b),
                        (values[2],a,c,d),(values[3],b,c,d)):
        if abs(v) < 1e-8 and min(x[0],y[0])-1e-8 <= p[0] <= max(x[0],y[0])+1e-8 and min(x[1],y[1])-1e-8 <= p[1] <= max(x[1],y[1])+1e-8:
            return True
    return False


def _clear(rectangle, obstacles):
    for polygon in obstacles:
        if any(_inside(p, polygon) for p in rectangle) or any(_inside(p, rectangle) for p in polygon):
            return False
        if any(_intersects(a,b,c,d)
               for a,b in zip(rectangle,rectangle[1:]+rectangle[:1])
               for c,d in zip(polygon,polygon[1:]+polygon[:1])):
            return False
    return True


def _nearest(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    denom = dx*dx+dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/denom)) if denom else 0
    return (a[0]+t*dx, a[1]+t*dy)


def _street_facing(center, normal, roads):
    for road in roads:
        points = road.get('points', [])
        width = float(road.get('width', 6))
        for a,b in zip(points,points[1:]):
            near = _nearest(center,a,b)
            delta = (near[0]-center[0],near[1]-center[1])
            distance = math.hypot(*delta)
            if distance and distance <= 16+width/2 and sum(x*y for x,y in zip(delta,normal))/distance > .7:
                return True
    return False


def plan_facades(footprint, height, min_height=0, *, seed=42, key='',
                 neighbors=(), roads=(), residential=None):
    """Return semantic groups of oriented box specs; safe to call without Blender.

    Each box is (center_xyz, dimensions_xyz, tangent_xy, outward_normal_xy).
    Neighbor rings are conservative horizontal obstacles at every facade height.
    Street-facing ground floors receive glazing and awnings when road data exists.
    """
    points = _ring(footprint)
    groups = {name: [] for name in COLORS}
    span = height-min_height
    if len(points) < 3 or span < 2.7:
        return groups
    area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
    if abs(area) < .01:
        return groups
    rng = random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{key}'.encode()).digest()[:8], 'big'))
    residential = residential if residential is not None else (span <= 38 and rng.random() < .52)
    floors = min(18, max(1, int(span/3.2)))
    floor_height = span/floors
    obstacles = [points]+[_ring(p) for p in neighbors if len(p) >= 3]
    window_width = rng.uniform(1.12, 1.55)
    for a,b in zip(points,points[1:]+points[:1]):
        length = math.dist(a,b)
        if length < 2.6:
            continue
        tangent = ((b[0]-a[0])/length,(b[1]-a[1])/length)
        normal = (tangent[1],-tangent[0]) if area > 0 else (-tangent[1],tangent[0])
        bays = min(16, max(1,int((length-.9)/2.65)))
        spacing = (length-.8)/bays
        width = min(window_width,spacing*.63)
        edge_center = ((a[0]+b[0])/2,(a[1]+b[1])/2)
        shops = min_height < .3 and _street_facing(edge_center,normal,roads)

        def point(u, depth):
            return (a[0]+tangent[0]*u+normal[0]*depth,
                    a[1]+tangent[1]*u+normal[1]*depth)

        def clear(u, w, depth):
            rect = [point(u-w/2,.012),point(u+w/2,.012),
                    point(u+w/2,depth+.06),point(u-w/2,depth+.06)]
            return _clear(rect,obstacles)

        def box(group,u,depth,z,w,d,h):
            if min(w,d,h) <= 0:
                return
            p=point(u,depth)
            groups[group].append(((p[0],p[1],z),(w,d,h),tangent,normal))

        def frame(u,z,w,h):
            box('glazing',u,.055,z,w,.065,h)
            for side in (-1,1):
                box('frames',u+side*w/2,.13,z,.085,.20,h+.13)
                box('frames',u,.13,z+side*h/2,w+.08,.20,.085)
            box('frames',u,.12,z,.055,.17,h)
            box('frames',u,.19,z-h/2-.08,w+.24,.34,.12)

        for bay in range(bays):
            u=.4+spacing*(bay+.5)
            if not clear(u,width+.3,.39):
                continue
            for floor in range(floors):
                base=min_height+floor*floor_height
                if floor == 0 and shops:
                    shop_width=min(spacing*.83,3.1)
                    if not clear(u,shop_width+.25,.42):
                        continue
                    shop_height=min(2.45,floor_height-.65)
                    frame(u,base+.25+shop_height/2,shop_width,shop_height)
                    box('shopfronts',u,.16,base+shop_height+.49,shop_width+.16,.22,.24)
                    if clear(u,shop_width+.28,1.05):
                        box('shopfronts',u,.53,base+shop_height+.32,shop_width+.25,1.0,.12)
                        box('shopfronts',u,1.0,base+shop_height+.18,shop_width+.25,.10,.27)
                    continue
                win_h=min(1.75,floor_height-.95)
                z=base+.85+win_h/2
                frame(u,z,width,win_h)
                if residential and floor > 0 and bay % 2 == 0 and floor_height < 4.8 and clear(u,width+.75,1.10):
                    balcony_width=width+.6
                    deck_z=base+.27
                    box('balconies',u,.56,deck_z,balcony_width,1.06,.15)
                    box('balconies',u,1.05,deck_z+1.03,balcony_width,.075,.075)
                    posts=max(3,math.ceil(balcony_width/.34))
                    for post in range(posts+1):
                        box('balconies',u-balcony_width/2+post*balcony_width/posts,1.05,deck_z+.55,.045,.045,1.02)
                    for side in (-1,1):
                        box('balconies',u+side*balcony_width/2,.55,deck_z+1.03,.075,1.02,.075)
                        box('balconies',u+side*balcony_width/2,.10,deck_z+.55,.045,.045,1.02)
    return groups


def _mesh_boxes(specs):
    vertices, faces = [], []
    base_faces = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    for center,size,tangent,normal in specs:
        offset=len(vertices)
        for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                      (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)):
            vertices.append((center[0]+x*size[0]/2*tangent[0]+y*size[1]/2*normal[0],
                             center[1]+x*size[0]/2*tangent[1]+y*size[1]/2*normal[1],
                             center[2]+z*size[2]/2))
        reverse=tangent[0]*normal[1]-tangent[1]*normal[0] < 0
        faces.extend(tuple(offset+i for i in (face[::-1] if reverse else face)) for face in base_faces)
    return vertices,faces


def add_facades(building_objects, collection, config):
    """Add up to four editable, parented semantic meshes per generated shell.

    Shells use scene.building's ordered lower/upper vertex rings. Roads optionally
    arrive as config['_detail_roads'] dictionaries with points and width keys.
    """
    import bpy
    buildings=[]
    for obj in building_objects:
        if obj.type != 'MESH' or obj.get('ww_detail') or obj.get('ww_kind') != 'building':
            continue
        coords=[obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        if len(coords) < 6 or len(coords)%2:
            continue
        n=len(coords)//2
        footprint=[(v.x,v.y) for v in coords[:n]]
        buildings.append((obj,footprint,min(v.z for v in coords),max(v.z for v in coords)))
    created=[]
    for obj,footprint,bottom,top in buildings:
        # Spatially reject distant obstacles before testing individual facade bays.
        low_x=min(p[0] for p in footprint)-2; high_x=max(p[0] for p in footprint)+2
        low_y=min(p[1] for p in footprint)-2; high_y=max(p[1] for p in footprint)+2
        neighbors=[p for other,p,lo,hi in buildings if other != obj and hi > bottom and lo < top
                   and max(x for x,y in p) >= low_x and min(x for x,y in p) <= high_x
                   and max(y for x,y in p) >= low_y and min(y for x,y in p) <= high_y]
        groups=plan_facades(footprint,top,bottom,seed=config.get('seed',42),
                           key=obj.get('osm_id',obj.name),neighbors=neighbors,
                           roads=config.get('_detail_roads',[]),
                           residential=residential_type(obj.get('ww_source_tags',{})))
        for group,specs in groups.items():
            if not specs:
                continue
            name=f'{obj.name}_Facade_{group.title()}'
            mesh=bpy.data.meshes.new(name)
            vertices,faces=_mesh_boxes(specs)
            mesh.from_pydata(vertices,[],faces);mesh.update()
            detail=bpy.data.objects.new(name,mesh);collection.objects.link(detail)
            detail.parent=obj;detail.matrix_parent_inverse=obj.matrix_world.inverted()
            detail['ww_detail']=True;detail['ww_lod_parent']=obj.name;detail['ww_feature']='facades'
            detail['ww_kind']='facade_'+group
            detail['ww_inferred']=True
            material_name='WW_Facade_'+group
            mat=bpy.data.materials.get(material_name)
            if mat is None:
                mat=bpy.data.materials.new(material_name);mat.diffuse_color=COLORS[group];mat.use_nodes=True
                shader=mat.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Base Color'].default_value=COLORS[group]
                shader.inputs['Roughness'].default_value=.28 if group == 'glazing' else .72
                if group == 'glazing':shader.inputs['Metallic'].default_value=.3
            mesh.materials.append(mat);created.append(detail)
    return created
