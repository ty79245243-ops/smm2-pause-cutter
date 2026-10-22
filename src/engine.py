"""Pause-menu gated cutting. Internal frame intervals are zero-based, end-exclusive."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from fractions import Fraction
import os, subprocess, tempfile, threading
import cv2
import numpy as np
import sys, shutil
from media_io import VideoCapture,local_video,INPUT_OPTIONS

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
# Inclusive coordinates in a 1920x1080 capture, stored here end-exclusive.
CLOSE_ROI = (1809,33,1881,105)
MENU_THRESHOLD = .80
VERSION = '2.7.4'

class Cancelled(Exception): pass

@dataclass
class Cut:
    start: int
    end: int
    menu_start: int
    menu_end: int
    enabled: bool = True
    note: str = 'メニューと前後の同一画面を確認'

@dataclass
class Analysis:
    source: str
    frames: int
    fps: float
    width: int
    height: int
    cuts: list[Cut]
    source_size: int
    source_mtime: int
    take_start: int = 0
    last_take_only: bool = False
    restart_dark_runs: list[tuple[int, int]] = field(default_factory=list)


def fully_black(frame, gray=None):
    """Near-zero decoded pixels only: exclude the fade, tolerate codec noise.

    Screen thumbnails reject ordinary gameplay cheaply. Only candidates need
    a full-resolution maximum so small bright HUD/sprite details cannot vanish
    through downsampling. Input is decoded BGR (video black is normally zero).
    """
    if gray is None:
        # Reverse search does not create resized boundary-cache images.
        h,w=frame.shape[:2]
        gray=cv2.cvtColor(frame[::max(1,h//90),::max(1,w//160)],cv2.COLOR_BGR2GRAY)
    if int(gray.max()) > 4 or float(gray.mean()) > 2:
        return False
    return cv2.minMaxLoc(frame.reshape(-1))[1] <= 12


def restart_groups(black, fps):
    """Complete bounded black runs; 60 +/-3 frames at nominal 60 Hz.

    Scale time windows to the recording FPS (59.94 uses nominal 60). Do not
    count fades or accept truncated runs touching the recording boundaries.
    The 70 +/-3 door/pipe window is explicitly excluded.
    """
    nominal = max(1, round(fps))
    tolerance = 3 * nominal / 60
    groups = []; start = None
    for i, is_black in enumerate(black):
        if is_black and start is None:
            start = i
        elif not is_black and start is not None:
            duration = i - start
            door = abs(duration - 70 * nominal / 60) <= tolerance + 1e-6
            if start > 0 and not door and abs(duration - nominal) <= tolerance + 1e-6:
                groups.append((start, i))
            start = None
    return groups


def valid_frame_stamp(stamp, index, fps, expected):
    return abs(stamp-index/fps)<=.003


def find_last_restart(cap, fps, expected, progress=lambda p,s:None, cancel=None, *, block_seconds=4):
    """Visit blocks from EOF backwards, decode each block forwards from a keyframe.

    Carry black runs across block boundaries. Require nonblack frames on both
    sides and stop at the first qualifying run encountered from the right.
    """
    hint=expected or cap.frame_count_hint()
    if hint<=0:
        progress(0,'動画のフレーム総数を確認しています…')
        hint=cap.count_frames(cancel)
        check_cancel(cancel)
    if hint<=0:raise ValueError('動画に読み取れるフレームがありません。')
    block=max(1,round(fps*block_seconds));upper=hint;total=None
    length=0;run_end=0;right_closed=False;seen=False
    nominal=max(1,round(fps));tolerance=3*nominal/60
    while upper>0:
        check_cancel(cancel)
        lower=max(0,upper-block)
        cap.set(cv2.CAP_PROP_POS_FRAMES,lower)
        flags=[];index=lower
        while total is None or index<upper:
            check_cancel(cancel)
            ok,frame=cap.read()
            if not ok:break
            stamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            matches=(cap.timestamp_matches(stamp,index,fps) if hasattr(cap,'timestamp_matches')
                     else valid_frame_stamp(stamp,index,fps,expected))
            if not matches:
                if hasattr(cap,'build_frame_index') and cap.frame_pts is None:
                    progress(0,'録画のフレーム時刻を確認しています…')
                    cap.build_frame_index(cancel);check_cancel(cancel)
                    return find_last_restart(cap,fps,expected,progress,cancel,block_seconds=block_seconds)
                raise ValueError('動画のフレーム位置を正確に読み取れませんでした。')
            flags.append(fully_black(frame));index+=1
        if total is None:
            if not flags:
                upper=lower;continue
            total=index
            if expected>0 and abs(total-expected)>2:
                raise ValueError('動画を最後まで読めませんでした。破損や非対応形式を確認してください。')
        elif index!=upper:
            raise ValueError('動画のフレーム位置を正確に読み取れませんでした。')
        progress(min(.19,.19*(total-lower)/max(1,total)),f'末尾から暗転を探索中：{lower+1:,}〜{index:,}フレーム')
        for offset in range(len(flags)-1,-1,-1):
            check_cancel(cancel)
            i=lower+offset
            if flags[offset]:
                if length==0:run_end=i+1;right_closed=seen
                length+=1
            else:
                if length:
                    door=abs(length-70*nominal/60)<=tolerance+1e-6
                    if right_closed and not door and abs(length-nominal)<=tolerance+1e-6:
                        return (i+1,run_end),total
                    length=0
                seen=True
        upper=lower
    return None,total or 0

def check_cancel(cancel):
    if cancel and cancel.is_set(): raise Cancelled()

def same(a, b):
    """Noise-tolerant, spatial comparison; never an exact-pixel comparison.

    Slightly smooth quantization noise, then require both whole-screen and
    local agreement. Local difference and SSIM guards preserve small sprite
    movement that a whole-screen average could hide. This comparison only
    establishes boundaries around a positively identified pause menu.
    """
    if float(cv2.absdiff(a,b).mean()) > 3.0: return False
    a=cv2.GaussianBlur(a,(3,3),.7).astype(np.float32)
    b=cv2.GaussianBlur(b,(3,3),.7).astype(np.float32)
    d=cv2.absdiff(a,b)
    if float(d.mean()) > 2.25 or float(d.max()) > 18: return False
    if float(cv2.boxFilter(d,-1,(5,5)).max()) > 8.0: return False
    ma=cv2.GaussianBlur(a,(7,7),1.2); mb=cv2.GaussianBlur(b,(7,7),1.2)
    va=np.maximum(0,cv2.GaussianBlur(a*a,(7,7),1.2)-ma*ma)
    vb=np.maximum(0,cv2.GaussianBlur(b*b,(7,7),1.2)-mb*mb)
    cov=cv2.GaussianBlur(a*b,(7,7),1.2)-ma*mb
    ssim=((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))
    return float(ssim.mean()) >= .990 and float(ssim.min()) >= .80

def make_close_reference():
    """Generic white cross generated from geometry; no game screenshot asset."""
    ref=np.zeros((72,72),np.uint8)
    points=np.array([(12,20),(20,12),(36,28),(52,12),(60,20),(44,36),
                     (60,52),(52,60),(36,44),(20,60),(12,52),(28,36)],np.int32)
    cv2.fillPoly(ref,[points],255,lineType=cv2.LINE_AA)
    return ref


def menu_match(frame, ref):
    """Inspect only the fixed close-button ROI; never resize the full frame."""
    h,w=frame.shape[:2]
    x,y,X,Y=CLOSE_ROI
    x,X=round(x*w/1920),round(X*w/1920)
    y,Y=round(y*h/1080),round(Y*h/1080)
    crop=frame[y:Y,x:X]
    if crop.size==0:return False
    if crop.ndim==3:crop=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    if crop.shape!=ref.shape:
        crop=cv2.resize(crop,(ref.shape[1],ref.shape[0]),interpolation=cv2.INTER_AREA)
    score=cv2.matchTemplate(crop,ref,cv2.TM_CCOEFF_NORMED)
    return float(score[0,0]) >= MENU_THRESHOLD

def menu_groups(mask):
    groups=[]
    for i,b in enumerate(mask):
        if b:
            if groups and i == groups[-1][1]+1: groups[-1][1]=i
            else: groups.append([i,i])
    # A single matching frame is insufficient evidence. Never merge different
    # menus merely because the player resumed briefly between them.
    return [(a,b) for a,b in groups if b-a+1 >= 3]

def resolve_cuts(gray, groups, fps, cancel=None):
    n=len(gray); window=max(20,round(fps*.65)); max_freeze=max(8,round(fps*.25))
    cuts=[]
    for k,(a,b) in enumerate(groups):
        check_cancel(cancel)
        lower=max(0,a-window,groups[k-1][1]+1 if k else 0)
        upper=min(n,b+window+1,groups[k+1][0] if k+1<len(groups) else n)
        # Find the closest identical, clean scene on opposite sides of the menu.
        # If restart/exit/death changes the scene, leave the event unchecked.
        pair=None
        for distance in range(2,2*window+1):
            for left in range(1,window+1):
                right=distance-left; p=a-left; q=b+right
                if right<1 or right>window or p<lower or q>=upper: continue
                if same(gray[p],gray[q]): pair=(p,q); break
            if pair: break
        if pair is None:
            cuts.append(Cut(a,b+1,a,b,False,'要確認：復帰画面が一致しない／境界不明'))
            continue
        p,q=pair
        s=p
        while s>lower and same(gray[s-1],gray[p]): s-=1
        e=q
        while e+1<upper and same(gray[e+1],gray[q]): e+=1
        note='メニューと前後の同一画面を確認'
        # Long motionless gameplay cannot be distinguished from a pause lead-in.
        # Preserve such runs instead of collapsing them.
        if p-s>max_freeze or s==lower:
            s=p; note='メニュー確認（長い前方静止区間は保持）'
        if e-q>max_freeze or e==upper-1:
            e=q-1; note='メニュー確認（長い後方静止区間は保持）'
        start=s+1; end=e+1  # retain first frozen gameplay frame
        if start>=end or (cuts and start<cuts[-1].end):
            cuts.append(Cut(a,b+1,a,b,False,'要確認：区間の重なり'))
        else: cuts.append(Cut(start,end,a,b,True,note))
    return cuts

def analyze(source, progress=lambda p,s:None, cancel=None, *, last_take_only=False):
    source=local_video(source); stat=source.stat()
    cap=VideoCapture(str(source))
    if not cap.isOpened(): raise ValueError('動画を開けません。対応する動画ファイルを選んでください。')
    fps=float(cap.get(cv2.CAP_PROP_FPS)); expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not np.isfinite(fps) or fps<1 or fps>240 or w<160 or h<90:
        cap.release(); raise ValueError('動画のフレームレート／解像度を読み取れません。')
    if w*h>7680*4320:
        cap.release(); raise ValueError('対応する解像度は最大8K（約3300万画素）です。')
    if abs(w/h-16/9)>.035:
        cap.release(); raise ValueError('16:9のゲーム画面が必要です。余白や配信枠を除いてから読み込んでください。')
    ref=make_close_reference()
    mask=[]; times=[]; count=0
    take_start=0; restarts=[]
    try:
        if last_take_only:
            fps=cap.prefer_cfr_rate()
            restart,expected=find_last_restart(cap,fps,expected,progress,cancel)
            if restart:
                take_start=restart[1]-1;restarts=[restart]
            cap.set(cv2.CAP_PROP_POS_FRAMES,take_start)
            progress(.2,f'対象範囲を確定：{take_start+1:,}〜{expected:,}フレーム。ポーズを解析します…')
        remaining=max(0,expected-take_start)
        with tempfile.TemporaryDirectory(prefix='mario_pause_') as tmp:
            if remaining>0 and shutil.disk_usage(tmp).free<remaining*160*90+64*1024*1024:
                raise ValueError('解析用の一時ファイルを保存する空き容量が不足しています。')
            cache=Path(tmp)/'frames.raw'
            with cache.open('wb',buffering=1024*1024) as f:
                while True:
                    check_cancel(cancel)
                    ok,frame=cap.read()
                    if not ok: break
                    mask.append(menu_match(frame,ref))
                    # Only the boundary cache needs a whole-screen thumbnail.
                    small=cv2.resize(frame,(160,90),interpolation=cv2.INTER_AREA)
                    g=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
                    f.write(g.tobytes())
                    times.append(cap.get(cv2.CAP_PROP_POS_MSEC)/1000)
                    count+=1
                    if count%30==0:
                        fraction=count/max(1,remaining)
                        progress(min(.98,(.2+.78*fraction) if last_take_only else fraction),f'ポーズ解析中：{count:,} / 約{remaining:,} フレーム')
            if not count: raise ValueError('動画に読み取れるフレームがありません。')
            if expected>0 and abs(count-remaining)>2: raise ValueError('動画を最後まで読めませんでした。破損や非対応形式を確認してください。')
            if last_take_only and not cap.timestamp_matches(times[0],take_start,fps):
                raise ValueError('切り出し開始のフレーム位置を正確に読み取れませんでした。')
            delta=np.diff(times)
            if len(delta)>10 and np.count_nonzero(np.abs(delta-1/fps)>.003)>max(3,len(delta)*.005):
                raise ValueError('可変フレームレートの動画です。固定フレームレートに変換してから読み込んでください。')
            gray=np.memmap(cache,dtype='uint8',mode='r',shape=(count,90,160))
            try:
                # Resolve only events inside the retained take. Keep original
                # frame numbers for editing, preview and the exported report.
                cuts=resolve_cuts(gray,menu_groups(mask),fps,cancel)
                for cut in cuts:
                    cut.start+=take_start; cut.end+=take_start
                    cut.menu_start+=take_start; cut.menu_end+=take_start
            finally: del gray
    finally: cap.release()
    # Normalize tiny mux-duration differences, but preserve genuine fractional FPS.
    fps=float(Fraction(fps).limit_denominator(1001))
    progress(1,f'解析完了：{len(cuts)}区間を検出')
    return Analysis(str(source),count+take_start,fps,w,h,cuts,stat.st_size,stat.st_mtime_ns,
                    take_start,bool(last_take_only),restarts)

def keep_ranges(analysis):
    if not 0<=analysis.take_start<analysis.frames:
        raise ValueError('最後のテイクの開始位置が動画の範囲外です。')
    cuts=sorted((c for c in analysis.cuts if c.enabled),key=lambda c:c.start)
    out=[]; cursor=0
    for c in cuts:
        if not (0<=c.start<c.end<=analysis.frames) or c.start<cursor:
            raise ValueError('カット区間が範囲外、または重なっています。')
        if cursor<c.start: out.append((cursor,c.start))
        cursor=c.end
    if cursor<analysis.frames: out.append((cursor,analysis.frames))
    out=[(max(a,analysis.take_start),b) for a,b in out if b>analysis.take_start]
    if not out: raise ValueError('全フレームを削除することはできません。')
    return out

def ffmpeg():
    bundled=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))/'bin'/'ffmpeg.exe'
    if bundled.is_file():return str(bundled.resolve())
    configured=os.environ.get('SMM2_PAUSE_CUTTER_FFMPEG')
    if configured:
        path=Path(configured)
        if not path.is_absolute() or not path.is_file():raise ValueError('FFmpegは実在する実行ファイルの絶対パスで指定してください。')
        return str(path.resolve())
    raise RuntimeError('FFmpegが見つかりません。配布ZIPをすべて展開するか、ビルド手順に従ってください。')

def ffmpeg_input():
    return ['-protocol_whitelist',INPUT_OPTIONS['protocol_whitelist'],
            '-format_whitelist',INPUT_OPTIONS['format_whitelist']]


def run_ffmpeg(args, progress, cancel, total):
    proc=subprocess.Popen([ffmpeg(),'-hide_banner','-nostdin','-loglevel','error',
        '-progress','pipe:1','-nostats',*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,encoding='utf-8',errors='replace',creationflags=CREATE_NO_WINDOW)
    errors=[]
    def drain():
        for line in proc.stderr:
            errors.append(line)
            if len(errors)>100: errors.pop(0)
    def watch():
        while proc.poll() is None:
            if cancel and cancel.wait(.15): proc.terminate(); break
            if not cancel: threading.Event().wait(.15)
    errthread=threading.Thread(target=drain,daemon=True); errthread.start()
    watcher=threading.Thread(target=watch,daemon=True); watcher.start()
    try:
        for line in proc.stdout:
            if line.startswith('frame='):
                frame=int(line.strip().split('=',1)[1]); progress(min(.99,frame/max(total,1)),f'書き出し中：{frame:,} / {total:,} フレーム')
        code=proc.wait(); errthread.join(); check_cancel(cancel)
        if code: raise RuntimeError('FFmpegの書き出しに失敗しました。\n'+''.join(errors)[-3000:])
    finally:
        if proc.poll() is None: proc.terminate(); proc.wait()
        proc.stdout.close(); proc.stderr.close()

def has_audio(source):
    p=subprocess.run([ffmpeg(),'-hide_banner',*ffmpeg_input(),'-i',str(local_video(source))],capture_output=True,
        text=True,encoding='utf-8',errors='replace',creationflags=CREATE_NO_WINDOW)
    return 'Audio:' in p.stderr

def export(analysis, destination, mute=True, progress=lambda p,s:None, cancel=None):
    dst=Path(destination).resolve(); src=Path(analysis.source).resolve()
    if dst==src: raise ValueError('元動画と同じ場所には保存できません。')
    if dst.exists(): raise ValueError('同名の出力ファイルがあります。別の名前を選んでください。')
    stat=src.stat()
    if stat.st_size!=analysis.source_size or stat.st_mtime_ns!=analysis.source_mtime:
        raise ValueError('解析後に元動画が変更されました。もう一度解析してください。')
    ranges=keep_ranges(analysis); total=sum(b-a for a,b in ranges)
    dst.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mario_export_',dir=dst.parent) as tmp:
        temp=Path(tmp)/'result.mp4'; graphfile=Path(tmp)/'filters.txt'
        fps=Fraction(analysis.fps).limit_denominator(1001)
        expr='+'.join(f'between(n,{a},{b-1})' for a,b in ranges)
        graph=f"[0:v:0]select='{expr}',setpts=N/({fps.numerator}/{fps.denominator}*TB)[v]"
        audio=not mute and has_audio(src)
        if audio:
            pieces=[]; links=[]
            for i,(a,b) in enumerate(ranges):
                pieces.append(f'[ax{i}]atrim=start={a/analysis.fps:.9f}:end={b/analysis.fps:.9f},asetpts=PTS-STARTPTS[a{i}]')
                links.append(f'[a{i}]')
            # Pad a shorter audio stream so all retained video intervals exist.
            graph+=';[0:a:0]asetpts=PTS-STARTPTS,apad,asplit='+str(len(ranges))+''.join(f'[ax{i}]' for i in range(len(ranges)))
            graph+=';'+ ';'.join(pieces)+';'+''.join(links)+f'concat=n={len(ranges)}:v=0:a=1[a]'
        graphfile.write_text(graph,encoding='utf-8')
        args=[*ffmpeg_input(),'-i',str(src),'-/filter_complex',str(graphfile),'-map','[v]']
        args+=['-map','[a]','-c:a','aac','-b:a','192k'] if audio else ['-an']
        args+=['-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',
            '-r',str(fps),'-fps_mode','cfr','-movflags','+faststart','-y',str(temp)]
        run_ffmpeg(args,progress,cancel,total)
        check_cancel(cancel)
        verify=VideoCapture(str(temp))
        got=int(verify.get(cv2.CAP_PROP_FRAME_COUNT)); verify.release()
        if got!=total: raise RuntimeError(f'書き出し検証でフレーム数が一致しません：期待 {total} / 実際 {got}')
        data={'app_version':VERSION,'detector':'close-button ROI + spatial SSIM v3','source':str(src),'output':str(dst),'frame_numbering':'1-based inclusive',
            'fps':analysis.fps,'input_frames':analysis.frames,'output_frames':total,
            'last_take_only':analysis.last_take_only,'take_start_frame':analysis.take_start+1,
            'restart_dark_runs':[{'from':a+1,'through':b} for a,b in analysis.restart_dark_runs],
            'audio':'muted' if not audio else 'retained and cut',
            'cuts':[{'delete_from':c.start+1,'delete_through':c.end,'enabled':c.enabled,'note':c.note,
                'menu_from':c.menu_start+1,'menu_through':c.menu_end+1} for c in analysis.cuts]}
        # Never replace an existing user file, including a racing writer.
        temp.rename(dst)
    progress(1,f'完了：{total:,}フレーム / {total/analysis.fps:.2f}秒')
    return data

