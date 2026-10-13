"""Independent architectural priors, not reconstructed/surveyed building facades.

Classification is stable by map identity, never scene/object iteration order.
Geometry and Blender integration live in separate modules.
"""
import hashlib
import json
import random

STYLES = {
    'house': dict(floor=3.1, pitch=3.2, width=1.30, window=1.55, sill=.85, recess=.18),
    'apartment': dict(floor=3.0, pitch=3.3, width=2.15, window=2.05, sill=.48, recess=.22),
    'office': dict(floor=3.6, pitch=2.55, width=1.80, window=2.05, sill=.80, recess=.22),
    'office_ribbon': dict(floor=3.6, pitch=2.7, width=2.60, window=1.75, sill=.95, recess=.20),
    'warehouse': dict(floor=6.0, pitch=4.8, width=2.9, window=.85, sill=3.7, recess=.16),
    'retail': dict(floor=3.8, pitch=3.5, width=2.75, window=2.65, sill=.22, recess=.24),
    'curtain_wall': dict(floor=3.65, pitch=1.45, width=1.40, window=2.85, sill=.32, recess=.13),
    'blank': dict(floor=4.0, pitch=4, width=0, window=0, sill=0, recess=.18),
}


def source_tags(tags):
    if isinstance(tags, str):
        try: tags = json.loads(tags)
        except (ValueError, TypeError): return {}
    return tags if isinstance(tags, dict) else {}


def stable_seed(seed=42, key=''):
    return int.from_bytes(hashlib.sha256(f'facade-v2:{seed}:{key}'.encode()).digest()[:8], 'big')


def classify_style(tags=None, *, height=12, area=100, seed=42, key='', override=None):
    """Return style and provenance. Explicit override > mapped use > size prior.

    Unknown use is *not* asserted as fact. Thresholds are design heuristics, not
    copied application constants. Optional facade:style is an explicit input.
    """
    tags = source_tags(tags)
    explicit = override if override and override != 'AUTO' else tags.get('facade:style')
    if explicit and explicit != 'AUTO':
        if explicit not in STYLES: raise ValueError('Unknown facade style: '+str(explicit))
        return explicit, 'manual_override'
    rng = random.Random(stable_seed(seed, key))
    kind = str(tags.get('building:use') or tags.get('building', '')).lower()
    if kind in {'roof','garage','garages','parking','service','utility','transformer_tower','construction','shed'}:
        return 'blank', 'mapped_use'
    if kind in {'warehouse','industrial','factory','hangar'}:
        return 'warehouse', 'mapped_use'
    if kind in {'house','detached','semidetached_house','terrace','bungalow','cabin'}:
        return 'house', 'mapped_use'
    if kind in {'apartments','residential','dormitory','hotel'}:
        return 'apartment', 'mapped_use'
    if kind in {'retail','supermarket','kiosk'} or tags.get('shop'):
        return 'retail', 'mapped_use'
    if kind in {'office','commercial'} or tags.get('office'):
        family = 'curtain_wall' if height >= 30 and area >= 150 and rng.random() < .60 else rng.choice(['office','office_ribbon'])
        return family, 'mapped_use_size_prior'
    if kind in {'school','university','hospital','civic','public','station','train_station','transportation'}:
        return 'office', 'mapped_use_generic_institutional'
    if kind in {'church','cathedral','temple','mosque'}:
        return 'blank', 'mapped_use_special_architecture_unsupported'
    if height <= 8 and area < 160:
        choices = ['house','house','retail']
    elif height <= 11 and area > 700:
        choices = ['warehouse','retail','office']
    elif height >= 30 and area > 150:
        choices = ['curtain_wall','curtain_wall','office_ribbon','office','apartment']
    elif height <= 22:
        choices = ['apartment','apartment','office','office_ribbon','retail']
    else:
        choices = ['office','office_ribbon','apartment']
    return rng.choice(choices), 'inferred_size_prior'
