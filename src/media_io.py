"""Local-only PyAV video decoding. OpenCV is used only for image processing."""
from pathlib import Path
import av
from array import array
from bisect import bisect_right

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
        self.container=None;self.error=None;self.position=0.;self.next_index=0;self.target=None;self.frame_pts=None;self.frame_keys=[]
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
        index=max(0,int(value))
        self.target=(float(self.frame_pts[index]*self.stream.time_base)-self.start
                     if self.frame_pts is not None and index<len(self.frame_pts) else index/self.fps)
        seek_stamp=round((self.start+self.target)/float(self.stream.time_base))
        if self.frame_pts is not None:
            # Seek by a preceding keyframe's decode timestamp. Its PTS may be
            # late; seeking by that PTS can otherwise skip to the next picture.
            key=bisect_right(self.frame_keys,(seek_stamp,2**63-1))-1
            seek_stamp=self.frame_keys[key][1] if key>=0 else (self.stream.start_time or 0)
        self.container.seek(seek_stamp,
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

    def frame_count_hint(self):
        if not self.isOpened():return 0
        duration=(float(self.stream.duration*self.stream.time_base) if self.stream.duration is not None
                  else float(self.container.duration/av.time_base) if self.container.duration is not None else 0)
        return max(0,round(duration*self.fps))

    def prefer_cfr_rate(self):
        # Mux durations can make average_rate slightly differ from the real
        # CFR timestamp grid (e.g. 60.005 instead of 60). Do not snap 59.94 to 60.
        guessed=float(self.stream.guessed_rate or self.fps)
        if self.fps>0 and abs(guessed-self.fps)/self.fps<.0001:self.fps=guessed
        return self.fps

    def timestamp_matches(self,stamp,index,fps):
        if self.frame_pts is None:return abs(stamp-index/fps)<=.003
        return 0<=index<len(self.frame_pts) and abs(stamp-(float(self.frame_pts[index]*self.stream.time_base)-self.start))<=.003

    def build_frame_index(self,cancel=None):
        """Map ordinal pictures to their actual PTS, only when seeking needs it.

        The common one-picture-per-packet case reads compressed packets only.
        Other packet layouts use decoded PTS without creating RGB images.
        No frame timing is invented and no duplicate frame is inserted.
        """
        self.container.seek(self.stream.start_time or 0,stream=self.stream,backward=True)
        stamps=[];keys=[]
        for packet in self.container.demux(self.stream):
            if cancel is not None and cancel.is_set():return
            if packet.pts is not None:
                stamps.append(packet.pts)
                if packet.is_keyframe:keys.append((packet.pts,min(packet.pts,packet.dts if packet.dts is not None else packet.pts)))
        stamps.sort();expected=self.stream.frames
        if not expected or len(stamps)!=expected or any(a>=b for a,b in zip(stamps,stamps[1:])):
            self.container.seek(self.stream.start_time or 0,stream=self.stream,backward=True)
            stamps=[];keys=[]
            for frame in self.container.decode(self.stream):
                if cancel is not None and cancel.is_set():return
                if frame.pts is None:raise ValueError('動画のフレーム位置を確認する時刻情報がありません。')
                stamps.append(frame.pts)
                if frame.key_frame:keys.append((frame.pts,min(frame.pts,frame.dts if frame.dts is not None else frame.pts)))
            if any(a>=b for a,b in zip(stamps,stamps[1:])):
                raise ValueError('動画のフレーム時刻が重複、または逆転しています。')
        if expected and len(stamps)!=expected:raise ValueError('動画のフレーム数と時刻情報が一致しません。')
        self.frame_pts=array('q',stamps)
        self.frame_keys=sorted(keys)
        self.decoder=iter(())

    def count_frames(self,cancel=None):
        self.container.seek(0,stream=self.stream,backward=True)
        count=0
        for frame in self.container.decode(self.stream):
            if cancel is not None and cancel.is_set():return 0
            count+=1
        self.decoder=iter(())
        return count

