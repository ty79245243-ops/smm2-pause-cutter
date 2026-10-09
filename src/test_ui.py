import time
import unittest
from unittest.mock import patch
from dataclasses import replace
from types import SimpleNamespace
import tkinter as tk
import numpy as np
from app import App
from engine import Analysis,Cut
from pause_table import ROW_HEIGHT,HEADER_BG,ROW_COLORS,SELECTED_BG


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.app=App(self.root)
        self.preview_patch=patch.object(self.app,'preview');self.preview_patch.start()
        self.error_patch=patch('app.messagebox.showerror');self.error_patch.start()
    def tearDown(self):
        self.preview_patch.stop();self.error_patch.stop();self.root.destroy()
    def ready(self,count=2,expand=True):
        self.app.load_file('test.mp4')
        cuts=[Cut(i*100+20,i*100+40,i*100+25,i*100+35,i%2==0) for i in range(count)]
        self.app.accept_analysis(Analysis('test.mp4',count*100,60,1920,1080,cuts,0,0))
        if expand:self.app.show_details()
        self.root.deiconify();self.root.update()
    def drain(self,seconds=.5):
        end=time.perf_counter()+seconds
        while time.perf_counter()<end:self.root.update();time.sleep(.005)
        self.root.update()
    def test_file_gating_and_bottom_export(self):
        self.assertTrue(self.app.analyze_btn.instate(['disabled']))
        self.assertTrue(all(r.instate(['disabled']) for r in self.app.radios))
        self.assertFalse(self.app.details_visible)
        self.ready()
        self.assertFalse(self.app.analyze_btn.instate(['disabled']))
        self.assertTrue(self.app.details_visible)
        self.assertIs(self.app.export_area.master,self.app.results)
        self.assertEqual(self.app.export_area.pack_info()['side'],'bottom')
        self.assertEqual(self.app.export_btn.pack_info()['side'],'left')
    def test_results_default_to_collapsed_and_export_is_available(self):
        self.ready(expand=False)
        self.assertTrue(self.app.results_visible);self.assertFalse(self.app.details_visible)
        self.assertFalse(self.app.details.winfo_ismapped());self.assertTrue(self.app.export_btn.winfo_ismapped())
        self.assertFalse(self.app.export_btn.instate(['disabled']))
        self.assertIsNone(self.app.preview_thread)
        self.app.review_btn.invoke();self.root.update()
        self.assertTrue(self.app.details_visible)
        self.app.review_btn.invoke();self.root.update()
        self.assertFalse(self.app.details_visible);self.assertTrue(self.app.export_btn.winfo_ismapped())
    def test_filter_indices_and_controls_target_original_rows(self):
        self.ready(6)
        self.app.view_mode.set('review');self.app.apply_filter();self.root.update()
        self.assertEqual(self.app.table.indices,[1,3,5])
        self.assertEqual(self.app.selected(),1)
        self.assertEqual(self.app.table.visible[1].fields['start'].get(),'121')
        self.app.table.visible[3].plan.invoke()
        self.assertTrue(self.app.analysis.cuts[3].enabled);self.assertFalse(self.app.analysis.cuts[1].enabled)
        self.assertEqual(self.app.table.indices,[1,3,5])
        self.app.begin_edit(3,'start');self.root.update()
        e=self.app.table.visible[3].fields['start'];e.delete(0,'end');e.insert(0,'325')
        self.app.finish_edit_event();self.assertEqual(self.app.analysis.cuts[3].start,324)
        self.app.table.visible[3].reset.invoke();self.assertEqual(self.app.analysis.cuts[3].start,320)
        self.assertFalse(self.app.analysis.cuts[3].enabled)
        self.app.view_mode.set('normal');self.app.apply_filter();self.root.update()
        self.assertEqual(self.app.table.indices,[0,2,4])
        self.app.table.visible[2].plan.invoke();self.assertFalse(self.app.analysis.cuts[2].enabled)
        self.assertEqual(self.app.table.indices,[0,2,4])
        self.app.view_mode.set('all');self.app.apply_filter()
        self.assertEqual(self.app.table.indices,list(range(6)))
    def test_filter_commits_edit_and_does_not_change_export_scope(self):
        self.ready(6);self.app.begin_edit(0,'start');self.root.update()
        e=self.app.table.visible[0].fields['start'];e.delete(0,'end');e.insert(0,'25')
        self.app.view_mode.set('review');self.app.apply_filter()
        self.assertEqual(self.app.analysis.cuts[0].start,24);self.assertIsNone(self.app.editor)
        from engine import keep_ranges
        self.assertEqual(sum(b-a for a,b in keep_ranges(self.app.analysis)),544)
        self.app.toggle_details();self.root.update();self.app.toggle_details();self.root.update()
        self.assertEqual(self.app.table.indices,[1,3,5]);self.assertTrue(self.app.analysis.cuts[0].enabled)
    def test_empty_filter_has_message_and_no_selection(self):
        self.ready(1);self.app.view_mode.set('review');self.app.apply_filter();self.root.update()
        self.assertFalse(self.app.table.indices);self.assertIsNone(self.app.selected())
        self.assertTrue(self.app.table.body.find_withtag('empty'))
        self.assertFalse(self.app.export_btn.instate(['disabled']))
    def test_filtered_scrolling_uses_display_positions(self):
        self.ready(60);self.app.view_mode.set('review');self.app.apply_filter();self.root.update()
        table=self.app.table;table.scroll_command('moveto','1.0');self.root.update()
        self.assertIn(59,table.visible);self.assertNotIn(1,table.visible)
        self.assertEqual(table.max_offset,max(0,30*ROW_HEIGHT-table.body.winfo_height()))
        for i,row in table.visible.items():
            self.assertAlmostEqual(table.body.coords(row.window)[1],table.positions[i]*ROW_HEIGHT-table.offset)
    def test_new_analysis_closes_review_and_resets_filter(self):
        self.ready();self.app.view_mode.set('review');self.app.apply_filter()
        a=Analysis('next.mp4',100,60,1920,1080,[Cut(20,40,25,35,True)],0,0)
        self.app.accept_analysis(a);self.root.update()
        self.assertFalse(self.app.details_visible);self.assertEqual(self.app.view_mode.get(),'all')
        self.assertEqual(self.app.table.indices,[0])
    def test_plan_is_a_checkbox_that_toggles(self):
        self.ready();button=self.app.table.visible[0].plan
        self.assertIsInstance(button,tk.Checkbutton)
        self.assertEqual(button['text'],'カット予定')
        self.assertEqual(button['cursor'],'hand2')
        button.invoke();self.assertFalse(self.app.analysis.cuts[0].enabled)
        self.assertEqual(button['text'],'カットしない')
        button.invoke();self.assertTrue(self.app.analysis.cuts[0].enabled)
    def test_selected_row_has_strong_color_difference(self):
        self.ready();self.app.table.select(0)
        self.assertEqual(self.app.table.visible[0].canvas['background'],SELECTED_BG)
        def rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))
        for color in ROW_COLORS:
            self.assertGreater(sum(abs(a-b) for a,b in zip(rgb(color),rgb(SELECTED_BG))),100)
        self.app.table.select(1)
        self.assertEqual(self.app.table.visible[1].canvas['background'],SELECTED_BG)
        self.assertEqual(self.app.table.visible[0].canvas['background'],ROW_COLORS[0])
    def test_click_outside_commits_and_ends_editing_even_on_same_row(self):
        self.ready();self.root.focus_force();self.app.begin_edit(0,'start');self.root.update()
        e=self.app.table.visible[0].fields['start'];e.delete(0,'end');e.insert(0,'25')
        self.app.table.visible[0].note.event_generate('<Button-1>',x=5,y=5);self.root.update()
        self.assertEqual(self.app.analysis.cuts[0].start,24)
        self.assertIsNone(self.app.editor);self.assertIsNot(self.root.focus_get(),e)
        self.app.begin_edit(0,'end');self.root.update()
        e=self.app.table.visible[0].fields['end'];e.delete(0,'end');e.insert(0,'45')
        self.app.caption_labels[0].event_generate('<Button-1>',x=5,y=5);self.root.update()
        self.assertEqual(self.app.analysis.cuts[0].end,45)
        self.assertIsNone(self.app.editor);self.assertIsNot(self.root.focus_get(),e)
    def test_reset_only_enabled_for_changed_rows_and_uncommitted_input(self):
        self.ready();row=self.app.table.visible[0]
        self.assertEqual(row.reset['state'],'disabled')
        self.app.begin_edit(0,'start');self.root.update()
        e=row.fields['start'];e.delete(0,'end');e.insert(0,'26');e.event_generate('<KeyRelease>');self.root.update()
        self.assertEqual(row.reset['state'],'normal');self.assertEqual(row.reset['background'],'#326bad')
        row.reset.invoke();self.root.update()
        self.assertEqual(e.get(),'21');self.assertEqual(row.reset['state'],'disabled')
        row.plan.invoke();self.assertEqual(row.reset['state'],'normal')
        row.reset.invoke();self.assertEqual(row.reset['state'],'disabled')
        self.app.edit_boundary(0,'end','45');self.assertEqual(row.reset['state'],'normal')
        self.app.locked(True);self.assertEqual(row.reset['state'],'disabled')
        self.app.locked(False);self.assertEqual(row.reset['state'],'normal')
    def test_input_is_white_inset_not_whole_cell(self):
        self.ready();row=self.app.table.visible[0];e=row.fields['start']
        self.assertEqual(e['background'],'white')
        self.assertNotEqual(row.canvas['background'],'white')
        self.assertLess(e.winfo_width(),98)
        self.assertGreater(int(e.place_info()['x']),self.app.table.column_bounds(row.width)[1])
    def test_edit_commit_escape_and_invalid_revert(self):
        self.ready();self.app.begin_edit(0,'start');self.root.update()
        e=self.app.table.visible[0].fields['start'];e.delete(0,'end');e.insert(0,'23')
        self.app.finish_edit_event();self.assertEqual(self.app.analysis.cuts[0].start,22)
        self.app.begin_edit(0,'end');self.root.update()
        e=self.app.table.visible[0].fields['end'];e.delete(0,'end');e.insert(0,'45')
        self.app.cancel_edit_event();self.assertEqual(e.get(),'40')
        self.app.begin_edit(0,'end');self.root.update();e.delete(0,'end');e.insert(0,'abc')
        self.assertFalse(self.app.finish_edit());self.assertEqual(e.get(),'40')
    def test_reset_restores_analysis_even_with_invalid_uncommitted_text(self):
        self.ready();original=replace(self.app.analysis.cuts[0])
        self.app.edit_boundary(0,'start','25');self.app.toggle_row(0)
        self.app.begin_edit(0,'end');self.root.update()
        e=self.app.table.visible[0].fields['end'];e.delete(0,'end');e.insert(0,'bad')
        self.app.table.visible[0].reset.invoke()
        self.assertEqual(self.app.analysis.cuts[0],original)
        self.assertEqual(e.get(),'40')
    def test_wheel_moves_through_intermediate_pixel_positions(self):
        self.ready(500);table=self.app.table;header_items=table.header.find_all()
        header_coords=[table.header.coords(i) for i in header_items]
        table.wheel(SimpleNamespace(delta=-120))
        self.assertEqual(table.offset,0)
        table.stop_animation()
        with patch('pause_table.time.perf_counter',return_value=table.last_tick+.016):
            table.tick()
        self.assertGreater(table.offset,0);self.assertLess(table.offset,90)
        self.assertNotEqual(table.offset%ROW_HEIGHT,0)
        self.drain(.4)
        self.assertAlmostEqual(table.offset,90,delta=.5)
        self.assertEqual(header_coords,[table.header.coords(i) for i in header_items])
        self.assertLess(len(table.visible),20)
    def test_fractional_trackpad_input_accumulates_and_end_clamps(self):
        self.ready(60);table=self.app.table
        table.wheel(SimpleNamespace(delta=-15));self.drain()
        self.assertAlmostEqual(table.offset,11.25,delta=.3)
        table.scroll_command('moveto','1.0');self.root.update()
        self.assertEqual(table.offset,table.max_offset)
        self.assertIn(59,table.visible);self.assertNotIn(0,table.visible)
        table.scroll_pixels(1000);self.drain(.1);self.assertEqual(table.offset,table.max_offset)
    def test_scrolling_commits_before_virtualized_row_is_removed(self):
        self.ready(60);self.app.begin_edit(0,'start');self.root.update()
        e=self.app.table.visible[0].fields['start'];e.delete(0,'end');e.insert(0,'25')
        self.app.table.scroll_command('moveto','1.0');self.root.update()
        self.assertEqual(self.app.analysis.cuts[0].start,24)
        self.app.table.scroll_command('moveto','0.0');self.root.update()
        self.assertEqual(self.app.table.visible[0].fields['start'].get(),'25')
    def test_busy_disables_buttons_and_fields(self):
        self.ready();self.app.locked(True);row=self.app.table.visible[0]
        self.assertEqual(row.plan['state'],'disabled');self.assertEqual(row.fields['start']['state'],'disabled')
        before=replace(self.app.analysis.cuts[0]);row.plan.invoke()
        self.assertEqual(before,self.app.analysis.cuts[0])
    def test_header_and_body_have_distinct_backgrounds_and_grid_weights(self):
        self.ready();table=self.app.table
        self.assertEqual(table.header['background'],HEADER_BG)
        self.assertNotIn(HEADER_BG,ROW_COLORS)
        lines=[i for i in table.header.find_all() if table.header.type(i)=='line']
        self.assertTrue(lines)
        self.assertTrue(all(float(table.header.itemcget(i,'width'))==3 for i in lines))
        row=self.app.table.visible[0]
        self.assertTrue(row.canvas.find_withtag('grid'))
    def test_new_file_clears_results_and_animation(self):
        self.ready(60);self.app.table.scroll_pixels(90)
        self.app.load_file('another.mp4')
        self.assertIsNone(self.app.analysis);self.assertFalse(self.app.table.rows)
        self.assertFalse(self.app.table.visible);self.assertIsNone(self.app.table.animation)
        self.assertFalse(self.app.details_visible)
    def test_preview_decoder_does_not_block_scrolling_and_rejects_stale_results(self):
        self.ready(60);self.preview_patch.stop()
        class SlowCapture:
            def __init__(self,*args):pass
            def set(self,*args):pass
            def read(self):time.sleep(.05);return True,np.zeros((90,160,3),np.uint8)
            def release(self):pass
        with patch('app.VideoCapture',SlowCapture):
            start=time.perf_counter();self.app.preview()
            self.assertLess(time.perf_counter()-start,.03)
            self.app.table.scroll_pixels(90);self.drain(.05)
            self.assertGreater(self.app.table.offset,0)
            self.drain(.4);self.assertEqual(len(self.app.photos),3)
            photos=list(self.app.photos)
            self.app.display_preview(self.app.preview_request-1,[(None,0)]*3)
            self.assertEqual(self.app.photos,photos)


if __name__=='__main__':unittest.main()
