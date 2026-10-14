"""Read-only upstream integration; physical stage geometry and physics-rate metering."""
import importlib
import os
from pathlib import Path
import sys
import numpy as np
from .rules import STAGES
from .camera import FollowCamera

PUBLIC_SHA = '04b1c0fded94dcde76411e6bd9d914a56d41102a'
TELEOP_SHA = 'a5ea3dbf4f97501c18ff090f86ff4cd413f6aaea'

class Meter:
    def __init__(self, roll, env):
        import mujoco as mj
        self.roll, self.e, self.mj = roll, env, mj
        self.d = mj.MjData(env.m)
        self.energy = 0.
        self.contacts = set()
        self.trace = []
        from k1env import ACT_JOINTS
        self.names = ACT_JOINTS
        self.km = np.array([2.2 if any(k in j for k in ('ankle_roll', 'shoulder', 'elbow', 'wrist')) else 4. for j in ACT_JOINTS])

    def rollout(self, models, datas, state0, ctrl, nstep, **kw):
        out = self.roll.rollout(models, datas, state0, ctrl, nstep=nstep, **kw)
        m, d, mj = self.e.m, self.d, self.mj
        states = kw['state']
        for k in range(nstep):
            st = state0[0] if k == 0 else states[0, k-1]
            mj.mj_setState(m, d, st, self.e.spec_state)
            d.ctrl[:] = ctrl[0, k]
            mj.mj_forward(m, d)
            tau = d.qfrc_actuator[self.e.dadr]
            qd = d.qvel[self.e.dadr]
            power = float(np.sum(tau*tau/self.km**2 + np.maximum(tau*qd, 0)))
            self.energy += power * m.opt.timestep
            mj.mj_setState(m, d, states[0, k], self.e.spec_state)
            mj.mj_forward(m, d)
            for c in d.contact:
                if c.dist > 0:
                    continue
                ids = (int(c.geom1), int(c.geom2))
                for gid in ids:
                    name = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, gid) or ''
                    other = ids[1] if gid == ids[0] else ids[0]
                    if name.startswith(('game_obstacle_','game_wall_')) and m.geom_bodyid[other] != 0:
                        self.contacts.add(name)
            self.trace.append((states[0, k].copy(), power))
        return out

