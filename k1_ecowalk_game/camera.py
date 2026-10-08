"""Render-only camera follow filter; independent of physics and scoring."""
import math
import time

class FollowCamera:
    def __init__(self):
        self.position=None
        self.yaw=0.
        self.updated=None

    def reset(self):
        self.position=None
        self.updated=None

    def follow(self,x,y,yaw,now=None):
        now=time.monotonic() if now is None else now
        if self.position is None or now-self.updated>1 or math.hypot(x-self.position[0],y-self.position[1])>3:
            self.position=[float(x),float(y)];self.yaw=float(yaw)
        else:
            dt=max(0.,now-self.updated)
            move=1-math.exp(-dt/.30)
            turn=1-math.exp(-dt/.45)
            self.position[0]+=move*(x-self.position[0])
            self.position[1]+=move*(y-self.position[1])
            angle=math.atan2(math.sin(yaw-self.yaw),math.cos(yaw-self.yaw))
            self.yaw+=turn*angle
        self.updated=now
        return self.position[0],self.position[1],self.yaw
