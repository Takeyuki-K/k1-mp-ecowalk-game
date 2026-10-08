"""Real policy integration check, optional dependencies available after setup.sh."""
import argparse,json
from k1_ecowalk_game.backend import Backend
from k1_ecowalk_game.rules import Run
p=argparse.ArgumentParser();p.add_argument('--ecowalk-root',default='vendor/k1-mp-ecowalk-public');p.add_argument('--teleop-root',default='vendor/k1-mp-ecowalk-teleop');a=p.parse_args()
results=[]
for stage in (1,2):
    b=Backend(a.ecowalk_root,a.teleop_root,stage);r=Run(stage)
    obstacles=[b.mj.mj_id2name(b.sim.m,b.mj.mjtObj.mjOBJ_GEOM,i) for i in range(b.sim.m.ngeom) if (b.mj.mj_id2name(b.sim.m,b.mj.mjtObj.mjOBJ_GEOM,i) or '').startswith('game_obstacle')]
    assert len(obstacles)==(0 if stage==1 else 3)
    for i in range(2500):
        v=0 if stage==1 and b.sim.qpos()[0]>19.25 else .9
        power,contacts,_=b.step(v,0);q=b.sim.qpos();qd=b.sim.qvel()
        r.update(b.sim.dt,power,q[:3],float((qd[:2]**2).sum()**.5),float(qd[5]),contacts,b.sim.fallen,b.sim.status()['mode']=='stand' and v==0)
        if r.outcome!='playing':break
    result=r.result();results.append(result);print(json.dumps(result),flush=True)
    if stage==1:assert r.outcome=='finished' and r.collisions==0
    else:assert r.collisions>0
    b.close()
print(json.dumps(results,indent=2))
