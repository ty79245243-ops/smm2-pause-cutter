import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import numpy as np,av
from media_io import VideoCapture,local_video,INPUT_OPTIONS,POS_FRAMES,POS_MSEC,FRAME_COUNT
from engine import ffmpeg_input,ffmpeg

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
        with av.open(str(path),'w') as container:
            stream=container.add_stream('mpeg4',rate=30);stream.width=160;stream.height=90;stream.pix_fmt='yuv420p'
            for i in range(10):
                frame=av.VideoFrame.from_ndarray(np.full((90,160,3),i*20,np.uint8),format='bgr24')
                for packet in stream.encode(frame):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        cap=VideoCapture(path);self.assertTrue(cap.isOpened());self.assertEqual(cap.get(FRAME_COUNT),10)
        self.assertTrue(cap.set(POS_FRAMES,5));ok,frame=cap.read();self.assertTrue(ok)
        self.assertAlmostEqual(cap.get(POS_MSEC),1000*5/30,places=2)
        self.assertLess(abs(int(frame[0,0,0])-100),5);cap.release()

if __name__=='__main__':unittest.main()
