bl_info={'name':'Whitebox World','author':'Whitebox World contributors','version':(0,1,0),'blender':(4,2,0),'location':'View3D > Sidebar > Whitebox','description':'Editable city and nature blockouts with independent actor motion','category':'3D View'}
import json, os
try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if bpy is not None:
    from bpy.props import EnumProperty,IntProperty,FloatProperty,StringProperty

    class WW_OT_generate(bpy.types.Operator):
        bl_idname='whitebox.generate';bl_label='Generate / Replace Whitebox';bl_options={'REGISTER','UNDO'}
        def invoke(self,context,event):
            return context.window_manager.invoke_confirm(self,event,message='Replace all WW_ collections, including your edits? Save a copy first.')
        def execute(self,context):
            from .scene import build
            s=context.scene
            config={'biome':s.ww_biome,'seed':s.ww_seed,'size':s.ww_size,'weather':s.ww_weather,'sun_elevation':s.ww_elevation,'sun_azimuth':s.ww_azimuth}
            if s.ww_map_file:config.update(map_file=bpy.path.abspath(s.ww_map_file),coordinate_system=s.ww_coordinates)
            try:build(config)
            except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}
            return {'FINISHED'}

    class WW_OT_environment(bpy.types.Operator):
        bl_idname='whitebox.environment';bl_label='Apply Sun / Weather';bl_options={'REGISTER','UNDO'}
        def execute(self,context):
            from .runtime import update_environment
            s=context.scene;s['ww_sun_elevation']=s.ww_elevation;s['ww_sun_azimuth']=s.ww_azimuth;s['ww_active_weather']=s.ww_weather;update_environment(s);return {'FINISHED'}

    class WW_OT_bake(bpy.types.Operator):
        bl_idname='whitebox.bake';bl_label='Bake Actor Animation';bl_options={'REGISTER','UNDO'}
        def execute(self,context):
            from .runtime import bake
            bake(context.scene);return {'FINISHED'}

    class WW_OT_refresh(bpy.types.Operator):
        bl_idname='whitebox.refresh';bl_label='Refresh Actor Pose'
        def execute(self,context):
            from .runtime import update_actors
            update_actors(context.scene);return {'FINISHED'}

    class WW_OT_export(bpy.types.Operator):
        bl_idname='whitebox.export';bl_label='Export Animated GLB'
        filepath:StringProperty(subtype='FILE_PATH',default='whitebox.glb')
        def execute(self,context):
            from .export import export_glb
            export_glb(self.filepath,context.scene);return {'FINISHED'}
        def invoke(self,context,event):context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}

    class WW_PT_panel(bpy.types.Panel):
        bl_label='Whitebox World';bl_idname='WW_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Whitebox'
        def draw(self,context):
            l=self.layout;s=context.scene
            l.label(text='1 · Generate editable environment')
            for prop in ('ww_biome','ww_seed','ww_size','ww_map_file','ww_coordinates'):l.prop(s,prop)
            l.operator('whitebox.generate');l.label(text='Only replaces WW_ collections',icon='INFO')
            l.separator();l.label(text='2 · Sun and weather')
            for prop in ('ww_elevation','ww_azimuth','ww_weather'):l.prop(s,prop)
            l.operator('whitebox.environment')
            l.separator();l.label(text='3 · Select an actor root (Empty)')
            a=context.object
            if a and a.get('ww_actor'):
                for p,label in [('ww_speed','Speed (m/s)'),('ww_offset','Start offset (m)'),('ww_loop','Loop'),('ww_path_name','Path object')]:l.prop(a,'["'+p+'"]',text=label)
                l.operator('whitebox.refresh')
            else:l.label(text='Actor settings appear on selection')
            l.label(text='Edit path vertices in Edit Mode')
            l.operator('whitebox.bake');l.operator('whitebox.export')

    CLASSES=(WW_OT_generate,WW_OT_environment,WW_OT_bake,WW_OT_refresh,WW_OT_export,WW_PT_panel)

    def register():
        for cls in CLASSES:bpy.utils.register_class(cls)
        S=bpy.types.Scene
        S.ww_biome=EnumProperty(name='Biome',items=[(x,x.title(),'') for x in ('city','beach','forest','grassland','mixed')],default='mixed')
        S.ww_weather=EnumProperty(name='Weather',items=[(x,x.title(),'') for x in ('clear','overcast','fog','rain')])
        S.ww_seed=IntProperty(name='Seed',default=42);S.ww_size=FloatProperty(name='Size (m)',default=160,min=20,max=2000)
        S.ww_elevation=FloatProperty(name='Sun elevation',default=35,min=0,max=90);S.ww_azimuth=FloatProperty(name='Sun azimuth',default=135,min=0,max=360)
        S.ww_map_file=StringProperty(name='Map (.geojson/.osm)',subtype='FILE_PATH');S.ww_coordinates=EnumProperty(name='Coordinates',items=[('auto','Auto',''),('local','Local meters',''),('wgs84','WGS84','')])
        from .runtime import install_handler,sync_panel
        install_handler()
        if hasattr(bpy.context,'scene'):sync_panel(bpy.context.scene)
        else:bpy.app.timers.register(lambda: sync_panel(bpy.context.scene),first_interval=0.1)

    def unregister():
        for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
        for p in ('ww_biome','ww_weather','ww_seed','ww_size','ww_elevation','ww_azimuth','ww_map_file','ww_coordinates'):delattr(bpy.types.Scene,p)
        from .runtime import frame_update,load_sync
        if load_sync in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(load_sync)
        if frame_update in bpy.app.handlers.frame_change_post:bpy.app.handlers.frame_change_post.remove(frame_update)
