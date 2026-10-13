import unittest,math
from whitebox_world.core import path_pose,validate_config
class MotionTests(unittest.TestCase):
    def test_constant_speed(self):
        for speed in (0,1.4,8):self.assertAlmostEqual(path_pose([(0,0,0),(100,0,0)],speed*3)[0][0],speed*3)
    def test_corner(self):
        p,h=path_pose([(0,0,0),(10,0,0),(10,10,0)],15);self.assertEqual(p,(10,5,0));self.assertAlmostEqual(h,math.pi/2)
    def test_loop_and_clamp(self):
        pts=[(0,0,0),(10,0,0)];self.assertEqual(path_pose(pts,12)[0],(2,0,0));self.assertEqual(path_pose(pts,12,False)[0],(10,0,0))
    def test_invalid(self):
        with self.assertRaises(ValueError):path_pose([(0,0,0),(0,0,0)],3)
        with self.assertRaises(ValueError):validate_config({'biome':'moon'})
        with self.assertRaises(ValueError):validate_config({'actors':[{'speed':-1}]})
if __name__=='__main__':unittest.main()
