"""Pure, deterministic motion and configuration helpers (meters, seconds, radians)."""
import math


def path_pose(points, distance, loop=True):
    if len(points) < 2:
        raise ValueError('A path needs at least two points')
    segments = [(a, b, math.dist(a, b)) for a, b in zip(points, points[1:])]
    total = sum(s[2] for s in segments)
    if total <= 1e-9:
        raise ValueError('Path length must be positive')
    d = distance % total if loop else min(max(distance, 0), total)
    for a, b, length in segments:
        if length and d <= length:
            t = d / length
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(3)), math.atan2(b[1]-a[1], b[0]-a[0])
        d -= length
    a,b,_ = segments[-1]
    return tuple(b), math.atan2(b[1]-a[1], b[0]-a[0])


def validate_config(config):
    if config.get('biome', 'city') not in ('city','beach','forest','grassland','mixed'):
        raise ValueError('Unknown biome')
    if not 20 <= float(config.get('size',160)) <= 2000:
        raise ValueError('size must be 20–2000 meters')
    if not 1 <= int(config.get('fps',24)) <= 120:
        raise ValueError('fps must be 1–120')
    if not 1 <= float(config.get('duration',12)) <= 600:
        raise ValueError('duration must be 1–600 seconds')
    for actor in config.get('actors',[]):
        if actor.get('kind','person') not in ('person','vehicle'):
            raise ValueError('Actor kind must be person or vehicle')
        points=actor.get('path',[[-60,-7,0],[60,-7,0]])
        if len(points)<2 or any(len(v) not in (2,3) or any(not math.isfinite(float(x)) for x in v) for v in points):
            raise ValueError('Actor paths need at least two finite 2D/3D points')
        normalized=[tuple(v) if len(v)==3 else (*v,0) for v in points]
        path_pose(normalized,0)
        if not math.isfinite(float(actor.get('speed',1.4))) or float(actor.get('speed',1.4)) < 0:
            raise ValueError('Actor speed cannot be negative')
    return config
