"""Blender integration for independently authored architectural facade grammars.

Pure classification, layout and geometry are separate and testable without bpy.
Near wall shells have real openings; unchanged coarse shells are complementary
LOD meshes. Camera movement changes collection visibility only.
"""
import json
from .facade_layout import plan_facades, plan_facade_layout, residential_type
from .facade_geometry import _mesh_boxes, shell_mesh
from .facade_styles import STYLES

COLORS = {
    'glazing': (.095,.18,.22,1), 'frames': (.55,.61,.63,1),
    'balconies': (.43,.48,.50,1), 'shopfronts': (.25,.39,.40,1),
    'accents': (.58,.62,.61,1), 'spandrels': (.16,.27,.30,1),
}


def add_facades(building_objects, collection, config):
    """Create editable wall, glazing, frame, balcony and accent meshes per shell.

    Only generated, ordered lower/upper-ring shells are supported. Re-running
    against an already detailed shell is a no-op, never an artist edit reset.
    Per-building config['facade_style_overrides'][osm_id or object name] selects
    a grammar. All geographic source tags and the original coarse mesh survive.
    """
    import bpy
    buildings=[]
    for obj in building_objects:
        if obj.type != 'MESH' or obj.get('ww_detail') or obj.get('ww_kind') != 'building':continue
        if obj.get('ww_facade_shell_pair'):continue
        coords=[obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        if len(coords)<6 or len(coords)%2:continue
        n=len(coords)//2; bottom=min(v.z for v in coords);top=max(v.z for v in coords)
        if any(abs(v.z-bottom)>1e-4 for v in coords[:n]) or any(abs(v.z-top)>1e-4 for v in coords[n:]):
            obj['ww_facade_status']='unsupported_edited_shell';continue
        if any((coords[i].xy-coords[i+n].xy).length>1e-4 for i in range(n)):
            obj['ww_facade_status']='unsupported_tapered_shell';continue
        buildings.append((obj,[(v.x,v.y) for v in coords[:n]],bottom,top))
    created=[]; overrides=config.get('facade_style_overrides',{})
    for obj,footprint,bottom,top in buildings:
        low_x=min(p[0] for p in footprint)-2;high_x=max(p[0] for p in footprint)+2
        low_y=min(p[1] for p in footprint)-2;high_y=max(p[1] for p in footprint)+2
        neighbors=[p for other,p,lo,hi in buildings if other!=obj and hi>bottom and lo<top
                   and max(x for x,y in p)>=low_x and min(x for x,y in p)<=high_x
                   and max(y for x,y in p)>=low_y and min(y for x,y in p)<=high_y]
        key=str(obj.get('osm_id',obj.name))
        override=overrides.get(key,overrides.get(obj.name,config.get('facade_style','AUTO')))
        layout=plan_facade_layout(footprint,top,bottom,seed=config.get('seed',42),key=key,
                                neighbors=neighbors,roads=config.get('_detail_roads',[]),
                                tags=obj.get('ww_source_tags',{}),style=override)
        obj['ww_facade_style']=layout['style'];obj['ww_facade_seed']=str(layout['seed'])
        obj['ww_facade_style_source']=layout['provenance'];obj['ww_facade_status']='generated'
        obj['ww_facade_floor_source']=layout.get('floor_source','none')
        obj['ww_facade_openings']=sum(len(e['openings']) for e in layout['edges'])
        if not layout['edges'] or layout['style']=='blank':continue
        obj['ww_facade_shell_pair']=True
        groups=layout['groups']
        for group in ['walls']+list(groups):
            if group!='walls' and not groups[group]:continue
            name=f'{obj.name}_Facade_{group.title()}'
            mesh=bpy.data.meshes.new(name)
            vertices,faces=shell_mesh(layout) if group=='walls' else _mesh_boxes(groups[group])
            mesh.from_pydata(vertices,[],faces);mesh.update()
            detail=bpy.data.objects.new(name,mesh);collection.objects.link(detail)
            detail.parent=obj;detail.matrix_parent_inverse=obj.matrix_world.inverted()
            detail['ww_detail']=True;detail['ww_lod_parent']=obj.name;detail['ww_feature']='facades'
            detail['ww_kind']='facade_'+group;detail['ww_inferred']=True
            detail['ww_facade_style']=layout['style']
            if group=='walls':
                for material in obj.data.materials:mesh.materials.append(material)
                detail['ww_real_apertures']=obj['ww_facade_openings']
            else:
                material_name='WW_Facade_'+group
                mat=bpy.data.materials.get(material_name)
                if mat is None:
                    mat=bpy.data.materials.new(material_name);mat.diffuse_color=COLORS[group];mat.use_nodes=True
                    shader=mat.node_tree.nodes.get('Principled BSDF')
                    shader.inputs['Base Color'].default_value=COLORS[group]
                    shader.inputs['Roughness'].default_value=.24 if group=='glazing' else .70
                    if group=='glazing':shader.inputs['Metallic'].default_value=.28
                mesh.materials.append(mat)
            created.append(detail)
    return created
