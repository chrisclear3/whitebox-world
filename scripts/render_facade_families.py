"""Build an original, meter-scale comparison of the eight facade families.

Run from the project root, after the facade implementation is ready:
  blender -b --factory-startup --python-exit-code 1 \
    --python scripts/render_facade_families.py

Outputs are isolated under artifacts/facade_v04; v0.3 demos are never opened.
Use -- --quick for a smaller render, or -- --no-render for geometry/export QA.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from whitebox_world.detail_runtime import group_details, install, setup, update_details
from whitebox_world.export import export_glb
from whitebox_world.facades import add_facades
from whitebox_world.facade_styles import STYLES
from whitebox_world.scene import building, collection, cube, material


# Each sample is an independent synthetic design, not a claimed map reconstruction.
# Both rows have ample separation, so the perspective view exposes two wall faces.
EXAMPLES = (
    dict(style='house', name='House', size=(11, 10), height=7,
         center=(-66, -30), tags={'building': 'house'}, label='PUNCHED WINDOWS'),
    dict(style='apartment', name='Apartment', size=(20, 16), height=18,
         center=(-22, -30), tags={'building': 'apartments'}, label='BALCONY RHYTHM'),
    dict(style='office', name='Office', size=(22, 18), height=21,
         center=(22, -30), tags={'building': 'office'}, label='REGULAR BAYS'),
    dict(style='office_ribbon', name='Ribbon_Office', size=(25, 18), height=24,
         center=(66, -30), tags={'building': 'office'}, label='HORIZONTAL BANDS'),
    dict(style='warehouse', name='Warehouse', size=(28, 23), height=8,
         center=(-66, 45), tags={'building': 'warehouse'}, label='HIGH WINDOWS'),
    dict(style='retail', name='Retail', size=(24, 17), height=7,
         center=(-22, 45), tags={'building': 'retail'}, label='SHOPFRONT GLAZING'),
    dict(style='curtain_wall', name='Curtain_Wall', size=(22, 20), height=38,
         center=(22, 45), tags={'building': 'commercial'}, label='DENSE MULLIONS'),
    dict(style='blank', name='Blank_Wall', size=(22, 18), height=12,
         center=(66, 45), tags={'building': 'service'}, label='SOLID SERVICE WALL'),
)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/facade_v04')
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--no-render', action='store_true')
    parser.add_argument('--skip-closeup', action='store_true')
    parser.add_argument('--seed', type=int, default=202604)
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return parser.parse_args(argv)


def set_material(name, color, roughness=.8):
    mat = material(name)
    mat.diffuse_color = color
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = color
    shader.inputs['Roughness'].default_value = roughness
    return mat


def aim(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()


def camera(name, location, target, col, lens=55):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj.location = location
    data.type = 'PERSP'
    data.lens = lens
    data.clip_start = .1
    data.clip_end = 1500
    aim(obj, target)
    return obj


def text_mesh(name, body, location, size, col, rotation=None, mat='Gallery_Ink'):
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body = body
    curve.align_x = 'CENTER'
    curve.size = size
    curve.space_character = 1.12
    curve.extrude = .004
    obj = bpy.data.objects.new(name, curve)
    col.objects.link(obj)
    obj.location = location
    if rotation is not None:
        obj.rotation_euler = rotation
    curve.materials.append(material(mat))
    # Export labels as ordinary editable geometry, without external font assets.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    obj.select_set(False)
    return obj


def fit_camera(scene, obj, target, objects, margin=.06):
    """Fit actual geometry rather than depending on a fragile fixed framing."""
    corners = [item.matrix_world @ Vector(point) for item in objects
               if item.type == 'MESH' for point in item.bound_box]
    target = Vector(target)
    for _ in range(45):
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, obj, point) for point in corners]
        if all(p.z > 0 and margin < p.x < 1 - margin and margin < p.y < 1 - margin
               for p in projected):
            # Keep the entire gallery centered, instead of leaving a large
            # unused area above the shorter architecture examples.
            cx = (min(p.x for p in projected) + max(p.x for p in projected)) / 2
            cy = (min(p.y for p in projected) + max(p.y for p in projected)) / 2
            obj.data.shift_x += cx - .5
            obj.data.shift_y += (cy - .5) * scene.render.resolution_y / scene.render.resolution_x
            return
        obj.location = target + (obj.location - target) * 1.055
    raise RuntimeError('Comparison camera could not frame all architecture and labels')


def lighting(scene, col):
    world = bpy.data.worlds.new('WW_FacadeGallery_World')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.78, .82, .88, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .65
    scene.world = world
    sun = bpy.data.lights.new('WW_Gallery_Sun', 'SUN')
    sun.energy = 2.6
    sun.angle = math.radians(12)
    obj = bpy.data.objects.new(sun.name, sun)
    col.objects.link(obj)
    obj.rotation_euler = tuple(math.radians(x) for x in (32, -22, -38))
    fill = bpy.data.lights.new('WW_Gallery_Fill', 'AREA')
    fill.energy = 24000
    fill.shape = 'DISK'
    fill.size = 85
    obj = bpy.data.objects.new(fill.name, fill)
    col.objects.link(obj)
    obj.location = (-55, -85, 100)
    aim(obj, (0, 0, 0))


def manifest(scene, anchors, config):
    samples = []
    for spec, obj in zip(EXAMPLES, anchors):
        assert obj.get('ww_facade_style') == spec['style'], (obj.name, dict(obj.items()))
        details = [o for o in scene.objects if o.get('ww_detail')
                   and o.get('ww_lod_parent') == obj.name and o.get('ww_feature') == 'facades']
        samples.append({
            'object': obj.name, 'style': obj['ww_facade_style'],
            'height_m': spec['height'], 'footprint_m': list(spec['size']),
            'stable_seed': obj.get('ww_facade_seed'),
            'family_source': obj.get('ww_facade_style_source'),
            'opening_count': obj.get('ww_facade_openings', 0),
            'paired_near_coarse_shells': bool(obj.get('ww_facade_shell_pair')),
            'source': 'synthetic_demo_manual_family_override',
            'detail_meshes': [{'object': o.name, 'kind': o.get('ww_kind'),
                               'vertices': len(o.data.vertices), 'polygons': len(o.data.polygons)}
                              for o in details if o.type == 'MESH'],
        })
    return {
        'scene': 'Original synthetic architectural family comparison',
        'units': 'meters', 'blender_version': bpy.app.version_string,
        'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [Path(__file__).resolve()] +
                          [ROOT / 'whitebox_world' / name for name in
                           ('facades.py', 'facade_styles.py', 'facade_layout.py',
                            'facade_geometry.py', 'detail_runtime.py', 'export.py')]},
        'render': {'engine': scene.render.engine, 'samples': scene.cycles.samples,
                   'overview_pixels': [scene.render.resolution_x * scene.render.resolution_percentage // 100,
                                       scene.render.resolution_y * scene.render.resolution_percentage // 100]},
        'ground_extent_m': {'blender_and_render': 2000, 'glb_export': 240},
        'config': config, 'samples': samples,
        'limitations': ['Inferred facade design, not surveyed architecture',
                        'No inferred true rooms or interior circulation',
                        'GLB is one fixed detail snapshot; use Blender for camera-driven LOD'],
    }


def export_gallery_glb(filepath, scene, ground):
    """Keep the infinite-looking render floor out of the GLB frame-all bounds."""
    original_scale = ground.scale.copy()
    try:
        ground.scale.x *= .12
        ground.scale.y *= .12
        bpy.context.view_layer.update()
        export_glb(str(filepath), scene)
    finally:
        ground.scale = original_scale
        bpy.context.view_layer.update()


def main():
    args = arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assert set(STYLES) == {s['style'] for s in EXAMPLES}, 'Update gallery for changed style keys'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.frame_start = scene.frame_end = 1
    scene.render.fps = 24
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16 if args.quick else 96
    # Some official distribution builds omit OpenImageDenoise. Plain Cycles
    # sampling keeps this offline comparison portable across those builds.
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 3000
    scene.render.resolution_y = 1800
    scene.render.resolution_percentage = 50 if args.quick else 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    config = {'biome': 'city', 'seed': args.seed, 'actors': [], 'duration': 1 / 24,
              'fps': 24, 'lod_mode': 'ALL', 'lod_distance': 85,
              'export_detail': 'ALL', 'facade_style_overrides': {
                  'Gallery_' + spec['name']: spec['style'] for spec in EXAMPLES}}
    scene['ww_config'] = json.dumps(config, ensure_ascii=False)
    scene['ww_seed'] = args.seed
    scene['ww_gallery_note'] = 'Eight synthetic examples. Facades are inferred design, not measured real buildings.'
    setup(scene, config)
    cols = {name: collection('WW_' + name) for name in
            ('Buildings', 'Facades', 'Gallery', 'Lighting', 'Cameras')}
    set_material('building', (.79, .79, .75, 1))
    set_material('Gallery_Ground', (.63, .64, .62, 1))
    set_material('Gallery_Plinth', (.84, .84, .80, 1))
    ink = set_material('Gallery_Ink', (.012, .028, .035, 1))
    ink.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value = 0
    set_material('Gallery_Accent', (.15, .31, .33, 1))
    ground = cube('WW_Gallery_Ground', (0, 0, -.65), (2000, 2000, .4),
                  'Gallery_Ground', cols['Gallery'])
    anchors = []
    for index, spec in enumerate(EXAMPLES, 1):
        x, y = spec['center']
        width, depth = spec['size']
        footprint = [(x - width / 2, y - depth / 2), (x + width / 2, y - depth / 2),
                     (x + width / 2, y + depth / 2), (x - width / 2, y + depth / 2)]
        obj = building('Gallery_' + spec['name'], footprint, spec['height'], cols['Buildings'])
        obj['ww_source_tags'] = json.dumps(spec['tags'])
        obj['ww_demo_source'] = 'synthetic_architecture_comparison'
        anchors.append(obj)
        cube('WW_Gallery_Plinth_' + spec['style'], (x, y, -.225), (36, 35, .45),
             'Gallery_Plinth', cols['Gallery'])
        cube('WW_Gallery_Accent_' + spec['style'], (x, y - 17.1, .016), (33, .13, .03),
             'Gallery_Accent', cols['Gallery'])
    bpy.context.view_layer.update()
    add_facades(anchors, cols['Facades'], config)
    group_details(scene)
    lighting(scene, cols['Lighting'])
    overview = camera('WW_Facade_Comparison_Camera', (100, -245, 182), (0, 8, 10),
                      cols['Cameras'])
    scene.camera = overview
    labels = []
    for index, spec in enumerate(EXAMPLES, 1):
        x, y = spec['center']
        title = f"{index:02d}  {spec['style'].replace('_', ' ').upper()}"
        labels.append(text_mesh('WW_Label_' + spec['style'], title, (x, y - 22, 2.4),
                                1.90, cols['Gallery'], overview.rotation_euler))
        labels.append(text_mesh('WW_Caption_' + spec['style'],
                                f"{spec['height']} m  /  {spec['label']}",
                                (x, y - 22, .50), 1.10, cols['Gallery'], overview.rotation_euler))
    bpy.context.view_layer.update()
    framing_objects = [o for o in scene.objects if o.type == 'MESH' and o != ground]
    fit_camera(scene, overview, (0, 8, 10), framing_objects)
    apartment = EXAMPLES[1]
    x, y = apartment['center']
    closeup = camera('WW_Facade_Recess_Camera', (x + 24, y - 31, 12),
                     (x + 3, y - 8, 6.8), cols['Cameras'], lens=58)
    closeup['ww_view_note'] = 'Oblique native geometry view: openings, inward reveals, balcony depth.'
    install()
    update_details(scene)
    bpy.context.view_layer.update()
    report = manifest(scene, anchors, config)
    report['outputs'] = {'blend': 'facade_families.blend', 'glb': 'facade_families.glb',
                         'overview': None if args.no_render else 'facade_families.png',
                         'closeup': None if args.no_render or args.skip_closeup else 'facade_recess_closeup.png'}
    export_gallery_glb(output / 'facade_families.glb', scene, ground)
    scene['ww_export_detail'] = 'CURRENT'
    scene.render.filepath = str(output / 'facade_families.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'facade_families.blend'), compress=True)
    if not args.no_render:
        bpy.ops.render.render(write_still=True)
        if not args.skip_closeup:
            scene.camera = closeup
            scene.render.resolution_x = 1800
            scene.render.resolution_y = 1600
            scene.render.filepath = str(output / 'facade_recess_closeup.png')
            # Floating overview labels are presentation only; keep them out of the detail view.
            for obj in labels:
                obj.hide_render = True
            update_details(scene)
            bpy.ops.render.render(write_still=True)
            for obj in labels:
                obj.hide_render = False
            scene.camera = overview
    (output / 'facade_families_manifest.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('FACADE_FAMILIES_OK', output, 'styles=', [item['style'] for item in report['samples']])


if __name__ == '__main__':
    main()
