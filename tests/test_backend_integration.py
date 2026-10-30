"""Real policy integration checks; skipped when the read-only vendor assets are absent."""
from pathlib import Path
import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    not Path('vendor/k1-mp-ecowalk-public/k1_mp_gait56/runs/final/walk.pt').exists(),
    reason='run setup.sh to install the read-only policy dependencies')


def backend(stage):
    import torch
    from k1_ecowalk_game.backend import Backend
    torch.set_num_threads(1)
    return Backend('vendor/k1-mp-ecowalk-public','vendor/k1-mp-ecowalk-teleop',stage)


@pytest.mark.parametrize('stage',[1,2,3,4])
def test_start_stop_restart_policy_and_state_layout(stage):
    b=backend(stage)
    try:
        assert b.sim.m.nq==32 and b.sim.m.nv==31
        initial=b.sim.env.state[0].copy()
        for _ in range(50):b.step(0,0)
        for _ in range(100):
            power,contacts,trace=b.step(1.2,0)
            assert power>=0 and len(trace)==4 and not contacts
        for _ in range(250):b.step(0,0)
        assert not b.sim.fallen and not b.collision_stop
        assert b.sim.status()['mode']=='stand'
        for _ in range(30):b.step(.9,0)
        assert b.sim.status()['mode']=='walk'
        b.sim.reset()
        np.testing.assert_array_equal(b.sim.env.state[0],initial)
        assert b.sim.sim_time==0
    finally:b.close()


def test_entire_visual_hull_contacts_only_new_scenery():
    old=backend(1);new=backend(4)
    try:
        m0,m1=old.sim.m,new.sim.m
        assert m0.nq==m1.nq and m0.nv==m1.nv and m0.nu==m1.nu
        np.testing.assert_array_equal(m0.body_mass[1:],m1.body_mass[1:len(m0.body_mass)])
        np.testing.assert_array_equal(m0.actuator_gainprm,m1.actuator_gainprm)
        for i in range(m1.ngeom):
            if m1.geom_group[i]==2:
                assert m1.geom_contype[i]&2 and m1.geom_conaffinity[i]==0
        assert not np.any(m0.geom_contype[m0.geom_group==2])
        # Stand -> run changes the active environment before rollout.
        _,_,trace=new.step(2.5,0)
        assert len(trace)==4 and not new.meters[0].trace and new.meters[1].trace
    finally:old.close();new.close()


def test_closing_gate_contact_stops_crushing_trial_and_retry_resets():
    b=backend(4)
    try:
        from k1_ecowalk_game.rules import Run
        r=Run(4)
        for env in (b.sim.g.W,b.sim.g.R):
            env.state[0,1]=6.;env.state[0,0]=5.5
        b.sim.sim_time=5.5
        for _ in range(300):
            power,contacts,_=b.step(0,0)
            r.update(.02,power,b.sim.qpos()[:3],0,0,contacts,
                     b.sim.fallen,False,b.collision_stop)
            assert np.isfinite(b.sim.env.state).all()
            if r.outcome!='playing':break
        assert r.outcome=='collision' and r.collisions>0
        assert max(m.penetration for m in b.meters)<.08
        stopped=b.sim.env.state.copy()
        b.step(4.5,1.)
        np.testing.assert_array_equal(b.sim.env.state,stopped)
    finally:b.close()
    retry=backend(4)
    try:
        assert not retry.collision_stop and retry.sim.sim_time==0
    finally:retry.close()
