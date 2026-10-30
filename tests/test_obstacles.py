"""Developer tests: never provide these internal fixtures to a player agent."""
import json
import math
import numpy as np
import pytest
import mujoco as mj
from k1_ecowalk_game.obstacles import Motion, moving_boxes, add_obstacles
from k1_ecowalk_game.rules import STAGES, public_course


def test_public_maps_have_no_private_geometry():
    course = public_course(STAGES[4])
    assert course['obstacles'] == []
    assert len(course['walls']) == 4  # Only the uninterrupted perimeter.
    assert course['notice']
    assert 'period' not in json.dumps(course)
    assert 'trajectory' not in json.dumps(course)
    assert 'game_obstacle' not in json.dumps(course)
    assert public_course(dict(course, private_motion={'position':[10,2]})) == course
    assert public_course(STAGES[2])['obstacles'] == STAGES[2]['obstacles']


def test_period_dwell_and_independence():
    boxes = moving_boxes(4)
    for box in boxes:
        for t in np.linspace(0,box.period,101):
            assert box.position(t) == pytest.approx(box.position(t+box.period))
        assert len({box.position(t) for t in np.linspace(0,box.period,50)}) > 2
        closed = box.period-2*box.ramp-box.hold
        t = closed+box.ramp-box.phase
        assert box.position(t+box.hold/2)[1] == pytest.approx(box.origin[1]+box.travel)
        assert box.position(closed/2-box.phase) == pytest.approx(box.origin)
    assert len({b.period for b in boxes}) >= 2
    a,b,c = moving_boxes(4)[::2]
    assert a.hold > b.hold > c.hold


def simple_model(stage):
    spec = mj.MjSpec.from_string('''<mujoco><option timestep="0.005" gravity="0 0 0"/>
    <worldbody><body name="probe" pos="0 0 1"><freejoint/>
    <geom name="probe" type="sphere" size="0.2" mass="10"/></body></worldbody></mujoco>''')
    add_obstacles(spec,mj,stage)
    return spec.compile()


def test_motion_controls_and_replay_are_time_based():
    from mujoco import rollout
    m = simple_model(4); motion = Motion(m,4);d=mj.MjData(m)
    state=np.empty((1,mj.mj_stateSize(m,mj.mjtState.mjSTATE_FULLPHYSICS)))
    d.time=4.7;mj.mj_getState(m,d,state[0],mj.mjtState.mjSTATE_FULLPHYSICS)
    controls=motion.controls(m,state,np.empty((1,4,0)),4)
    with rollout.Rollout() as r:
        output,_=r.rollout(m,d,state,controls,nstep=4,
            control_spec=mj.mjtState.mjSTATE_CTRL|mj.mjtState.mjSTATE_MOCAP_POS)
    for index,box in zip(motion.ids,motion.boxes):
        assert d.mocap_pos[index] == pytest.approx(box.position(4.715))
    # Render reconstruction uses the captured state's clock, not current wall time.
    render=mj.MjData(m);mj.mj_setState(m,render,output[0,-1],mj.mjtState.mjSTATE_FULLPHYSICS)
    motion.apply(render,render.time)
    for index,box in zip(motion.ids,motion.boxes):
        assert render.mocap_pos[index] == pytest.approx(box.position(4.72))
    motion.apply(render,0)
    for index,box in zip(motion.ids,motion.boxes):
        assert render.mocap_pos[index] == pytest.approx(box.position(0))


def test_real_contact_blocks_probe_without_divergence():
    m=simple_model(4);d=mj.MjData(m);motion=Motion(m,4)
    position,velocity=[5.1,0.,.8],[2.,0.,0.]
    d.qpos[:3]=position;d.qvel[:3]=velocity
    touched=False;deepest=0.
    for _ in range(350):
        motion.apply(d,d.time);mj.mj_step(m,d)
        for c in d.contact:
            if c.dist<=0:
                touched=True;deepest=min(deepest,c.dist)
        assert np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()
        assert np.max(abs(d.qvel)) < 30
    assert touched
    assert deepest > -.08
    assert d.qpos[0]<5.8
