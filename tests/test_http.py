import json
import threading
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.request import urlopen,Request
from k1_ecowalk_game.app import Handler
from k1_ecowalk_game.ranking import Handler as RankingHandler, initialize_database
from k1_ecowalk_game.rules import Run
import sqlite3

def test_image_cache_query_route():
    class Lock:
        def __enter__(self):pass
        def __exit__(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.game=SimpleNamespace(lock=Lock(),frame_bytes=b'image',render_error=None)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/frame.jpg?t=123') as r:
            assert r.read()==b'image'
    finally:server.shutdown();thread.join();server.server_close()

def test_ranking_submission_and_stage_filter(tmp_path):
    server=ThreadingHTTPServer(('127.0.0.1',0),RankingHandler)
    server.token='test-secret';server.database=str(tmp_path/'db');server.uploads=str(tmp_path/'uploads')
    with sqlite3.connect(server.database) as db:db.execute('CREATE TABLE runs (run_id TEXT PRIMARY KEY,player TEXT,stage INTEGER,score REAL,energy_j REAL,elapsed_s REAL,collisions INTEGER)')
    with sqlite3.connect(server.database) as db:db.execute("INSERT INTO runs VALUES ('old','legacy',1,123,1000,10,0)")
    initialize_database(server.database)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        payload={'player':'player','result':Run(3,energy_j=1000,elapsed=10,outcome='finished').result()}
        req=Request(base+'/runs',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer test-secret'})
        with urlopen(req) as r:assert json.loads(r.read())['score']==5000
        with urlopen(Request(base+'/ranking/3',headers={'Authorization':'Bearer test-secret'})) as r:assert len(json.loads(r.read())['entries'])==1
        with urlopen(Request(base+'/ranking/1',headers={'Authorization':'Bearer test-secret'})) as r:assert json.loads(r.read())['entries']==[]
        with urlopen(Request(base+'/ranking/2',headers={'Authorization':'Bearer test-secret'})) as r:assert json.loads(r.read())['entries']==[]
    finally:server.shutdown();thread.join();server.server_close()


def test_observation_only_blocks_non_observation_routes(tmp_path):
    from urllib.error import HTTPError
    from k1_ecowalk_game.app import Game
    from k1_ecowalk_game.rules import STAGES
    import pytest
    g=Game(SimpleNamespace(output=str(tmp_path),observation_only=True,ranking_url=None))
    g.backend=SimpleNamespace(camera_mode='first',camera_yaw=0.,camera_pitch=0.,
                              course=STAGES[4],sim=SimpleNamespace(status=lambda:{'x':0,'y':0,'yaw':0}))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.game=g
    thread=threading.Thread(target=server.serve_forever);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        for path in ('/recordings','/recordings/test','/recordings/test?x=1',
                     '/ranking/4','/replays/test','/obstacles.py','/../runs/test/states.jsonl'):
            with pytest.raises(HTTPError) as exc:urlopen(base+path)
            assert exc.value.code==403
        for path in ('/replay-local','/replay-import','/replay-ranking','/replay-control','/submit'):
            with pytest.raises(HTTPError) as exc:urlopen(Request(base+path,data=b'{}'))
            assert exc.value.code==403
        with urlopen(Request(base+'/camera',data=b'{"mode":"third","yaw":20,"pitch":-25}')) as r:
            assert json.load(r)['ok']
        assert g.backend.camera_mode=='first'
        assert g.backend.camera_pitch==-25
        with urlopen(Request(base+'/command',data=b'{"v":1.2,"w":0.4}')) as r:
            assert json.load(r)['ok']
        assert g.command==(1.2,.4,False)
        with urlopen(base+'/status') as r:status=json.load(r)
        assert status['observation_only'] and status['directory'] is None
        assert status['course']['obstacles']==[]
        assert 'period' not in json.dumps(status) and 'mocap' not in json.dumps(status)
    finally:server.shutdown();thread.join();server.server_close()
