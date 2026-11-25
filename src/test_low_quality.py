"""Self-generated regressions; no game screenshots are distributed."""
import unittest
import cv2
import numpy as np
from engine import same,compressed_same,resolve_cuts,timestamp_fps,make_close_reference
from phase30 import CrossTracker,is_30fps


class LowQualityTests(unittest.TestCase):
    def test_cfr_uses_timestamp_grid_despite_short_tail(self):
        times=np.arange(750,dtype=float)/30
        times[-1]-=1/60
        self.assertEqual(timestamp_fps(times,30.04008016),30)
        self.assertTrue(is_30fps(timestamp_fps(times,30.04008016)))

    def test_fractional_rate_is_not_rounded_to_integer(self):
        fps=30000/1001
        self.assertAlmostEqual(timestamp_fps(np.arange(750)/fps,29.98),fps)
        self.assertEqual(timestamp_fps([0]*20,30),30)
        self.assertEqual(timestamp_fps(np.arange(750)/25,30),30)

    def test_quantized_timestamp_ticks_do_not_change_nominal_rate(self):
        times=np.round(np.arange(807)/30*29996)/29996
        self.assertEqual(timestamp_fps(times,30.00001487),30)

    def test_timestamp_median_does_not_hide_variable_rate(self):
        times=np.cumsum([0]+[1/30,1/20]*50)
        fps=timestamp_fps(times,30)
        self.assertGreater(np.count_nonzero(abs(np.diff(times)-1/fps)>.003),3)

    def test_blurred_cross_at_low_resolutions_and_clipped_edge(self):
        template=make_close_reference()[12:61,12:61]
        for width,height in ((1280,720),(854,480)):
            for x in (1820,1827,1840,1835,1876):
                frame=np.zeros((1080,1920,3),np.uint8)
                frame[44:93,x:min(x+49,1920)]=template[:,:min(49,1920-x),None]
                frame=cv2.resize(frame,(width,height),interpolation=cv2.INTER_AREA)
                frame=cv2.GaussianBlur(frame,(3,3),.6)
                tracker=CrossTracker(template);tracker.add(frame)
                self.assertIsNotNone(tracker.positions[0],(width,x))
                self.assertLessEqual(abs(tracker.positions[0]-x),3)

    def scenes(self):
        rng=np.random.default_rng(81)
        a=rng.integers(20,235,(90,160),dtype=np.uint8)
        b=np.clip(a.astype(float)+rng.normal(0,6,a.shape),0,255).astype(np.uint8)
        return a,b

    def test_compression_fallback_with_temporal_freeze(self):
        a,b=self.scenes()
        self.assertFalse(same(a,b));self.assertTrue(compressed_same(a,b))
        g=np.random.default_rng(42).integers(0,256,(100,90,160),dtype=np.uint8)
        g[20:25]=a;g[60:62]=b
        cut=resolve_cuts(g,[(38,49)],60)[0]
        self.assertTrue(cut.enabled);self.assertEqual((cut.start,cut.end),(21,62))

    def test_fallback_requires_repeated_clean_picture(self):
        a,b=self.scenes()
        g=np.random.default_rng(42).integers(0,256,(100,90,160),dtype=np.uint8)
        g[20]=a;g[60:62]=b
        self.assertFalse(resolve_cuts(g,[(38,49)],60)[0].enabled)

    def test_real_motion_and_concentrated_changes_remain_rejected(self):
        a,b=self.scenes()
        self.assertFalse(compressed_same(a,np.roll(b,1,axis=1)))
        b[40:45,70:75]=255
        self.assertFalse(compressed_same(a,b))
        blank=np.zeros((90,160),np.uint8);tiny=blank.copy();tiny[40,70]=100
        self.assertFalse(compressed_same(blank,tiny))


if __name__=='__main__':unittest.main()
