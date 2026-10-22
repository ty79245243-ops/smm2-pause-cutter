import tempfile,unittest,json,base64
from pathlib import Path
from unittest.mock import patch
import numpy as np,av
from media_io import VideoCapture,local_video,INPUT_OPTIONS,POS_FRAMES,POS_MSEC,FRAME_COUNT
from engine import ffmpeg_input,ffmpeg,Analysis,export

class SecurityTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_missing_directory_and_playlist_rejected(self):
        for p in (self.root,self.root/'missing.mp4'):
            with self.assertRaises(ValueError):local_video(p)
        p=self.root/'playlist.m3u8';p.write_text('#EXTM3U',encoding='utf-8')
        with self.assertRaises(ValueError):local_video(p)
    def test_renamed_remote_playlist_is_rejected_by_decoder(self):
        p=self.root/'playlist.mp4'
        p.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttps://example.invalid/segment.ts\n#EXT-X-ENDLIST\n',encoding='utf-8')
        cap=VideoCapture(p)
        self.assertFalse(cap.isOpened());self.assertIsNotNone(cap.error)
        self.assertIn('format_whitelist',INPUT_OPTIONS)
        self.assertEqual(INPUT_OPTIONS['protocol_whitelist'],'file,pipe')
    def test_encoder_network_protocols_are_restricted(self):
        self.assertEqual(ffmpeg_input(),['-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,avi'])
    def test_ffmpeg_override_must_be_an_absolute_existing_file(self):
        with patch('engine.Path.is_file',return_value=False),patch.dict('os.environ',{'SMM2_PAUSE_CUTTER_FFMPEG':'ffmpeg.exe'}):
            with self.assertRaises(ValueError):ffmpeg()
    def test_decoder_frame_count_timestamp_and_seek_with_own_video(self):
        path=self.root/'own sample & name.mp4'
        # Ten self-generated solid-color MPEG4 frames, 30fps, pixels i*20.
        # Decode verification does not require an encoder in the decoder DLLs.
        fixture=Path(__file__).parent/'test_fixtures'/'ten_frames.b64'
        path.write_bytes(base64.b64decode(fixture.read_bytes()))
        cap=VideoCapture(path);self.assertTrue(cap.isOpened());self.assertEqual(cap.get(FRAME_COUNT),10)
        self.assertTrue(cap.set(POS_FRAMES,5));ok,frame=cap.read();self.assertTrue(ok)
        self.assertAlmostEqual(cap.get(POS_MSEC),1000*5/30,places=2)
        self.assertLess(abs(int(frame[0,0,0])-100),5);cap.release()

    def test_export_saves_only_mp4_and_ignores_old_cut_report(self):
        source=self.root/'input.mp4'
        source.write_bytes(base64.b64decode((Path(__file__).parent/'test_fixtures/ten_frames.b64').read_bytes()))
        stat=source.stat();a=Analysis(str(source),10,30,160,90,[],stat.st_size,stat.st_mtime_ns)
        def encode(args,*unused):Path(args[-1]).write_bytes(source.read_bytes())
        dst=self.root/'output.mp4'
        with patch('engine.run_ffmpeg',side_effect=encode):export(a,dst)
        self.assertTrue(dst.is_file());self.assertFalse(dst.with_suffix('.cuts.json').exists())
        old=self.root/'another.cuts.json';old.write_text('old record',encoding='utf-8')
        with patch('engine.run_ffmpeg',side_effect=encode):export(a,self.root/'another.mp4')
        self.assertEqual(old.read_text(encoding='utf-8'),'old record')

    def test_actual_pts_index_seeks_both_late_tail_frames_by_ordinal(self):
        shifted=self.root/'shifted.mp4'
        # Self-generated ten solid-color frames, with the last two PTS delayed
        # by one and two clock slots. Decoder-only builds need no encoder.
        shifted.write_bytes(base64.b64decode((Path(__file__).parent/'test_fixtures/ten_frames_delayed_tail.b64').read_bytes()))
        cap=VideoCapture(shifted)
        try:
            cap.build_frame_index()
            self.assertEqual(len(cap.frame_pts),10)
            for index,want in ((8,160),(9,180),(5,100)):
                self.assertTrue(cap.set(POS_FRAMES,index));ok,frame=cap.read();self.assertTrue(ok)
                self.assertLess(abs(float(frame.mean())-want),5)
                self.assertTrue(cap.timestamp_matches(cap.get(POS_MSEC)/1000,index,cap.fps))
        finally:cap.release()

if __name__=='__main__':unittest.main()
