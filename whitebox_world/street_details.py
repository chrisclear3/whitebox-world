"""Editable original street props and deterministic, collision-aware placement.

The planner imports no Blender APIs. Source features must already be projected
into scene metres. Inferred assets are illustrative, not surveyed infrastructure.
"""
import math
import random

KINDS = ('trees', 'road_markings', 'utility_poles', 'traffic_lights')
NON_MOTOR = {'footway', 'path', 'steps', 'cycleway', 'pedestrian', 'track'}


def segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    den = dx*dx+dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def inside_polygon(p, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if p[0] < x:
                inside = not inside
    return inside


class PlacementIndex:
    """Small spatial grid; queries cost local density rather than city size."""
    def __init__(self, roads, buildings, cell=24):
        self.cell = cell
        self.grid = {}
        for i, road in enumerate(roads):
            for a, b in zip(road['points'], road['points'][1:]):
                radius = float(road.get('width', 6))/2
                self._insert(('road', a, b, radius, i),
                             (min(a[0], b[0])-radius, min(a[1], b[1])-radius,
                              max(a[0], b[0])+radius, max(a[1], b[1])+radius))
        for building in buildings:
            polygon = list(building.get('footprint', []))
            if polygon:
                self._insert(('building', polygon), (min(p[0] for p in polygon),
                    min(p[1] for p in polygon), max(p[0] for p in polygon), max(p[1] for p in polygon)))

    def _cells(self, bounds):
        x0, y0, x1, y1 = bounds
        for x in range(math.floor(x0/self.cell), math.floor(x1/self.cell)+1):
            for y in range(math.floor(y0/self.cell), math.floor(y1/self.cell)+1):
                yield x, y

    def _insert(self, item, bounds):
        for key in self._cells(bounds):
            self.grid.setdefault(key, []).append(item)

    def clear(self, p, radius, ignore_road=None):
        seen = set()
        for key in self._cells((p[0]-radius, p[1]-radius, p[0]+radius, p[1]+radius)):
            for item in self.grid.get(key, []):
                if id(item) in seen:
                    continue
                seen.add(id(item))
                if item[0] == 'road':
                    if item[4] != ignore_road and segment_distance(p, item[1], item[2]) < item[3]+radius:
                        return False
                else:
                    polygon = item[1]
                    if inside_polygon(p, polygon) or any(segment_distance(p, a, b) <= radius
                        for a, b in zip(polygon, polygon[1:]+polygon[:1])):
                        return False
        return True


def road_samples(road, spacing, start=None):
    """Continuous arc-length sampling, without duplicate samples at vertices."""
    distance = spacing/2 if start is None else start
    for a, b in zip(road['points'], road['points'][1:]):
        length = math.dist(a[:2], b[:2])
        if length < 1e-8:
            continue
        tangent = ((b[0]-a[0])/length, (b[1]-a[1])/length)
        while distance <= length:
            yield (a[0]+tangent[0]*distance, a[1]+tangent[1]*distance), tangent
            distance += spacing
        distance -= length



def on_road_surface(point, road):
    """Match the rectangular road segment meshes, including square end caps."""
    for a, b in zip(road['points'], road['points'][1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length2 = dx*dx+dy*dy
        if length2 < 1e-10:
            continue
        t = ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length2
        if 0 <= t <= 1 and segment_distance(point,a,b) <= float(road.get('width',6))/2:
            return True
    return False


def _road_tag(road, key, default=''):
    return road.get(key, road.get('tags', {}).get(key, default))


def _at_grade(road):
    for key in ('bridge', 'tunnel'):
        if str(_road_tag(road, key, 'no')).lower() not in ('no', '', 'none', 'false', '0'):
            return False
    try:
        return float(_road_tag(road, 'layer', 0) or 0) == 0
    except (TypeError, ValueError):
        return False


def intersections(roads, min_angle=0):
    """Find at-grade segment crossings; grade-separated tagged ways are skipped."""
    segments = []
    grid = {}
    found = {}
    for ri, road in enumerate(roads):
        if _road_tag(road, 'highway') in NON_MOTOR or not _at_grade(road):
            continue
        for a, b in zip(road['points'], road['points'][1:]):
            if math.dist(a[:2], b[:2]) < 1e-6:
                continue
            keys = [(x, y) for x in range(math.floor(min(a[0], b[0])/32), math.floor(max(a[0], b[0])/32)+1)
                    for y in range(math.floor(min(a[1], b[1])/32), math.floor(max(a[1], b[1])/32)+1)]
            candidates = {idx for key in keys for idx in grid.get(key, [])}
            for idx in candidates:
                rj, c, d = segments[idx]
                if rj == ri:
                    continue
                u = (b[0]-a[0], b[1]-a[1]); v = (d[0]-c[0], d[1]-c[1])
                den = u[0]*v[1]-u[1]*v[0]
                if abs(den) < 1e-7 or abs(den)/(math.hypot(*u)*math.hypot(*v)) < math.sin(math.radians(min_angle))-1e-9:
                    continue
                q = (c[0]-a[0], c[1]-a[1])
                t = (q[0]*v[1]-q[1]*v[0])/den
                s = (q[0]*u[1]-q[1]*u[0])/den
                if -1e-7 <= t <= 1+1e-7 and -1e-7 <= s <= 1+1e-7:
                    p = (a[0]+u[0]*t, a[1]+u[1]*t)
                    key = (round(p[0], 1), round(p[1], 1))
                    entry = found.setdefault(key, {'point': p, 'roads': set()})
                    entry['roads'].update((ri, rj))
            idx = len(segments); segments.append((ri, a, b))
            for key in keys:
                grid.setdefault(key, []).append(idx)
    return list(found.values())


def signal_junctions(roads, merge_distance=12):
    """Conservative signal candidates: real bends/crossings, merged nearby nodes.

    Merge around the first representative rather than chaining an entire street
    into a single junction. Keep that real road crossing as the placement anchor.
    """
    candidates = intersections(roads, min_angle=30)
    merged = []
    minor = {'service', 'living_street', 'track', 'path', 'footway', 'pedestrian'}
    for candidate in sorted(candidates, key=lambda j: j['point']):
        if all(_road_tag(roads[i], 'highway') in minor for i in candidate['roads']):
            continue
        neighbor = next((j for j in merged if math.dist(candidate['point'],j['point']) < merge_distance),None)
        if neighbor is not None:
            neighbor['roads'].update(candidate['roads'])
        else:
            merged.append({'point':candidate['point'],'roads':set(candidate['roads'])})
    return merged


def plan_street_details(roads, buildings, config, source_features=None):
    """Return feature lists and metadata. All coordinates are local metres."""
    options = config.get('street_details', {})
    if options is False:
        options = {'enabled': False}
    options = options if isinstance(options, dict) else {}
    result = {kind: [] for kind in KINDS}
    limits = {'trees': int(options.get('max_trees', 220)), 'utility_poles': int(options.get('max_poles', 140)),
              'traffic_lights': int(options.get('max_traffic_lights', 80)), 'road_markings': int(options.get('max_markings', 3000))}
    limitations = ['Procedural street props are illustrative, not verified real-world locations.',
                   'Lane paint and signal hardware are stylized, not a traffic-engineering survey.',
                   'Source points colliding with mapped footprints or carriageways are omitted, never relocated.',
                   'Unmapped road levels/bridges may produce inferred false intersections.']
    if not options.get('enabled', True):
        result['metadata'] = {'counts': {k: 0 for k in KINDS}, 'limitations': limitations, 'enabled': False}
        return result
    rng = random.Random(int(config.get('seed', 42)))
    index = PlacementIndex(roads, buildings)
    used = []
    source_counts = {k: 0 for k in KINDS}
    skipped_source = 0
    aliases = {'tree': 'trees', 'utility_pole': 'utility_poles', 'traffic_light': 'traffic_lights'}
    features = source_features or []
    if isinstance(features, dict):
        features = [dict(f, kind=kind) for kind, group in features.items() if isinstance(group, list) for f in group]

    def add(kind, p, radius, road_ids, placement='procedural', source_id=None, angle=0, size=1):
        if len(result[kind]) >= max(0, limits[kind]):
            return False
        if not index.clear(p, radius) or any(math.dist(p, q) < radius+r+.6 for q, r in used):
            return False
        item = {'point': tuple(p), 'angle': angle, 'size': size, 'placement': placement,
                'source_road_ids': [str(x) for x in road_ids], 'source_id': source_id}
        result[kind].append(item); used.append((tuple(p), radius))
        return True

    for f in features:
        kind = aliases.get(f.get('kind'), f.get('kind'))
        p = f.get('point')
        if kind not in ('trees', 'utility_poles', 'traffic_lights') or not p or len(p) < 2:
            continue
        p = tuple(float(x) for x in p[:2])
        if not all(math.isfinite(x) for x in p):
            continue
        nearest = min(range(len(roads)), key=lambda i: min((segment_distance(p, a, b)
            for a, b in zip(roads[i]['points'], roads[i]['points'][1:])), default=float('inf')), default=None)
        ids = [roads[nearest].get('osm_id') or f'road_{nearest}'] if nearest is not None else []
        size = 4.8 if kind == 'trees' else 1
        if add(kind, p, 2.0 if kind == 'trees' else 1.15 if kind == 'utility_poles' else .65, ids, 'source', f.get('osm_id'), size=size):
            source_counts[kind] += 1
        else:
            skipped_source += 1

    junctions = intersections(roads)
    for ri, road in enumerate(roads):
        road_id = road.get('osm_id') or f'road_{ri}'
        width = float(road.get('width', 6))
        for kind, spacing, radius in [('trees', max(5, float(options.get('tree_spacing', 22))), 2.0),
                                      ('utility_poles', max(10, float(options.get('pole_spacing', 38))), 1.15)]:
            if kind == 'utility_poles' and road.get('highway') in NON_MOTOR:
                continue
            for p, tangent in road_samples(road, spacing):
                for side in ((-1, 1) if kind == 'trees' else (1,)):
                    offset = width/2+radius+.9
                    candidate = (p[0]-tangent[1]*offset*side, p[1]+tangent[0]*offset*side)
                    add(kind, candidate, radius, [road_id], angle=math.atan2(tangent[1], tangent[0]),
                        size=rng.uniform(4.0, 4.8) if kind == 'trees' else 1)
        if width >= 5 and road.get('highway') not in NON_MOTOR:
            for p, tangent in road_samples(road, 8):
                if len(result['road_markings']) >= max(0, limits['road_markings']):
                    break
                # No center paint through junctions, intersecting roads, or buildings.
                if any(math.dist(p, j['point']) < width+3 for j in junctions if ri in j['roads']):
                    continue
                ends = [(p[0]+tangent[0]*d, p[1]+tangent[1]*d) for d in (-1.7, 0, 1.7)]
                if not all(on_road_surface(q, road) and index.clear(q, .1, ignore_road=ri) for q in ends):
                    continue
                result['road_markings'].append({'point': p, 'angle': math.atan2(tangent[1], tangent[0]),
                    'road_index': ri, 'source_road_ids': [str(road_id)], 'placement': 'procedural'})
    signal_candidates = signal_junctions(roads)
    for j in signal_candidates:
        p = j['point']; road_ids = [roads[i].get('osm_id') or f'road_{i}' for i in sorted(j['roads'])]
        half = max(float(roads[i].get('width', 6))/2 for i in j['roads'])
        # Candidate ring gives corners at arbitrary junction angles, checked against all roads.
        placed = 0
        for attempt in range(16):
            angle = ((attempt*7)%16)*math.tau/16
            distance = (half+1.4)*math.sqrt(2)
            q = (p[0]+math.cos(angle)*distance, p[1]+math.sin(angle)*distance)
            if add('traffic_lights', q, .65, road_ids, angle=angle+math.pi):
                placed += 1
            if placed >= 2:
                break
    result['metadata'] = {'counts': {kind: len(result[kind]) for kind in KINDS},
        'source_counts': source_counts, 'procedural_counts': {k: len(result[k])-source_counts[k] for k in KINDS},
        'skipped_source_collisions_or_limit': skipped_source, 'intersection_count': len(junctions),
        'signal_junction_count': len(signal_candidates), 'limits': limits, 'limitations': limitations, 'enabled': True}
    return result


class _Mesh:
    """Disconnected solids batched into one editable mesh per logical part."""
    def __init__(self):
        self.vertices = []; self.faces = []; self.materials = []

    def solid(self, vertices, faces, material=0):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset+i for i in face) for face in faces)
        self.materials.extend([material]*len(faces))

    def box(self, center, size, material=0):
        x,y,z = center; a,b,c = [s/2 for s in size]
        self.solid([(x+i*a,y+j*b,z+k*c) for k in (-1,1) for j in (-1,1) for i in (-1,1)],
                   [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)], material)

    def rings(self, rings, sides=8, material=0):
        vertices = [(math.cos(i*math.tau/sides)*r,math.sin(i*math.tau/sides)*r,z)
                    for z,r in rings for i in range(sides)]
        faces = [tuple(range(sides-1,-1,-1)), tuple(range((len(rings)-1)*sides,len(rings)*sides))]
        faces += [(j*sides+i,j*sides+(i+1)%sides,(j+1)*sides+(i+1)%sides,(j+1)*sides+i)
                  for j in range(len(rings)-1) for i in range(sides)]
        self.solid(vertices, faces, material)


