"""Pure floor/bay layout, semantic modules and aperture constraints in meters."""
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


from .facade_styles import STYLES, classify_style, stable_seed, source_tags


def plan_facade_layout(footprint, height, min_height=0, *, seed=42, key='',
                       neighbors=(), roads=(), residential=None, tags=None, style=None):
    """Plan bounded modules and actual openings in edge-local (u,z) coordinates.

    Semantic box groups remain editable meshes. Openings drive *replacement*
    near walls, never overlays on the solid coarse building. Neighbors are a
    conservative full-height 2D exclusion; this intentionally over-suppresses
    windows above shorter adjoining buildings rather than inventing exposure.
    """
    points = _ring(footprint)
    groups = {name: [] for name in COLORS}
    groups['accents'] = []
    groups['spandrels'] = []
    result = dict(groups=groups, edges=[], footprint=points, bottom=min_height,
                  top=height, style='blank', provenance='invalid_geometry', seed=stable_seed(seed,key))
    span = height-min_height
    if len(points) < 3 or span < 2.7: return result
    area2 = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
    if abs(area2) < .01: return result
    # Reject self-crossing rings instead of creating an invalid architectural mesh.
    segments=list(zip(points,points[1:]+points[:1]))
    if any(_intersects(a,b,c,d) for i,(a,b) in enumerate(segments)
           for j,(c,d) in enumerate(segments) if j > i+1 and not (i == 0 and j == len(segments)-1)):
        result['provenance']='unsupported_self_intersection';return result
    if not tags and residential is not None and not style:
        style = 'apartment' if residential else 'office'
    family, provenance = classify_style(tags, height=span, area=abs(area2)/2, seed=seed,key=key,override=style)
    result.update(style=family,provenance=provenance)
    rule=STYLES[family]; rng=random.Random(result['seed'])
    # Keep the floor rhythm architectural rather than stretching 18 capped floors.
    floors=max(1,min(90,round(span/rule['floor'])))
    result['floor_source']='height_prior'
    try:
        mapped=float(source_tags(tags).get('building:levels',0))
        minimum=float(source_tags(tags).get('building:min_level',0))
        candidate=round(mapped-minimum)
        if mapped and (min_height < .3 or minimum > 0) and 1 <= candidate <= min(90,span/2.3):
            floors=candidate;result['floor_source']='mapped_levels'
    except (ValueError,TypeError,OverflowError):pass
    if family == 'warehouse': floors=1;result['floor_source']='industrial_single_hall'
    fh=span/floors
    result['floors']=floors
    obstacles=[points]+[_ring(p) for p in neighbors if len(p)>=3]
    longest=max(math.dist(a,b) for a,b in segments)
    variation=rng.uniform(.90,1.08)
    for edge_index,(a,b) in enumerate(segments):
        length=math.dist(a,b)
        if length < 1e-6: continue
        tangent=((b[0]-a[0])/length,(b[1]-a[1])/length)
        normal=(tangent[1],-tangent[0]) if area2>0 else (-tangent[1],tangent[0])
        edge=dict(a=a,b=b,length=length,tangent=tangent,normal=normal,openings=[])
        result['edges'].append(edge)
        if length < 2.25 or family == 'blank': continue
        margin=max(.45,min(.75,length*.055))
        usable=length-2*margin
        bays=max(1,min(120,int(usable/rule['pitch'])))
        spacing=usable/bays
        edge_center=((a[0]+b[0])/2,(a[1]+b[1])/2)
        street=_street_facing(edge_center,normal,roads)
        principal=street or length >= longest*.95
        balcony_side=family == 'apartment' and principal
        shops = min_height < .3 and street and family in {'retail','apartment','office','office_ribbon','curtain_wall'}

        def point(u,depth):
            return (a[0]+tangent[0]*u+normal[0]*depth,a[1]+tangent[1]*u+normal[1]*depth)

        def clear(u,w,depth):
            rect=[point(u-w/2,.012),point(u+w/2,.012),point(u+w/2,depth*2+.08),point(u-w/2,depth*2+.08)]
            return _clear(rect,obstacles)

        def box(group,u,depth,z,w,d,h):
            if min(w,d,h) <= 1e-5 or z-h/2 < min_height-1e-6 or z+h/2 > height+1e-6:return
            p=point(u,depth)
            groups[group].append(((p[0],p[1],z),(w,d,h),tangent,normal))

        def opening(u,z,w,h,kind='window'):
            if w < .45 or h < .4 or u-w/2 < margin-.01 or u+w/2 > length-margin+.01:return False
            if z-h/2 < min_height+.16 or z+h/2 > height-.22:return False
            if not clear(u,w+.12,.20):return False
            # Inward reveals must actually lie within the shell at both jambs.
            if not all(_inside(point(v,-.31),points) for v in (u-w/2,u,u+w/2)):return False
            edge['openings'].append(dict(u0=u-w/2,u1=u+w/2,z0=z-h/2,z1=z+h/2,kind=kind))
            recess=rule['recess']
            box('glazing' if kind!='loading' else 'accents',u,-recess,z,w,.045,h)
            frame=.055 if family == 'curtain_wall' else .075
            for side in (-1,1):
                box('frames',u+side*(w/2-frame/2),-.035,z,frame,.105,h)
                box('frames',u,-.035,z+side*(h/2-frame/2),w-2*frame,.105,frame)
            if kind=='loading':
                for row in range(1,8):box('frames',u,-.055,z-h/2+h*row/8,w,.09,.035)
            elif family == 'house':
                box('frames',u,-.025,z,.055,.11,h-2*frame)
                for side in (-1,1):
                    half=(w-2*frame-.055)/2
                    box('frames',u+side*(.055/2+half/2),-.025,z+.08,half,.11,.055)
                # Paired slim shutters are a house-only silhouette cue.
                if clear(u,w+.54,.15):
                    for side in (-1,1):box('accents',u+side*(w/2+.17),.05,z,.25,.10,h)
            elif family in {'office_ribbon','curtain_wall'} or kind=='shop':
                panes=max(1,round(w/(1.35 if family=='curtain_wall' else 1.5)))
                for p in range(1,panes):box('frames',u-w/2+w*p/panes,-.015,z,.065,.12,h-2*frame)
                if kind=='shop':box('frames',u,-.025,z+h*.24,w,.11,.055)
            elif family in {'office','apartment','retail'}:
                box('frames',u,-.025,z,.045,.10,h-2*frame)
                if family=='office':
                    for side in (-1,1):
                        half=(w-2*frame-.045)/2
                        box('frames',u+side*(.045/2+half/2),-.025,z+h*.25,half,.10,.045)
            if family not in {'curtain_wall','warehouse'}:
                box('frames',u,.075,z-h/2-.045,w+.13,.23,.09)
            return True

        for floor in range(floors):
            base=min_height+floor*fh
            is_shop=floor==0 and shops
            if family in {'office_ribbon','curtain_wall'} and not is_shop:
                # Continuous glazed bands, unlike repeated punched windows.
                w=usable; h=fh-.50 if family=='curtain_wall' else min(rule['window'],fh-.72)
                z=base+(fh-h)/2+h/2
                if opening(length/2,z,w,h,'ribbon'):
                    if family=='curtain_wall':
                        box('spandrels',length/2,-.025,base+.39,w-.06,.08,.52)
                        panes=max(1,round(w/1.35))
                        for p in range(panes+1):
                            box('frames',margin+w*p/panes,.035,base+fh/2,.065,.14,fh)
                    elif clear(length/2,w,.18):
                        box('accents',length/2,.055,base+.17,w,.14,.20)
                else:
                    # Shared/partially obstructed elevations keep individually safe bays.
                    for bay in range(bays):
                        u=margin+spacing*(bay+.5)
                        opening(u,z,spacing-.12,h,'ribbon')
                continue
            for bay in range(bays):
                u=margin+spacing*(bay+.5)
                w=min(rule['width']*variation,spacing-.40)
                h=min(rule['window'],fh-.95)
                sill=min(rule['sill'],fh-h-.30)
                if family=='apartment' and not balcony_side:
                    w=min(1.0,spacing*.5);h=min(1.25,fh-1.1);sill=.95
                if family=='warehouse':
                    sill=max(.50,span-h-1.0)
                if is_shop or (family=='retail' and floor==0 and min_height<.3):
                    w=min(spacing-.22,3.7);h=min(2.85,fh-.70);sill=.24
                z=base+sill+h/2
                kind='shop' if is_shop or (family=='retail' and floor==0 and min_height<.3) else 'window'
                if not opening(u,z,w,h,kind):continue
                if kind=='shop':
                    if clear(u,w+.12,.30):box('shopfronts',u,.08,base+fh-.22,w+.1,.16,.30)
                    if street and clear(u,w+.16,.90):
                        box('shopfronts',u,.43,base+h+.38,w+.12,.85,.10)
                        box('shopfronts',u,.83,base+h+.27,w+.12,.09,.20)
                if balcony_side and floor>0 and clear(u,min(spacing-.1,w+.65),1.12):
                    bw=min(spacing-.1,w+.65);deck=base+.20
                    box('balconies',u,.55,deck,bw,1.10,.14)
                    box('balconies',u,1.055,deck+.95,bw,.08,.09)
                    box('accents',u,1.04,deck+.45,bw,.07,.55)
                    posts=max(2,round(bw/.55))
                    for p in range(posts+1):box('balconies',u-bw/2+bw*p/posts,1.045,deck+.53,.045,.07,.90)
                    for side in (-1,1):box('balconies',u+side*bw/2,.56,deck+.55,.08,1.05,1.0)
            if family=='warehouse':
                # A broad, inset loading shutter differentiates industrial ground floors.
                if principal and span>=5 and usable>=4:
                    w=min(3.7,usable*.36);h=min(3.4,span-rule['window']-1.7)
                    if h>=2:opening(length/2,min_height+.20+h/2,w,h,'loading')
                for bay in range(bays+1):
                    u=margin+spacing*bay
                    if clear(u,.1,.16):box('frames',u,.045,min_height+span/2,.075,.12,span-.12)
        # Modest roofline; no change to the mapped height or footprint.
        if family in {'house','apartment','retail','office'} and clear(length/2,length-.16,.20):
            box('accents',length/2,.055,height-.16,length-.16,.14,.18)
    return result


def plan_facades(*args,**kwargs):
    """Compatibility API for callers needing only semantic box specifications."""
    return plan_facade_layout(*args,**kwargs)['groups']
