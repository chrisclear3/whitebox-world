"""Download a bounded ODbL map extract from public Rokehan packs (no app code).

Python standard library only. Fails on missing/invalid data; never synthesizes a city.
"""
import argparse, datetime, gzip, hashlib, json, math, os, pathlib, sys, tempfile, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from whitebox_world.geo import project_lonlat, load_map, parse_length
BASE = 'https://tools.oyasumi-gamedev.com/rokehan/packs/'
ATTR = '© OpenStreetMap contributors, ODbL 1.0; public pack supplied by Rokehan'

def decode_coordinates(values):
    if len(values) % 2: raise ValueError('Odd packed coordinate count')
    lat = lon = 0
    out = []
    for i in range(0, len(values), 2):
        lat += values[i]; lon += values[i+1]
        out.append([lon / 10_000_000, lat / 10_000_000])
    return out

def clip_segment(a, b, half):
    low, high = 0., 1.
    delta = [b[i]-a[i] for i in range(2)]
    for p, q in ((-delta[0],a[0]+half),(delta[0],half-a[0]),(-delta[1],a[1]+half),(delta[1],half-a[1])):
        if p == 0:
            if q < 0: return None
        elif p < 0: low=max(low,q/p)
        else: high=min(high,q/p)
        if low > high: return None
    if high-low < 1e-10: return None
    return [[a[i]+t*delta[i] for i in range(2)] for t in (low,high)]

def clipped_lines(points, half):
    lines=[]
    for a,b in zip(points,points[1:]):
        seg=clip_segment(a,b,half)
        if seg:
            if lines and math.dist(lines[-1][-1],seg[0]) < 1e-7: lines[-1].append(seg[1])
            else: lines.append(seg)
    return lines

def extract(tiles, origin, size):
    half=size/2; features=[]; seen=set(); omitted_relations=set(); boundary_buildings=0
    for tile in tiles:
        if tile.get('v',1) != 1: raise ValueError('Unsupported Rokehan pack version')
        for rel in tile.get('r',[]): omitted_relations.add(rel[0])
        for osm_id, nodes, packed, tags in tile.get('w',[]):
            if osm_id in seen: continue
            seen.add(osm_id)
            pts=[project_lonlat(*p,origin) for p in decode_coordinates(packed)]
            props={**tags,'osm_type':'way','osm_id':osm_id,'osm_url':f'https://www.openstreetmap.org/way/{osm_id}'}
            if tags.get('building') not in (None,'no') or tags.get('building:part') not in (None,'no'):
                if len(pts)<4 or pts[0]!=pts[-1]: continue
                if not all(abs(x)<=half and abs(y)<=half for x,y in pts):
                    if any(abs(x)<=half and abs(y)<=half for x,y in pts): boundary_buildings+=1
                    continue
                props['height_source']='osm_height' if parse_length(tags.get('height') or tags.get('building:height')) else 'estimated_levels_x_3m' if tags.get('building:levels') else 'estimated_default_9m'
                geom={'type':'Polygon','coordinates':[pts]}
            elif tags.get('highway') and tags.get('area')!='yes':
                # Flat-ground example excludes grade-separated/subsurface ways.
                if tags.get('tunnel') not in (None,'no') or tags.get('bridge') not in (None,'no') or str(tags.get('layer','0')) != '0': continue
                lines=clipped_lines(pts,half)
                if not lines: continue
                geom={'type':'MultiLineString','coordinates':lines}
            else: continue
            features.append({'type':'Feature','id':f'way/{osm_id}','properties':props,'geometry':geom})
    return {'type':'FeatureCollection','name':f'Real OSM extract near {origin[1]:.5f}, {origin[0]:.5f}','coordinate_system':'local','origin':origin,'attribution':ATTR,'license':'https://opendatacommons.org/licenses/odbl/1-0/','features':features,'limitations':{'terrain':'flat; no DEM imported','relations_omitted_in_source_tiles':len(omitted_relations),'boundary_buildings_omitted':boundary_buildings,'roads':'width inferred where absent; underground/elevated ways excluded','buildings':'whole way footprints only; no relation assembly or building-part union'}}

