import unittest
import numpy as np
import cv2
from unittest.mock import patch
from engine import menu_match,make_close_reference,CLOSE_ROI
from engine import resolve_cuts, menu_groups, Analysis, Cut, keep_ranges, same

class CloseButtonTests(unittest.TestCase):
    def setUp(self):
        self.ref=make_close_reference()
        self.frame=np.zeros((1080,1920,3),np.uint8)
        x,y,X,Y=CLOSE_ROI
        self.frame[y:Y,x:X]=self.ref[:,:,None]
    def test_only_close_button_required_and_no_full_frame_resize(self):
        with patch('engine.cv2.resize',wraps=cv2.resize) as resize:
            self.assertTrue(menu_match(self.frame,self.ref))
            resize.assert_not_called()
        self.assertFalse(menu_match(np.zeros_like(self.frame),self.ref))
    def test_outside_roi_does_not_affect_detection_and_noise_is_tolerated(self):
        rng=np.random.default_rng(8)
        frame=rng.integers(0,256,self.frame.shape,dtype=np.uint8)
        x,y,X,Y=CLOSE_ROI
        noisy=np.clip(self.ref.astype(float)+rng.normal(0,4,self.ref.shape),0,255).astype(np.uint8)
        frame[y:Y,x:X]=noisy[:,:,None]
        self.assertTrue(menu_match(frame,self.ref))
    def test_other_resolution_scales_only_the_roi(self):
        for w,h in ((1280,720),(3840,2160)):
            frame=np.zeros((h,w,3),np.uint8)
            x,y,X,Y=CLOSE_ROI
            x,X=round(x*w/1920),round(X*w/1920)
            y,Y=round(y*h/1080),round(Y*h/1080)
            frame[y:Y,x:X]=cv2.resize(self.ref,(X-x,Y-y))[:,:,None]
            with patch('engine.cv2.resize',wraps=cv2.resize) as resize:
                self.assertTrue(menu_match(frame,self.ref))
                self.assertEqual(resize.call_count,1)
                self.assertEqual(resize.call_args.args[0].shape,(Y-y,X-x))


class DetectionTests(unittest.TestCase):
    def test_duplicate_gameplay_without_menu_is_untouched(self):
        g=np.zeros((200,90,160),np.uint8)
        self.assertEqual(resolve_cuts(g,menu_groups([False]*200),60),[])
    def test_pause_retains_exactly_first_frozen_frame(self):
        rng=np.random.default_rng(7)
        g=rng.integers(0,256,(100,90,160),dtype=np.uint8)
        scene=g[20].copy(); g[20:25]=scene; g[60:62]=scene
        cuts=resolve_cuts(g,[(38,49)],60)
        self.assertEqual((cuts[0].start,cuts[0].end),(21,62))
    def test_restart_is_unchecked(self):
        g=np.random.default_rng(4).integers(0,256,(100,90,160),dtype=np.uint8)
        self.assertFalse(resolve_cuts(g,[(38,49)],60)[0].enabled)
    def test_long_natural_static_run_is_preserved(self):
        g=np.random.default_rng(2).integers(0,256,(150,90,160),dtype=np.uint8)
        g[0:60]=g[1]; g[110:140]=g[1]
        c=resolve_cuts(g,[(74,99)],60)[0]
        self.assertEqual(c.start,60)
        self.assertEqual(c.end,110)
    def test_tiny_sprite_motion_not_hidden_by_average(self):
        a=np.zeros((90,160),np.uint8); b=a.copy(); b[40:43,70:73]=100
        self.assertFalse(same(a,b))
    def test_single_pixel_motion_is_not_hidden_by_average(self):
        a=np.zeros((90,160),np.uint8); b=a.copy(); b[40,70]=100
        self.assertFalse(same(a,b))
    def test_quantization_noise_and_small_luminance_change(self):
        rng=np.random.default_rng(8)
        a=rng.integers(20,235,(90,160),dtype=np.uint8)
        b=np.clip(a.astype(float)+rng.normal(0,3,a.shape)+.5,0,255).astype(np.uint8)
        self.assertTrue(same(a,b))
    def test_compression_artifacts_do_not_require_three_pixel_limit(self):
        rng=np.random.default_rng(12)
        a=rng.integers(20,235,(90,160),dtype=np.uint8)
        b=np.clip(a.astype(float)+rng.normal(0,3,a.shape),0,255).astype(np.uint8)
        self.assertGreater(np.count_nonzero(np.abs(a.astype(float)-b)>8),3)
        self.assertTrue(same(a,b))
    def test_camera_shift_is_not_a_pause(self):
        a=np.random.default_rng(2).integers(0,256,(90,160),dtype=np.uint8)
        self.assertFalse(same(a,np.roll(a,1,axis=1)))
    def test_single_frame_false_match_is_ignored(self):
        self.assertEqual(menu_groups([False,True,False]),[])
    def test_brief_resumption_does_not_merge_menus(self):
        self.assertEqual(menu_groups([True]*3+[False]*2+[True]*3),[(0,2),(5,7)])
    def test_cut_ranges_and_disabled_events(self):
        a=Analysis('',100,60,1920,1080,[Cut(20,30,22,28),Cut(40,50,42,48,False)],0,0)
        self.assertEqual(keep_ranges(a),[(0,20),(30,100)])
        a.cuts.append(Cut(29,40,32,36))
        with self.assertRaises(ValueError): keep_ranges(a)

if __name__=='__main__': unittest.main()
