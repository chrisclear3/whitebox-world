import pathlib,zipfile
root=pathlib.Path(__file__).resolve().parents[1]
with zipfile.ZipFile(root/'artifacts/whitebox_world_addon.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((root/'whitebox_world').glob('*.py')):z.write(p,p.relative_to(root))
print(root/'artifacts/whitebox_world_addon.zip')