def fetch(url, records, refresh=False):
    cache=pathlib.Path(tempfile.gettempdir())/'whitebox-rokehan-cache';cache.mkdir(exist_ok=True)
    cached=cache/hashlib.sha256(url.encode()).hexdigest()
    if cached.exists() and 'index.json' not in url and not refresh:
        raw=cached.read_bytes()
    else:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WhiteboxWorld/0.2 public map adapter'}),timeout=60) as response:
            raw=response.read(16*1024*1024+1)
        if len(raw)<=16*1024*1024: cached.write_bytes(raw)
    if len(raw)>16*1024*1024: raise ValueError('Pack exceeds 16 MiB limit')
    records.append({'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    return json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)

def tile_xy(lon,lat): return int((lon+180)/360*32768),int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*32768)


def scene_config(data, map_name, size):
    roads=[f for f in data['features'] if f['geometry']['type']=='MultiLineString']
    def choose(kinds):
        candidates=[]
        for feature in roads:
            if feature['properties'].get('highway') not in kinds: continue
            for line in feature['geometry']['coordinates']:
                length=sum(math.dist(a,b) for a,b in zip(line,line[1:]))
                if length>=25:
                    score=min(math.hypot(*p) for p in line) - min(length,100)*.2
                    candidates.append((score,feature,line))
        if not candidates: raise ValueError('No suitable actual mapped actor route')
        return min(candidates,key=lambda item:item[0])[1:]
    actors=[]
    for name,kind,kinds,speed in [('Shibuya_Walker','person',{'footway','pedestrian'},1.4),('Shibuya_Car','vehicle',{'primary','secondary','tertiary','residential'},4.0)]:
        f,line=choose(kinds)
        # Way direction is retained, including mapped one-way direction. Reverse -1.
        if kind=='vehicle' and f['properties'].get('oneway')=='-1': line=list(reversed(line))
        actors.append({'name':name.replace('Shibuya_','Mapped_'),'kind':kind,'speed':speed,'loop':False,'path':[[*point,.08] for point in line],'source_osm_way':f['properties']['osm_id'],'route_note':'Mapped centreline; illustrative motion, not traffic or collision simulation'})
    return {'biome':'city','size':size,'seed':42,'fps':24,'duration':8,'weather':'clear','sun_elevation':45,'sun_azimuth':135,'map_file':map_name,'coordinate_system':'local','origin':data['origin'],'require_real_map':True,'actors':actors}

def write_outputs(output, data, config):
    """Prepare both files before replacing either; roll back a failed pair update."""
    output.parent.mkdir(parents=True, exist_ok=True)
    payloads={output: data, output.with_suffix('.json'): config}
    originals={path: path.read_bytes() if path.exists() else None for path in payloads}
    staged={}; replaced=[]
    def stage(path, contents):
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', suffix='.tmp', delete=False) as f:
            f.write(contents); f.flush(); os.fsync(f.fileno())
            return pathlib.Path(f.name)
    try:
        for path, content in payloads.items():
            staged[path]=stage(path, (json.dumps(content,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        for path, temporary in staged.items():
            os.replace(temporary,path);replaced.append(path)
    except Exception:
        for path in reversed(replaced):
            if originals[path] is None: path.unlink(missing_ok=True)
            else: os.replace(stage(path, originals[path]),path)
        raise
    finally:
        for temporary in staged.values(): temporary.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--lon',type=float,default=139.7005);p.add_argument('--lat',type=float,default=35.6595);p.add_argument('--size',type=float,default=300);p.add_argument('--refresh',action='store_true',help='Redownload cached data packs');p.add_argument('--output',type=pathlib.Path,default=ROOT/'configs/shibuya.geojson');args=p.parse_args()
    if args.output.suffix.lower() != '.geojson': p.error('--output must end in .geojson (companion config uses .json)')
    if not 50<=args.size<=600 or not -85<args.lat<85 or not -180<=args.lon<=180: p.error('size must be 50–600 m and coordinates valid')
    records=[]; ix=fetch(BASE+'index.json',records,args.refresh);h=args.size/2;dy=math.degrees(h/6371008.8);dx=dy/math.cos(math.radians(args.lat))
    x0,y0=tile_xy(args.lon-dx,args.lat+dy);x1,y1=tile_xy(args.lon+dx,args.lat-dy)
    pack=next((p for p in ix['packs'] if p['z']==15 and p['x'][0]<=x0<=x1<=p['x'][1] and p['y'][0]<=y0<=y1<=p['y'][1]),None)
    if not pack: raise ValueError('No public Rokehan pack covers this area. Use scripts/fetch_osm.py --help for the separate OSM downloader; no synthetic fallback was generated.')
    if any(c in pack['base'] for c in (':','..')): raise ValueError('Unsafe pack path')
    tiles=[fetch(f"{BASE}{pack['base']}osm/15/{x}/{y}.json.gz",records,args.refresh) for x in range(x0,x1+1) for y in range(y0,y1+1)]
    bigs=sorted({b for t in tiles for b in t.get('b',[])})
    if len(bigs)>50: raise ValueError('Too many oversized features')
    for b in bigs:
        if not b or any(c not in 'wr0123456789' for c in b): raise ValueError('Unsafe big-feature key')
        tiles.append(fetch(f"{BASE}{pack['base']}big/{b}.json.gz",records,args.refresh))
    data=extract(tiles,[args.lon,args.lat],args.size)
    data['provenance']={'provider':'Rokehan public OSM packs','provider_url':'https://tools.oyasumi-gamedev.com/rokehan/','pack':pack,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'requested_size_m':args.size,'sources':records,'transform':'delta decode; WGS84 to local east/north metres; clip roads; retain whole contained building ways'}
    kinds=[f['geometry']['type'] for f in data['features']]
    if 'Polygon' not in kinds or 'MultiLineString' not in kinds: raise ValueError('Extract lacks real buildings or roads')
    config=scene_config(data,args.output.name,args.size)
    write_outputs(args.output,data,config)
    print(f'{args.output}: {kinds.count("Polygon")} real building ways, {kinds.count("MultiLineString")} real road ways')

if __name__=='__main__': main()
