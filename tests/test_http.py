import json
import threading
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.request import urlopen,Request
from k1_ecowalk_game.app import Handler
from k1_ecowalk_game.ranking import Handler as RankingHandler
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
    thread=threading.Thread(target=server.serve_forever);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        payload={'player':'player','result':Run(1,energy_j=1000,elapsed=10,outcome='finished').result()}
        req=Request(base+'/runs',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer test-secret'})
        with urlopen(req) as r:assert json.loads(r.read())['score']==5000
        with urlopen(Request(base+'/ranking/1',headers={'Authorization':'Bearer test-secret'})) as r:assert len(json.loads(r.read())['entries'])==1
        with urlopen(Request(base+'/ranking/2',headers={'Authorization':'Bearer test-secret'})) as r:assert json.loads(r.read())['entries']==[]
    finally:server.shutdown();thread.join();server.server_close()
