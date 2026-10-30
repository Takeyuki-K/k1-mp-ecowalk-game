import math
import pytest
from k1_ecowalk_game.rules import Run
from k1_ecowalk_game.ranking import validate

def test_goal_requires_physical_stop_and_hold():
    r=Run(1)
    for _ in range(60):r.update(.02,100,[20,0,1],0,0,stopped=False)
    assert r.outcome=='playing'
    for _ in range(51):r.update(.02,100,[20,0,1],0,0,stopped=True)
    assert r.outcome=='finished'
    assert r.result()['average_power_w']==pytest.approx(100)

def test_contact_episodes_and_energy_units():
    r=Run(2)
    for contacts in ({'a'},{'a'},set(),{'a','b'}):r.update(1,3600,[0,0,1],1,0,contacts)
    assert r.collisions==3
    assert r.result()['energy_wh']==4
    r.outcome='finished'
    assert r.result(400,1)['prediction']['swaps_8h']==71

def test_failure_cannot_score():
    r=Run(1);r.update(.02,100,[20,0,1],0,0,fallen=True,stopped=True)
    assert r.result()['score']==0

def test_server_recomputes_score_and_rejects_nan():
    r=Run(1,energy_j=1000,elapsed=10,outcome='finished').result();r['score']=1e9
    assert validate({'player':'test','result':r})[1]['score']==5000
    r['energy_j']=math.nan
    with pytest.raises(ValueError):validate({'player':'test','result':r})

def test_goal_overlay_progress_resets_when_leaving():
    r=Run(1)
    r.update(.2,100,[20,0,1],0,0,stopped=True)
    result=r.result()
    assert result['inside_goal'] and result['goal_hold_s']==pytest.approx(.2)
    r.update(.2,100,[18,0,1],0,0,stopped=True)
    assert not r.result()['inside_goal'] and r.result()['goal_hold_s']==0

def test_goal_status_can_be_serialized_from_numpy_state():
    import json
    import numpy as np
    r=Run(1)
    r.update(.02,100,np.array([20.,0.,1.]),0,0,stopped=True)
    assert json.loads(json.dumps(r.result()))['inside_goal'] is True

def test_enclosed_courses_and_s_curve():
    from k1_ecowalk_game.rules import STAGES, on_course, course_center
    assert len(STAGES[2]['walls'])==4
    assert not on_course(2,[10,3,1])
    assert len(STAGES[3]['walls'])==66
    for x in range(-2,31):
        y=course_center(3,x)
        assert on_course(3,[x,y,1])
        assert on_course(3,[x,y+2,1])
        assert not on_course(3,[x,y+2.6,1])
    assert not on_course(3,[10,0,1])
    r=Run(3)
    for _ in range(51):r.update(.02,100,[28,0,1],0,0,stopped=True)
    assert r.outcome=='finished'


def test_deep_contact_stops_new_stage_without_scoring():
    r=Run(4)
    r.update(.02,100,[6,0,1],0,0,contacts={'wall'},collision_stop=True)
    assert r.outcome=='collision' and r.collisions==1 and r.result()['score']==0
    before=r.elapsed
    r.update(.02,100,[7,0,1],1,0)
    assert r.elapsed==before
