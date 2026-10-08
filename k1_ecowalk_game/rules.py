"""Versioned game rules, independent of ROS and MuJoCo."""
from dataclasses import dataclass, field
import math

RULES = 'ecowalk-game-2'
WALL_THICKNESS = .18
WALL_HEIGHT = 1.6

def s_center(x):
    t = max(0., min(1., (x-2.)/24.))
    return 4.8 * math.sin(2*math.pi*t) * math.sin(math.pi*t)

def corridor_walls(points, half_width):
    # Closed perimeter. Wall joints overlap, so there are no shortcuts around the ends.
    offset = half_width + WALL_THICKNESS/2
    left = [(x,y+offset) for x,y in points]
    right = [(x,y-offset) for x,y in points]
    walls = []
    for rail in (left,right):
        for p,q in zip(rail,rail[1:]):
            walls.append([*p,*q,WALL_THICKNESS,WALL_HEIGHT])
    for index in (0,-1):
        walls.append([*left[index],*right[index],WALL_THICKNESS,WALL_HEIGHT])
    return walls

S_CENTERLINE = [[float(x),s_center(float(x))] for x in range(-2,31)]
STAGES = {
    1: {'title':'20m STRAIGHT', 'length':20., 'goal':[20.,0.], 'goal_half_size':[.75,1.],
        'obstacles':[], 'walls':[], 'centerline':[[-2.,0.],[24.,0.]],
        'bounds':[-2.,24.,-5.,5.]},
    2: {'title':'10m OBSTACLES', 'length':10., 'goal':[10.,0.], 'goal_half_size':[.75,1.],
        'obstacles':[(3.,0.,.4,.65),(5.5,-1.,.4,.65),(7.5,1.,.4,.65)],
        'walls':corridor_walls([[-2.,0.],[13.,0.]],2.5),
        'centerline':[[-2.,0.],[13.,0.]], 'corridor_half_width':2.5,
        'bounds':[-2.,13.,-2.5,2.5]},
    3: {'title':'S-CURVE', 'length':28., 'goal':[28.,0.], 'goal_half_size':[.75,1.],
        'obstacles':[], 'walls':corridor_walls(S_CENTERLINE,2.5),
        'centerline':S_CENTERLINE, 'corridor_half_width':2.5,
        'bounds':[-2.,30.,-6.3,6.3]},
}

def course_center(stage, x):
    points = STAGES[stage]['centerline']
    for (ax,ay),(bx,by) in zip(points,points[1:]):
        if ax <= x <= bx:
            return ay + (by-ay)*(x-ax)/(bx-ax)
    return points[0][1] if x < points[0][0] else points[-1][1]

def on_course(stage, pos):
    cfg = STAGES[stage]
    xmin,xmax,ymin,ymax = cfg['bounds']
    x,y = float(pos[0]),float(pos[1])
    if not xmin <= x <= xmax or not ymin <= y <= ymax:
        return False
    width = cfg.get('corridor_half_width')
    return width is None or abs(y-course_center(stage,x)) <= width

@dataclass
class Run:
    stage: int
    energy_j: float = 0.
    elapsed: float = 0.
    collisions: int = 0
    hold: float = 0.
    inside_goal: bool = False
    outcome: str = 'playing'
    active_contacts: set = field(default_factory=set)
    last_contact: dict = field(default_factory=dict)

    def update(self, dt, power, pos, speed, yaw_rate, contacts=(), fallen=False, stopped=False):
        if self.outcome != 'playing':
            return
        if not math.isfinite(power) or power < 0 or dt <= 0:
            raise ValueError('invalid energy sample')
        self.energy_j += power * dt
        self.elapsed += dt
        contacts = set(contacts)
        for contact in contacts:
            if contact not in self.active_contacts and self.elapsed - self.last_contact.get(contact, -1e9) > .3:
                self.collisions += 1
            self.last_contact[contact] = self.elapsed
        self.active_contacts = contacts
        cfg = STAGES[self.stage]
        gx,gy = cfg['goal']; hx,hy = cfg['goal_half_size']
        inside = abs(pos[0]-gx) <= hx and abs(pos[1]-gy) <= hy
        self.inside_goal = bool(inside)
        self.hold = self.hold + dt if inside and speed < .08 and abs(yaw_rate) < .08 and stopped else 0.
        if fallen:
            self.outcome = 'fallen'
        elif not on_course(self.stage,pos):
            self.outcome = 'out_of_bounds'
        elif self.hold >= 1.:
            self.outcome = 'finished'
        elif self.elapsed >= 300:
            self.outcome = 'timeout'

    def result(self, battery_wh=None, usable_fraction=.8, auxiliary_w=0.):
        avg = self.energy_j / self.elapsed if self.elapsed else 0.
        work_wh = (avg + auxiliary_w) * 8
        usable = battery_wh * usable_fraction if battery_wh else None
        return dict(rules=RULES, stage=self.stage, outcome=self.outcome,
                    inside_goal=self.inside_goal, goal_hold_s=self.hold, goal_hold_required_s=1.,
                    elapsed_s=self.elapsed, energy_j=self.energy_j, energy_wh=self.energy_j/3600,
                    average_power_w=avg, collisions=self.collisions,
                    score=max(0., 10000 / (1 + self.energy_j/1000) - 250*self.collisions) if self.outcome == 'finished' else 0.,
                    prediction=dict(label='予測・同じステージを8時間連続反復／休憩・交換時間を除く',
                                    average_power_w=avg+auxiliary_w, energy_8h_wh=work_wh,
                                    battery_wh=battery_wh, usable_fraction=usable_fraction,
                                    auxiliary_w=auxiliary_w,
                                    swaps_8h=max(0, math.ceil(work_wh/usable)-1) if usable else None))
