"""Local-only PyAV video decoding. OpenCV is used only for image processing."""
from pathlib import Path
import av

ALLOWED_SUFFIXES={'.mp4','.m4v','.mov','.mkv','.avi'}
INPUT_OPTIONS={'protocol_whitelist':'file,pipe','format_whitelist':'mov,matroska,avi'}
# Numeric properties preserve the small capture interface used by the UI.
POS_MSEC,POS_FRAMES,WIDTH,HEIGHT,FPS,FRAME_COUNT=0,1,3,4,5,7


def local_video(source):
    path=Path(source).resolve()
    if not path.is_file():raise ValueError('通常の動画ファイルを選んでください。')
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError('MP4 / MOV / MKV / AVI / M4V の動画ファイルを選んでください。')
    return path


class VideoCapture:
    def __init__(self,source):
        self.container=None;self.error=None;self.position=0.;self.next_index=0;self.target=None
        try:
            path=local_video(source)
            self.container=av.open(str(path),mode='r',options=INPUT_OPTIONS)
            self.stream=next(iter(self.container.streams.video))
            self.stream.thread_type="AUTO"
            self.fps=float(self.stream.average_rate or self.stream.guessed_rate or 0)
            self.start=float((self.stream.start_time or 0)*self.stream.time_base)
            self.decoder=iter(self.container.decode(self.stream))
        except Exception as e:
            self.error=e;self.release()

    def isOpened(self):return self.container is not None

    def get(self,key):
        if not self.isOpened():return 0
        return {WIDTH:self.stream.width,HEIGHT:self.stream.height,FPS:self.fps,
                FRAME_COUNT:self.stream.frames or 0,POS_MSEC:self.position*1000,
                POS_FRAMES:self.next_index}.get(key,0)

    def set(self,key,value):
        if key!=POS_FRAMES or not self.isOpened() or self.fps<=0:return False
        self.target=max(0,float(value))/self.fps
        self.container.seek(round((self.start+self.target)/float(self.stream.time_base)),
                            stream=self.stream,backward=True,any_frame=False)
        self.decoder=iter(self.container.decode(self.stream))
        self.next_index=max(0,int(value));return True

    def read(self):
        if not self.isOpened():return False,None
        for frame in self.decoder:
            position=float(frame.pts*frame.time_base)-self.start if frame.pts is not None else self.next_index/self.fps
            if self.target is not None and position+(.25/self.fps)<self.target:continue
            self.target=None;self.position=position;self.next_index+=1
            return True,frame.to_ndarray(format='bgr24')
        return False,None

    def release(self):
        if self.container is not None:self.container.close();self.container=None

