"""Classify the two sampling phases using only the pause-menu close button."""
from dataclasses import dataclass,replace
import cv2


def is_30fps(fps):
    return min(abs(fps-30),abs(fps-30000/1001))<.01


@dataclass(frozen=True)
class PausePhase:
    cut_start:int
    cut_end:int
    menu_start:int
    menu_end:int
    freeze:int
    before:str|None
    after:str|None
    entry_x:int|None=None
    exit_x:int|None=None

    def shifted(self,n):
        return replace(self,cut_start=self.cut_start+n,cut_end=self.cut_end+n,
                       menu_start=self.menu_start+n,menu_end=self.menu_end+n,freeze=self.freeze+n)


class CrossTracker:
    def __init__(self,template):
        # Smooth the reference and ROI together. Upscaled low-resolution
        # recordings have softer edges than the generated geometric cross.
        self.template=cv2.GaussianBlur(template,(3,3),.7)
        self.positions=[]

    def add(self,frame):
        h,w=frame.shape[:2]
        crop=frame[round(28*h/1080):round(110*h/1080),round(1804*w/1920):w]
        if crop.shape[:2]!=(82,116):crop=cv2.resize(crop,(116,82),interpolation=cv2.INTER_LINEAR)
        roi=cv2.GaussianBlur(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(3,3),.7)
        response=cv2.matchTemplate(roi,self.template,cv2.TM_CCOEFF_NORMED)
        _,score,_,point=cv2.minMaxLoc(response)
        if score>=.88 and 42<=point[1]+28<=47:
            self.positions.append(point[0]+1804);return
        # On exit the odd phase shows a cross clipped by the right edge.
        # Search only its known location, not the whole gameplay image.
        best=None
        for x in range(1874,1879):
            width=1920-x
            image=roi[:,x-1804:]
            response=cv2.matchTemplate(image,self.template[:,:width],cv2.TM_CCOEFF_NORMED)
            _,score,_,point=cv2.minMaxLoc(response)
            if score>=.90 and 42<=point[1]+28<=47 and (best is None or score>best[0]):best=(score,x)
        self.positions.append(best[1] if best else None)


def classify(positions,cut):
    n=len(positions);a=cut.menu_start;b=cut.menu_end
    stable=lambda x:x is not None and abs(x-1820)<=3
    first=next((i for i in range(max(0,a-2),min(n-1,a+4))
                if stable(positions[i]) and stable(positions[i+1])),None)
    entry=[] if first is None else [x for x in positions[max(0,first-8):first]
                                    if x is not None and not stable(x)]
    x=entry[-1] if entry else None
    before='odd' if x is not None and abs(x-1840)<=3 else 'even' if x is not None and abs(x-1827)<=3 else None
    moving=[x for x in positions[max(0,b-1):min(n,b+4)] if x is not None and not stable(x)]
    kinds={('even' if abs(x-1835)<=3 else 'odd' if abs(x-1876)<=3 else None) for x in moving}
    after=next(iter(kinds)) if len(kinds)==1 and None not in kinds else None
    return PausePhase(cut.start,cut.end,a,b,cut.start-1,before,after,x,moving[-1] if moving else None)
