import unittest
import cv2
import numpy as np
from unittest.mock import patch
from threading import Event
from engine import find_last_restart,Cancelled,valid_frame_stamp
from media_io import VideoCapture
from types import SimpleNamespace
from engine import restart_groups,fully_black,Analysis,Cut,keep_ranges


class LastTakeTests(unittest.TestCase):
    def test_late_pts_requires_actual_timestamp_index_not_a_tail_exception(self):
        self.assertFalse(valid_frame_stamp(20011776/15360,78168,60,78169))
        self.assertFalse(valid_frame_stamp(99/60+3/60,99,60,100))
        self.assertFalse(valid_frame_stamp(99/60+4/60,99,60,100))
        self.assertFalse(valid_frame_stamp(50/60+3/60,50,60,100))
        self.assertFalse(valid_frame_stamp(99/60-1/60,99,60,100))
    def reverse(self,mask,fps=60,expected=None):
        class Capture:
            def __init__(self):self.index=0;self.seeks=[];self.reads=0
            def set(self,key,index):self.index=index;self.seeks.append(index);return True
            def get(self,key):return (self.index-1)*1000/fps
            def read(self):
                if self.index>=len(mask):return False,None
                self.reads+=1;value=mask[self.index];self.index+=1
                return True,np.full((1,1,3),int(value),np.uint8)
            def frame_count_hint(self):return len(mask)
        cap=Capture()
        with patch('engine.fully_black',side_effect=lambda f:bool(f[0,0,0])), \
                patch('engine.cv2.resize',side_effect=AssertionError('探索中に縮小しない')), \
                patch('engine.menu_match',side_effect=AssertionError('探索中にポーズ判定しない')):
            got,total=find_last_restart(cap,fps,len(mask) if expected is None else expected)
        self.assertEqual(total,len(mask))
        return got,cap

    def test_reverse_stops_at_latest_retry_across_block_boundary(self):
        mask=[False]*700;mask[100:160]=[True]*60;mask[425:485]=[True]*60
        mask[570:640]=[True]*70
        got,cap=self.reverse(mask)
        self.assertEqual(got,(425,485))
        self.assertEqual(cap.seeks,[460,220])
        self.assertEqual(cap.reads,480)

    def test_reverse_margins_match_forward_reference(self):
        for fps in (30,59.94,60,120):
            for size in range(round(fps*.8),round(fps*1.4)):
                mask=[False]*7+[True]*size+[False]*11
                got,_=self.reverse(mask,fps)
                reference=restart_groups(mask,fps)
                self.assertEqual(got,reference[-1] if reference else None,(fps,size))

    def test_reverse_ignores_initial_and_trailing_incomplete_runs(self):
        mask=[True]*60+[False]*10+[True]*60+[False]*10+[True]*60
        got,_=self.reverse(mask)
        self.assertEqual(got,(70,130))
        self.assertIsNone(self.reverse([True]*60+[False]*10+[True]*60)[0])

    def test_reverse_uses_duration_hint_for_unknown_frame_count(self):
        self.assertEqual(self.reverse([False]*10+[True]*60+[False]*10,expected=0)[0],(10,70))

    def test_reverse_cancellation_before_decode(self):
        cancel=Event();cancel.set()
        with self.assertRaises(Cancelled):find_last_restart(None,60,100,cancel=cancel)

    def test_cfr_grid_ignores_tiny_mux_rate_error_but_keeps_5994(self):
        for average,guessed,want in [(60.005,60,60),(59.94,60,59.94),(60000/1001,60000/1001,60000/1001)]:
            cap=SimpleNamespace(fps=average,stream=SimpleNamespace(guessed_rate=guessed))
            self.assertAlmostEqual(VideoCapture.prefer_cfr_rate(cap),want)

    def test_retry_margin_and_door_pipe_are_separate(self):
        for count in range(50,81):
            with self.subTest(count=count):
                got=restart_groups([False]*10+[True]*count+[False]*10,60)
                self.assertEqual(got,[(10,10+count)] if 57<=count<=63 else [])

    def test_multiple_retries_and_later_doors(self):
        mask=[False]*5+[True]*60+[False]*5+[True]*57+[False]*5+[True]*70+[False]*5
        self.assertEqual(restart_groups(mask,60),[(5,65),(70,127)])

    def test_partial_runs_at_recording_edges_are_not_retries(self):
        self.assertEqual(restart_groups([True]*60+[False]*5+[True]*60,60),[])

    def test_fractional_fps_and_scaled_other_fps(self):
        for fps,count,accepted in [(59.94,57,True),(59.94,63,True),(30,29,True),(30,31,True),
                (30,28,False),(30,35,False),(120,114,True),(120,126,True),(120,140,False)]:
            with self.subTest(fps=fps,count=count):
                self.assertEqual(bool(restart_groups([False]+[True]*count+[False],fps)),accepted)

    def test_black_tolerates_low_codec_noise_but_excludes_fade(self):
        rng=np.random.default_rng(25)
        for frame,expected in [(np.zeros((180,320,3),np.uint8),True),
                (rng.integers(0,4,(180,320,3),dtype=np.uint8),True),
                (np.full((180,320,3),8,np.uint8),False),
                (np.full((180,320,3),30,np.uint8),False)]:
            g=cv2.cvtColor(cv2.resize(frame,(160,90),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
            self.assertEqual(fully_black(frame,g),expected)

    def test_tiny_bright_object_is_not_lost_in_thumbnail(self):
        frame=np.zeros((1080,1920,3),np.uint8);frame[101,401]=255
        g=cv2.cvtColor(cv2.resize(frame,(160,90),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
        self.assertFalse(fully_black(frame,g))

    def test_keep_ranges_starts_at_first_black_frame_and_cuts_inside_take(self):
        a=Analysis('',300,60,1920,1080,[Cut(10,30,12,28),Cut(220,240,225,235)],0,0,
                   take_start=150,last_take_only=True,restart_dark_runs=[(150,210)])
        self.assertEqual(keep_ranges(a),[(150,220),(240,300)])
        a.cuts[1].enabled=False
        self.assertEqual(keep_ranges(a),[(150,300)])

    def test_no_retry_keeps_entire_video(self):
        a=Analysis('',300,60,1920,1080,[],0,0,last_take_only=True)
        self.assertEqual(keep_ranges(a),[(0,300)])
