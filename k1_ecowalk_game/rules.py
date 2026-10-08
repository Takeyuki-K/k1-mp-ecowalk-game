"""Versioned game rules, independent of ROS and MuJoCo."""
from dataclasses import dataclass, field
import math

RULES = 'ecowalk-game-1'
STAGES = {
    1: {'length': 20., 'obstacles': []},
    2: {'length': 10., 'obstacles': [(3., 0., .4, .65), (5.5, -1., .4, .65), (7.5, 1., .4, .65)]},
}

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
        inside = abs(pos[0] - STAGES[self.stage]['length']) <= .75 and abs(pos[1]) <= 1.
        self.inside_goal = bool(inside)
        self.hold = self.hold + dt if inside and speed < .08 and abs(yaw_rate) < .08 and stopped else 0.
        if fallen:
            self.outcome = 'fallen'
        elif abs(pos[1]) > 5 or pos[0] < -2 or pos[0] > STAGES[self.stage]['length'] + 4:
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
