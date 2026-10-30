"""Developer-only real-policy validation; not a visual player or agent endpoint.

Run from the repository root with PYTHONDONTWRITEBYTECODE=1. Requires setup.
Outputs aggregate measurements only. Never expose this script or its fixtures to
an agent playing through the observation-only HTTP boundary.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch

from k1_ecowalk_game.backend import Backend
from k1_ecowalk_game.obstacles import moving_boxes
from k1_ecowalk_game.rules import Run, course_center

ROOT = 'vendor/k1-mp-ecowalk-public'
TELEOP = 'vendor/k1-mp-ecowalk-teleop'


def robot_x_bounds(backend, data):
    """Conservative world AABB of every collidable robot hull, including arms."""
    m = backend.sim.m
    ids = np.flatnonzero((m.geom_bodyid > 0) &
        (m.body_mocapid[m.geom_bodyid] < 0) &
        ((m.geom_contype > 0) | (m.geom_conaffinity > 0)))
    rot = data.geom_xmat[ids].reshape(-1,3,3)
    centers = data.geom_xpos[ids] + np.einsum('nij,nj->ni',rot,m.geom_aabb[ids,:3])
    extents = np.einsum('nij,nj->ni',abs(rot),m.geom_aabb[ids,3:])
    return float((centers-extents)[:,0].min()), float((centers+extents)[:,0].max())


def gate_sweep():
    b = Backend(ROOT, TELEOP, 4)
    report = []
    try:
        for wall_index, speeds in ((0,(.6,1.2)),(1,(.9,1.2,1.6)),(2,(1.2,1.6,2.,2.5,3.))):
            box = moving_boxes(4)[wall_index*2]
            gx = box.origin[0]
            for speed in speeds:
                successes = []; collisions = failures = 0
                phases = np.arange(0,box.period,.5)
                for phase in phases:
                    b.sim.reset()
                    b.collision_stop = False
                    # Isolate each gate. Robot placement and clock offsets are
                    # test fixtures, never actions in the player API.
                    for env in (b.sim.g.W,b.sim.g.R):
                        env.state[0,1] += gx-4
                    for _ in range(75):b.step(0,0)
                    for env in (b.sim.g.W,b.sim.g.R):env.state[0,0] = phase
                    b.sim.sim_time = float(phase)
                    hit = set(); velocities = []; passed = False
                    for _ in range(650):
                        _,contacts,_ = b.step(speed,0)
                        hit.update(contacts)
                        assert np.isfinite(b.sim.env.state).all()
                        data = next(m.d for m in b.meters if m.trace)
                        low,high = robot_x_bounds(b,data)
                        if high > gx-box.half_size[0] and low < gx+box.half_size[0]:
                            velocities.append(float(b.sim.qvel()[0]))
                        if low > gx+box.half_size[0]+.05:
                            passed = True
                            break
                        if hit or b.sim.fallen:break
                    if passed and not hit and not b.sim.fallen:
                        successes.append(float(np.mean(velocities)))
                    collisions += bool(hit)
                    failures += bool(b.sim.fallen)
                row = dict(wall='ABC'[wall_index],command_m_s=speed,trials=len(phases),
                           clear_passes=len(successes),contact_trials=collisions,
                           fallen_trials=failures,
                           passing_mean_speed_m_s=round(float(np.mean(successes)),3) if successes else None)
                report.append(row)
                print(json.dumps(row),flush=True)
    finally:b.close()
    return report


def update_run(b, run, v, w):
    power, contacts, _ = b.step(v,w)
    assert np.isfinite(b.sim.env.state).all()
    qd = b.sim.qvel()
    run.update(b.sim.dt,power,b.sim.qpos()[:3],float(np.linalg.norm(qd[:2])),float(qd[5]),
               contacts,b.sim.fallen,b.sim.status()['mode']=='stand' and v==w==0,b.collision_stop)


def regression():
    report=[]
    for stage in (1,2,3):
        b=Backend(ROOT,TELEOP,stage);run=Run(stage)
        try:
            for _ in range(15001):
                s=b.sim.status();x,y=s['x'],s['y'];v=.9;w=0.
                if stage==3:
                    tx=min(x+1.3,28.);ty=course_center(3,tx)
                    angle=math.atan2(ty-y,tx-x)
                    err=math.atan2(math.sin(angle-s['yaw']),math.cos(angle-s['yaw']))
                    w=max(-.7,min(.7,1.5*err))
                if stage in (1,3) and x>(19.25 if stage==1 else 27.25):v=w=0
                update_run(b,run,v,w)
                if run.outcome!='playing':break
            result=run.result();report.append(result);print(json.dumps(result),flush=True)
            if stage in (1,3):assert run.outcome=='finished' and run.collisions==0
            else:assert run.collisions>0  # Deliberately drive into the old obstacle.
        finally:b.close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checks',choices=('all','gates','regression'),default='all')
    parser.add_argument('--output',default='/tmp/k1-vnext-validation.json')
    args=parser.parse_args();torch.set_num_threads(1)
    report={'method':'developer internal-state tests; not visual-only play'}
    for name,fn in (('regression',regression),('gates',gate_sweep)):
        if args.checks in ('all',name):report[name]=fn()
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
