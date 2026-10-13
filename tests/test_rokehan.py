import json, math, pathlib, sys, unittest, subprocess, tempfile, os
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from fetch_rokehan import decode_coordinates, clip_segment, clipped_lines, extract, scene_config, tile_xy, write_outputs
from whitebox_world.geo import load_map, mapped_actors

class RokehanTests(unittest.TestCase):
    def test_reject_conflicting_output_suffix(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/fetch_rokehan.py'),'--output','bad.json'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('--output must end in .geojson',result.stderr)
    def test_failed_pair_write_restores_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'city.geojson';cfg=path.with_suffix('.json')
            path.write_text('old map');cfg.write_text('old config')
            real_replace=os.replace; calls=[]
            def fail_second(a,b):
                calls.append(b)
                if len(calls)==2: raise OSError('simulated full disk')
                return real_replace(a,b)
            with patch('fetch_rokehan.os.replace',side_effect=fail_second):
                with self.assertRaises(OSError):write_outputs(path,{'new':'map'},{'new':'config'})
            self.assertEqual(path.read_text(),'old map');self.assertEqual(cfg.read_text(),'old config')
            self.assertEqual(len(list(path.parent.iterdir())),2)
    def test_delta_axes(self):
        self.assertEqual(decode_coordinates([356595000,1397005000,100,-200]),[[139.7005,35.6595],[139.70048,35.65951]])
        with self.assertRaises(ValueError):decode_coordinates([1])
    def test_tile(self):self.assertEqual(tile_xy(139.7005,35.6595),(29099,12905))
    def test_clipping(self):
        self.assertEqual(clip_segment([-20,0],[20,0],10),[[-10.,0.],[10.,0.]])
        self.assertIsNone(clip_segment([-20,20],[20,20],10))
        self.assertEqual(len(clipped_lines([[-20,0],[0,0],[20,0]],10)),1)
    def test_unknown_version_fails(self):
        with self.assertRaises(ValueError):extract([{'v':2}], [139.7005,35.6595],300)
    def test_real_fixture(self):
        raw=json.loads((ROOT/'configs/shibuya.geojson').read_text());data=load_map(ROOT/'configs/shibuya.geojson')
        self.assertEqual(len(data['buildings']),105);self.assertEqual(len(data['roads']),244)
        self.assertEqual(data['origin'],[139.7005,35.6595]);self.assertEqual(data['warnings'],[])
        self.assertTrue(all(f['properties']['osm_id']>0 for f in raw['features']))
        self.assertTrue(all('osm_id' in b for b in data['buildings']))
        self.assertIn('ODbL',data['attribution']);self.assertTrue(raw['provenance']['sources'])
        self.assertEqual(raw['provenance']['pack']['name'],'tokyo')
        for f in raw['features']:
            for part in f['geometry']['coordinates']:
                self.assertTrue(all(abs(x)<=150.000001 and abs(y)<=150.000001 for x,y in part))
        self.assertEqual(sum(b['height_source']=='osm_height' for b in data['buildings']),74)
    def test_paths_are_actual_source_roads(self):
        raw=json.loads((ROOT/'configs/shibuya.geojson').read_text())
        cfg=scene_config(raw,'shibuya.geojson',300)
        self.assertTrue(cfg['require_real_map']);self.assertEqual(len(cfg['actors']),2)
        for actor in cfg['actors']:
            source=next(f for f in raw['features'] if f['properties']['osm_id']==actor['source_osm_way'])
            points=[p[:2] for p in actor['path']]
            self.assertTrue(points in source['geometry']['coordinates'] or list(reversed(points)) in source['geometry']['coordinates'])
            self.assertFalse(actor['loop'])
        self.assertEqual(len(mapped_actors(load_map(ROOT/'configs/shibuya.geojson'))),2)
    def test_no_routes_no_synthetic_fallback(self):
        self.assertEqual(mapped_actors({'roads':[]}),[])
        with self.assertRaises(ValueError):scene_config({'features':[]},'empty.geojson',300)

if __name__=='__main__':unittest.main()
