import unittest
from engine import Analysis,Cut,pause_marker_frames


class PauseMarkerTests(unittest.TestCase):
    def make(self,cuts,start=0,frames=200):
        return Analysis('',frames,60,1920,1080,cuts,0,0,take_start=start,last_take_only=bool(start))

    def test_retained_press_frame_is_marked_not_first_frame_after_cut(self):
        a=self.make([Cut(21,62,38,49)],frames=100)
        self.assertEqual(pause_marker_frames(a),[20])

    def test_multiple_cuts_account_for_preceding_deleted_frames(self):
        a=self.make([Cut(20,30,22,28),Cut(50,70,52,68)])
        self.assertEqual(pause_marker_frames(a),[19,39])

    def test_disabled_and_no_cuts_do_not_mark_any_frame(self):
        self.assertEqual(pause_marker_frames(self.make([])),[])
        self.assertEqual(pause_marker_frames(self.make([Cut(20,30,22,28,False)])),[])

    def test_last_take_crop_omits_older_events_and_offsets_retained_events(self):
        a=self.make([Cut(20,30,22,28),Cut(110,120,112,118)],start=100)
        self.assertEqual(pause_marker_frames(a),[9])

    def test_marker_can_be_on_very_first_output_frame(self):
        a=self.make([Cut(101,120,112,118)],start=100)
        self.assertEqual(pause_marker_frames(a),[0])

    def test_removed_preceding_frame_is_not_marked(self):
        a=self.make([Cut(20,30,22,28),Cut(30,40,32,38)])
        self.assertEqual(pause_marker_frames(a),[19])
        self.assertEqual(pause_marker_frames(self.make([Cut(0,10,2,8)])),[])