def add_street_details(roads, buildings, collections, config, source_features=None):
    """Create meshes directly (no operator primitives), then return JSON-safe metadata."""
    import bpy
    plan = plan_street_details(roads, buildings, config, source_features)
    if not plan['metadata']['enabled']:
        plan['metadata']['object_count'] = 0
        return plan['metadata']
    colors = [('Bark',(.32,.29,.23,1)),('Foliage',(.30,.47,.34,1)),('Metal',(.25,.29,.30,1)),
              ('Paint',(.88,.89,.77,1)),('SignalRed',(.75,.11,.07,1)),('SignalAmber',(.85,.51,.06,1)),
              ('SignalGreen',(.12,.56,.30,1)),('Insulator',(.64,.72,.72,1))]
    mats=[]
    for name, color in colors:
        mat = bpy.data.materials.get('WW_Street_'+name) or bpy.data.materials.new('WW_Street_'+name)
        mat.diffuse_color=color; mat.use_nodes=True
        shader=mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value=color; shader.inputs['Roughness'].default_value=.8
        mats.append(mat)

    def mesh_data(name, builder):
        mesh=bpy.data.meshes.new(name); mesh.from_pydata(builder.vertices, [], builder.faces); mesh.update()
        for mat in mats: mesh.materials.append(mat)
        for poly, slot in zip(mesh.polygons, builder.materials): poly.material_index=slot
        return mesh

    templates={}
    b=_Mesh(); b.rings([(0,.045),(.65,.033)], material=0)
    b.rings([(.42,.13),(.67,.39),(.97,.32),(1.18,.03)], sides=9, material=1)
    templates['trees']=mesh_data('WW_StreetTree_LinkedMesh',b)
    b=_Mesh(); b.rings([(0,.15),(7.2,.095)], material=0); b.box((0,0,6.7),(.3,2.1,.19),2)
    templates['utility_poles']=mesh_data('WW_UtilityPole_LinkedMesh',b)
    b=_Mesh()
    for y in (-.8,0,.8): b.box((0,y,6.96),(.19,.19,.34),7)
    templates['pole_detail']=mesh_data('WW_PoleInsulators_LinkedMesh',b)
    b=_Mesh(); b.rings([(0,.12),(3.6,.085)], material=2); b.box((.12,0,3.5),(.33,.4,1.02),2)
    templates['traffic_lights']=mesh_data('WW_TrafficSignal_LinkedMesh',b)
    b=_Mesh()
    for z, mat in [(3.8,4),(3.5,5),(3.2,6)]: b.box((.3,0,z),(.055,.24,.22),mat)
    templates['signal_detail']=mesh_data('WW_SignalLenses_LinkedMesh',b)
    coll_keys=dict(zip(KINDS,('Trees','RoadMarkings','UtilityPoles','TrafficLights')))
    objects=0

    def make(name, mesh, item, kind, detail=False):
        nonlocal objects
        obj=bpy.data.objects.new(name,mesh); collections[coll_keys[kind]].objects.link(obj)
        obj.location=(*item['point'],0); obj.rotation_euler.z=item.get('angle',0)
        obj['ww_feature']=kind; obj['ww_detail']=detail; obj['ww_placement']=item['placement']
        obj['ww_source_road_ids']=','.join(item.get('source_road_ids',[]))
        if item.get('source_id') is not None: obj['osm_id']=str(item['source_id'])
        obj['ww_generated']=True; objects+=1
        return obj

    for kind in ('trees','utility_poles','traffic_lights'):
        for i,item in enumerate(plan[kind]):
            obj=make('WW_'+kind.title()+f'_{i:04d}',templates[kind],item,kind)
            if kind=='trees': obj.scale=(item['size'],)*3
            if kind in ('utility_poles','traffic_lights'):
                detail=make(obj.name+'_Detail',templates['pole_detail' if kind=='utility_poles' else 'signal_detail'],item,kind,True)
                detail.parent=obj; detail.location=(0,0,0); detail.rotation_euler=(0,0,0)
    grouped={}
    for item in plan['road_markings']: grouped.setdefault(item['road_index'],[]).append(item)
    for ri,items in grouped.items():
        b=_Mesh()
        origin=items[0]['point']
        for item in items:
            c,s=math.cos(item['angle']),math.sin(item['angle'])
            vertices=[(item['point'][0]-origin[0]+x*c-y*s,item['point'][1]-origin[1]+x*s+y*c,.09)
                      for x,y in [(-1.6,-.08),(1.6,-.08),(1.6,.08),(-1.6,.08)]]
            b.solid(vertices,[(0,1,2,3)],3)
        item=dict(items[0],angle=0)
        obj=make(f'WW_RoadPaint_{ri:04d}',mesh_data(f'WW_RoadPaintMesh_{ri:04d}',b),item,'road_markings',True)
        obj['ww_marking_count']=len(items)
    metadata=plan['metadata']; metadata['object_count']=objects
    metadata['editable_geometry']='Original low-poly meshes; shared prop mesh data, one paint mesh per road.'
    return metadata
