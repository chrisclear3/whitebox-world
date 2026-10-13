"""Blender-independent realization of facade box modules and perforated walls."""
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


def wall_boxes(layout, thickness=.30):
    """Rectangle subtraction in wall-local coordinates leaves genuine apertures.

    Every occupied interval becomes a wall prism with jamb/reveal faces. No
    opaque full-height facade face spans the glass, including ribbon windows.
    Caps close the roof and base separately. Interior rooms are not invented.
    """
    boxes=[]
    bottom,top=layout['bottom'],layout['top']
    for edge in layout['edges']:
        openings=edge['openings']; length=edge['length']
        levels=sorted(set([bottom,top]+[o[k] for o in openings for k in ('z0','z1')]))
        a,t,n=edge['a'],edge['tangent'],edge['normal']
        for lo,hi in zip(levels,levels[1:]):
            mid=(lo+hi)/2
            intervals=sorted((o['u0'],o['u1']) for o in openings if o['z0'] < mid < o['z1'])
            cursor=0
            solid=[]
            for left,right in intervals:
                if left>cursor+1e-7:solid.append((cursor,left))
                cursor=max(cursor,right)
            if cursor < length-1e-7:solid.append((cursor,length))
            for left,right in solid:
                u=(left+right)/2
                boxes.append(((a[0]+t[0]*u-n[0]*thickness/2,
                               a[1]+t[1]*u-n[1]*thickness/2,mid),
                              (right-left,thickness,hi-lo),t,n))
    return boxes


def shell_mesh(layout):
    """Welded exterior panels, reveal quads and one roof/base cap.

    Do not realize the subtraction strips as closed boxes: adjacent wall-box
    endcaps coincide with the next wall at corners and cause black z-fighting.
    These surfaces form the exterior architectural skin, not invented rooms.
    """
    vertices,faces=[],[]
    indices={}
    def face(points):
        ids=[]
        for p in points:
            key=tuple(round(v,8) for v in p)
            if key not in indices:indices[key]=len(vertices);vertices.append(tuple(p))
            ids.append(indices[key])
        if len(set(ids))>=3:faces.append(tuple(ids))
    for c,size,t,n in wall_boxes(layout):
        def panel(x,z):
            return (c[0]+x*t[0]+n[0]*size[1]/2,c[1]+x*t[1]+n[1]*size[1]/2,c[2]+z)
        points=[panel(-size[0]/2,-size[2]/2),panel(size[0]/2,-size[2]/2),
                panel(size[0]/2,size[2]/2),panel(-size[0]/2,size[2]/2)]
        # t cross up must point outward for either input winding.
        if t[1]*n[0]-t[0]*n[1]<0:points.reverse()
        face(points)
    for e in layout['edges']:
        a,t,n=e['a'],e['tangent'],e['normal']
        def p(u,z,d):return (a[0]+t[0]*u+n[0]*d,a[1]+t[1]*u+n[1]*d,z)
        for o in e['openings']:
            u0,u1,z0,z1=(o[k] for k in ('u0','u1','z0','z1'))
            outer=[p(u0,z0,0),p(u1,z0,0),p(u1,z1,0),p(u0,z1,0)]
            inner=[p(u0,z0,-.30),p(u1,z0,-.30),p(u1,z1,-.30),p(u0,z1,-.30)]
            for i in range(4):
                j=(i+1)%4
                points=[outer[i],outer[j],inner[j],inner[i]]
                if t[1]*n[0]-t[0]*n[1]<0:points.reverse()
                face(points)
    points=layout['footprint']
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))
    for z,up in ((layout['bottom'],False),(layout['top'],True)):
        cap=[(x,y,z) for x,y in points]
        if (area>0)!=up:cap.reverse()
        face(cap)
    return vertices,faces