class Backend:
    def __init__(self, root, teleop, stage, course=None):
        import mujoco as mj
        self.mj = mj
        self.course = course or STAGES[stage]
        root, teleop = Path(root).expanduser().resolve(), Path(teleop).expanduser().resolve()
        sys.path.insert(0, str(teleop/'k1_ecowalk_ros'))
        sys.path.insert(0, str(root/'k1_mp_gait56'))
        base = importlib.import_module('k1env')
        original = getattr(base, '_game_original_build_spec', base.build_spec)
        base._game_original_build_spec = original
        def stage_spec(*args, **kw):
            spec = original(*args, **kw)
            for i, (x, y, hx, hy) in enumerate(self.course['obstacles']):
                spec.worldbody.add_geom(name=f'game_obstacle_{i}', type=mj.mjtGeom.mjGEOM_BOX,
                                        pos=[x,y,.75], size=[hx,hy,.75], rgba=[.95,.35,.12,.25])
            for i,(x1,y1,x2,y2,width,height) in enumerate(self.course['walls']):
                angle = np.arctan2(y2-y1,x2-x1)
                half_length = np.hypot(x2-x1,y2-y1)/2 + width/2
                spec.worldbody.add_geom(name=f'game_wall_{i}',type=mj.mjtGeom.mjGEOM_BOX,
                    pos=[(x1+x2)/2,(y1+y2)/2,height/2],size=[half_length,width/2,height/2],
                    quat=[np.cos(angle/2),0,0,np.sin(angle/2)],rgba=[.28,.47,.52,.25])
            spec.worldbody.add_geom(name='game_goal', type=mj.mjtGeom.mjGEOM_BOX,
                                    pos=[*self.course['goal'],.005], size=[*self.course['goal_half_size'],.005],
                                    contype=0, conaffinity=0, rgba=[.2,.85,.45,.5])
            return spec
        eco = importlib.import_module('k1env_eco')
        base.build_spec = eco.build_spec = stage_spec
        from k1_ecowalk_ros.sim_core55 import EcoWalk56Sim
        try:
            self.sim = EcoWalk56Sim(str(root))
        finally:
            base.build_spec = eco.build_spec = original
        self.meters = []
        for e in (self.sim.g.W, self.sim.g.R):
            # MotorRollout calls its inner rollout with the motor-limited controls.
            holder = e.roll if hasattr(e.roll, 'roll') else e
            attr = 'roll'
            meter = Meter(getattr(holder, attr), e)
            setattr(holder, attr, meter)
            self.meters.append(meter)
        self.data = mj.MjData(self.sim.m)
        self.renderer = None
        self.camera_mode = 'third'
        self.camera_yaw = 0.0  # Degrees relative to robot heading (render-only)
        self.camera_pitch = 0.0  # Degrees relative to the default camera elevation
        self.follow_camera = FollowCamera()
        self.stage = stage

    def step(self, v, w, brake=False):
        self.sim.set_command(v,w)
        if brake:
            self.sim.brake()
        elif v == 0 and w == 0:
            self.sim.stop()
        else:
            self.sim.start()
        active = int(self.sim.g.mode[0])
        for meter in self.meters:
            meter.energy = 0.; meter.contacts.clear(); meter.trace.clear()
        self.sim.step()
        meter = self.meters[active]
        return meter.energy/self.sim.dt, meter.contacts, meter.trace

    def frame(self, state=None, mode=None, camera_mode=None):
        if self.renderer is None:
            self.sim.m.vis.global_.offwidth = max(1280,self.sim.m.vis.global_.offwidth)
            self.sim.m.vis.global_.offheight = max(720,self.sim.m.vis.global_.offheight)
            self.renderer = self.mj.Renderer(self.sim.m, height=720, width=1280)
        env = self.sim.env if mode is None else (self.sim.g.R if mode else self.sim.g.W)
        self.mj.mj_setState(env.m, self.data, env.state[0] if state is None else state, env.spec_state)
        self.mj.mj_forward(self.sim.m, self.data)
        cam = self.mj.MjvCamera()
        q = self.data.qpos
        qw,qx,qy,qz = q[3:7]
        yaw = float(np.arctan2(2*(qw*qz+qx*qy),1-2*(qy*qy+qz*qz)))
        if (camera_mode or self.camera_mode) == 'first':
            # Free camera near head, looking along robot heading (MuJoCo camera conventions).
            self.follow_camera.reset()
            head = self.sim.m.body('head_link').id
            # Eye is anchored at the front of the head, rather than orbiting
            # around a target in front of the robot. A small forward clearance
            # avoids starting inside the head mesh (geometry dependent).
            heading = np.array([np.cos(yaw), np.sin(yaw), 0.])
            eye = self.data.xpos[head] + .12 * heading + [0., 0., .03]
            azimuth = yaw + np.radians(self.camera_yaw)
            elevation = np.radians(-5. + self.camera_pitch)
            direction = np.array([np.cos(elevation)*np.cos(azimuth),
                                  np.cos(elevation)*np.sin(azimuth),
                                  np.sin(elevation)])
            cam.distance = .3
            cam.lookat[:] = eye + cam.distance * direction
            cam.azimuth = np.degrees(azimuth)
            cam.elevation = np.degrees(elevation)
        else:
            # MuJoCo azimuth is the viewing direction: yaw looks along the robot's heading.
            # Aim below the pelvis so head and feet both fit in the 16:9 frame.
            x,y,heading = self.follow_camera.follow(q[0],q[1],yaw)
            cam.lookat[:] = [x,y,.85]; cam.distance = 4.; cam.azimuth = np.degrees(heading); cam.elevation = -12
        self.renderer.update_scene(self.data, camera=cam)
        self.renderer.scene.flags[self.mj.mjtRndFlag.mjRND_SHADOW] = False
        self.renderer.scene.flags[self.mj.mjtRndFlag.mjRND_REFLECTION] = False
        return self.renderer.render()

    def close_renderer(self):
        if self.renderer:
            self.renderer.close()
            self.renderer = None

    def close(self, close_renderer=True):
        if close_renderer:
            self.close_renderer()
        for e in (self.sim.g.W,self.sim.g.R):
            roll = e.roll
            while hasattr(roll,'roll'):
                roll = roll.roll
            if hasattr(roll,'close'):
                roll.close()
