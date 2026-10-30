"""Private, deterministic scenery. Never serialize this module into player APIs.

Mocap bodies keep robot nq/nv, policy observations and saved robot states unchanged.
All trajectories depend only on MuJoCo simulation time, including replay/seek.
"""
from dataclasses import dataclass
import math
import numpy as np

SCENERY_VERSION = 1


@dataclass(frozen=True)
class MovingBox:
    name: str
    origin: tuple
    half_size: tuple
    rgba: tuple
    period: float
    phase: float
    travel: float
    ramp: float = 0.
    hold: float = 0.

    def position(self, t):
        u = (t + self.phase) % self.period
        if self.ramp:
            # Closed dwell, smooth opening, open dwell, smooth closing.
            closed = self.period - 2*self.ramp - self.hold
            if u < closed:
                f = 0.
            elif u < closed + self.ramp:
                f = .5 - .5*math.cos(math.pi*(u-closed)/self.ramp)
            elif u < closed + self.ramp + self.hold:
                f = 1.
            else:
                f = .5 + .5*math.cos(math.pi*(u-closed-self.ramp-self.hold)/self.ramp)
        else:
            f = math.sin(2*math.pi*u/self.period)
        x, y, z = self.origin
        return (x, y + self.travel*f, z)


def moving_boxes(stage):
    if stage == 4:
        boxes = []
        for label, x, hx, period, phase, ramp, hold, color in (
            ('a', 6., .20, 8.0, 0., .85, 2.2, (.12,.65,.95,1.)),
            ('b', 16., .35, 7.1, 1.3, .70, 1.25, (.95,.62,.08,1.)),
            ('c', 26., .70, 6.3, 2.4, .55, .45, (.85,.18,.32,1.)),
        ):
            for side in (-1, 1):
                boxes.append(MovingBox(f'game_obstacle_{label}_{side}',
                    (x, side*1.25, .95), (hx,1.25,.95), color,
                    period, phase, side*1.15, ramp, hold))
        return tuple(boxes)
    return ()


def add_obstacles(spec, mj, stage):
    if stage != 4:
        return
    # Only new scenery also collides with the full visual hull (including arms).
    # Existing robot-floor, self contacts, masses and actuator settings are intact.
    for geom in spec.geoms:
        if geom.type == mj.mjtGeom.mjGEOM_MESH and geom.group == 2:
            geom.contype |= 2
        if geom.name and any(k in geom.name for k in ('shoulder','elbow','wrist','head')):
            geom.contype |= 2
    options = dict(type=mj.mjtGeom.mjGEOM_BOX, contype=0, conaffinity=3,
                   friction=[.7,.02,.001], group=0)
    for box in moving_boxes(stage):
        body = spec.worldbody.add_body(name=box.name, mocap=True, pos=box.position(0))
        body.add_geom(name=box.name, size=box.half_size, rgba=box.rgba, **options)


class Motion:
    def __init__(self, model, stage):
        self.boxes = moving_boxes(stage)
        self.ids = [int(model.body(box.name).mocapid[0]) for box in self.boxes]

    def apply(self, data, t):
        for index, box in zip(self.ids, self.boxes):
            data.mocap_pos[index] = box.position(t)

    def controls(self, model, initial_state, ctrl, nstep):
        """Supply the position at the start of each actual physics step."""
        result = np.empty((len(initial_state), nstep, model.nu + 3*model.nmocap))
        result[:,:,:model.nu] = ctrl
        for batch, state in enumerate(initial_state):
            for k in range(nstep):
                positions = result[batch,k,model.nu:].reshape(-1,3)
                positions[:] = model.body_pos[model.body_mocapid >= 0]
                for index, box in zip(self.ids, self.boxes):
                    positions[index] = box.position(state[0]+k*model.opt.timestep)
        return result
