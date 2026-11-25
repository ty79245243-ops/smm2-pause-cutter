import unittest
from dataclasses import replace
import numpy as np,cv2
from phase30 import CrossTracker,PausePhase,classify,is_30fps
from engine import Analysis,Cut,output_plan,make_close_reference


class Phase30Tests(unittest.TestCase):
    def test_cross_positions_including_clipped_exit(self):
        template=make_close_reference()[12:61,12:61]
        for width,height in ((1920,1080),(1280,720)):
            for x in (1820,1827,1840,1835,1876):
                frame=np.zeros((1080,1920,3),np.uint8)
                frame[44:93,x:min(x+49,1920)]=template[:,:min(49,1920-x),None]
                if width!=1920:frame=cv2.resize(frame,(width,height),interpolation=cv2.INTER_AREA)
                tracker=CrossTracker(template);tracker.add(frame)
                self.assertIsNotNone(tracker.positions[0],(width,x))
                self.assertLessEqual(abs(tracker.positions[0]-x),3)

    def test_four_traces_and_missing_animation(self):
        cut=Cut(5,26,10,20)
        for before in ('odd','even'):
            for after in ('odd','even',None):
                positions=[None]*30
                positions[7:9]=[1835,1840] if before=='odd' else [1847,1827]
                positions[9:21]=[1820]*12
                positions[21]=1835 if after=='even' else 1876 if after=='odd' else None
                decision=classify(positions,cut)
                self.assertEqual((decision.before,decision.after),(before,after))

    def test_30_rate_detection(self):
        for fps in (30,30000/1001,30.000014):self.assertTrue(is_30fps(fps))
        for fps in (24,25,50,60,120):self.assertFalse(is_30fps(fps))

    def test_exact_four_repetition_patterns_and_audio_duration(self):
        for before in ('odd','even'):
            for after in ('odd','even'):
                left=[1,3,5,6] if before=='odd' else [2,4,6]
                right=[7,9,11] if after=='odd' else [8,10,12]
                frames=left+[-1]*3+right;freeze=len(left)-1
                c=Cut(freeze+1,freeze+4,freeze+1,freeze+3)
                phase=PausePhase(c.start,c.end,c.menu_start,c.menu_end,freeze,before,after)
                a=Analysis('',len(frames),30,1920,1080,[c],0,0,phases=[phase])
                p=output_plan(a);kept=[i for s,e in p.ranges for i in range(s,e)]
                actual=[frames[source] for n,source in enumerate(kept) for _ in range(1 if n in p.singles else 2)]
                expected=[x for x in left[:-1] for _ in range(1 if before=='odd' and x==5 else 2)]
                expected +=[6]*(1 if after=='odd' else 2)+[x for x in right for _ in range(2)]
                self.assertEqual(actual,expected,(before,after))
                self.assertEqual(p.frames,len(expected));self.assertEqual(p.fps,60)
                self.assertAlmostEqual(sum(e-s for s,e in p.audio_ranges)/30,p.frames/60)
                self.assertEqual(p.markers,[expected.index(6)])

    def test_disabled_and_edited_cuts_do_not_apply_phase_correction(self):
        c=Cut(4,8,5,7)
        phase=PausePhase(4,8,5,7,3,'odd','odd')
        a=Analysis('',12,30,1920,1080,[c],0,0,phases=[phase])
        c.enabled=False
        self.assertEqual(output_plan(a).frames,24);self.assertEqual(output_plan(a).singles,[])
        c.enabled=True;c.end=9
        self.assertEqual(output_plan(a).singles,[])

    def test_crop_and_close_pauses_do_not_double_shorten_shared_frame(self):
        c1=Cut(2,6,3,5);c2=Cut(7,10,8,9)
        a=Analysis('',12,30,1920,1080,[c1,c2],0,0,phases=[
            PausePhase(2,6,3,5,1,'even','odd'),PausePhase(7,10,8,9,6,'odd','even')])
        self.assertEqual(output_plan(a).singles,[1])
        a.take_start=6
        self.assertEqual(output_plan(a).singles,[])
        self.assertEqual(output_plan(a).markers,[0])

    def test_unknown_side_uses_two_repetitions_without_guessing(self):
        c=Cut(4,8,5,7);a=Analysis('',12,30,1920,1080,[c],0,0,phases=[PausePhase(4,8,5,7,3,'odd',None)])
        self.assertEqual(output_plan(a).singles,[2])
