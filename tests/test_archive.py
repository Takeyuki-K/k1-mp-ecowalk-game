import json
import threading
import sqlite3
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
import pytest
from k1_ecowalk_game.rules import Run,STAGES,RULES
from k1_ecowalk_game.backend import PUBLIC_SHA
from k1_ecowalk_game.archive import check_bundle,recordings,identifier
from k1_ecowalk_game.recording import Recorder
from k1_ecowalk_game.ranking import Handler,initialize_database,entries,save_submission,replay_payload
from k1_ecowalk_game.app import Game,Handler as GameHandler

def sample():
    result=Run(2,elapsed=2,energy_j=100,outcome='finished').result()
    row=dict(t=0.,mode=0,state=[0.]*8,result=result,power_w=50)
    meta=json.loads(json.dumps(dict(stage=2,rules=RULES,public_commit=PUBLIC_SHA,course=STAGES[2])))
    return dict(player='test',metadata=meta,result=result,states=json.dumps(row)+'\n')

def test_wall_attached_boxes():
    for index,(x,y,hx,hy) in enumerate(STAGES[2]['obstacles']):
        assert (y+hy if index%2==0 else y-hy)==(2.5 if index%2==0 else -2.5)
        assert 5-2*hy>=2

def test_replay_bundle_validation():
    p=sample();assert len(check_bundle(p))==1
    p['states']=p['states'].replace('0.0','NaN',1)
    with pytest.raises(ValueError):check_bundle(p)
    for value in ('../secrets','/etc/passwd','a/b',''):
        with pytest.raises(ValueError):identifier(value)

def test_persistent_scores_and_replay_http(tmp_path):
    db=tmp_path/'ranking.db';uploads=tmp_path/'uploads';initialize_database(db)
    p=sample();score=save_submission(db,uploads,{k:v for k,v in p.items() if k!='states'})
    assert not entries(db,uploads,2)['replays'][score['run_id']]
    assert save_submission(db,uploads,p)['run_id']==score['run_id']
    initialize_database(db)
    assert len(entries(db,uploads,2)['entries'])==1
    assert entries(db,uploads,2)['replays'][score['run_id']]
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.token='secret';server.database=db;server.uploads=uploads
    t=threading.Thread(target=server.serve_forever);t.start()
    try:
        upload=Request(f'http://127.0.0.1:{server.server_port}/runs',data=json.dumps(p).encode(),headers={'Authorization':'Bearer secret'})
        with urlopen(upload) as r:assert json.load(r)['run_id']==score['run_id']
        req=Request(f'http://127.0.0.1:{server.server_port}/replays/'+score['run_id'],headers={'Authorization':'Bearer secret'})
        with urlopen(req) as r:assert check_bundle(json.load(r))==check_bundle(p)
    finally:server.shutdown();t.join();server.server_close()

def test_local_saved_record_registration(tmp_path):
    p=sample();r=Recorder(tmp_path/'drive',p['metadata']);r.append(json.loads(p['states']));r.close(p['result'])
    game=Game(SimpleNamespace(output=str(tmp_path),ranking_url=None))
    assert recordings(tmp_path)[0]['outcome']=='finished'
    server=ThreadingHTTPServer(('127.0.0.1',0),GameHandler);server.game=game
    t=threading.Thread(target=server.serve_forever);t.start();base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(Request(base+'/submit',data=json.dumps(dict(id='drive',player='local',include_replay=True)).encode())) as response:
            assert json.load(response)['score']>0
        with urlopen(base+'/ranking/2') as response:
            ranking=json.load(response);assert ranking['entries'][0][0]=='local';assert all(ranking['replays'].values())
        with urlopen(base+'/recordings/drive') as response:assert check_bundle(json.load(response))
    finally:server.shutdown();t.join();server.server_close()
