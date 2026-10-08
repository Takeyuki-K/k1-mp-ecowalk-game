"""Small invitation-only, self-reported leaderboard. Deploy behind HTTPS for online use."""
import argparse
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .rules import Run, RULES, STAGES

def validate(payload):
    r = payload['result']
    name = payload['player']
    if not isinstance(name,str) or not 1 <= len(name) <= 40 or any(ord(c)<32 for c in name):
        raise ValueError('invalid player')
    if r.get('rules') != RULES or r.get('outcome') != 'finished' or r.get('stage') not in STAGES:
        raise ValueError('only finished compatible runs accepted')
    e,t,c = r['energy_j'],r['elapsed_s'],r['collisions']
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (e,t,c)):
        raise ValueError('invalid metrics')
    if not 0 <= e <= 1e8 or not 1 <= t <= 300 or int(c) != c or not 0 <= c <= 100000:
        raise ValueError('invalid metrics range')
    # Ignore client score: derive score from fixed rules.
    result = Run(int(r['stage']),energy_j=e,elapsed=t,collisions=int(c),outcome='finished').result()
    return name,result

def entries(database,uploads,stage):
    with sqlite3.connect(database) as db:
        data=db.execute('SELECT player,score,energy_j,elapsed_s,collisions,run_id FROM runs WHERE stage=? AND rules=? ORDER BY score DESC,energy_j ASC LIMIT 100',(stage,RULES)).fetchall()
    return dict(verification='self-reported / trusted participants only',entries=data,
                replays={row[5]:(Path(uploads)/row[5]/'replay.json').exists() for row in data})

def save_submission(database,uploads,payload):
    from .archive import check_bundle
    name,r=validate(payload)
    states=payload.get('states','')
    if not isinstance(states,str):raise ValueError('invalid replay')
    if states:
        check_bundle(payload)
        if payload['metadata']['stage']!=r['stage'] or payload['metadata'].get('rules')!=RULES:raise ValueError('incompatible replay course')
    # Replay inclusion does not change identity: re-upload can add a missing replay.
    run_id=hashlib.sha256(json.dumps(dict(player=name,result=r,metadata=payload.get('metadata')),sort_keys=True).encode()).hexdigest()
    directory=Path(uploads)/run_id;directory.mkdir(parents=True,exist_ok=True)
    if states:
        import uuid
        temp=directory/(str(uuid.uuid4())+'.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False));temp.replace(directory/'replay.json')
    with sqlite3.connect(database) as db:
        db.execute('INSERT OR IGNORE INTO runs (run_id,player,stage,score,energy_j,elapsed_s,collisions,rules) VALUES (?,?,?,?,?,?,?,?)',(run_id,name,r['stage'],r['score'],r['energy_j'],r['elapsed_s'],r['collisions'],RULES))
    return dict(run_id=run_id,score=r['score'],verification='self-reported')

def replay_payload(uploads,run_id):
    from .archive import identifier
    path=Path(uploads)/identifier(run_id)/'replay.json'
    if not path.exists():raise ValueError('再生データはアップロードされていません')
    return json.loads(path.read_text())

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data):
        data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def authorized(self):
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        return hmac.compare_digest(token,self.server.token)
    def do_GET(self):
        if not self.authorized(): self.respond(401,{'error':'token required'});return
        try:
            if self.path in tuple(f'/ranking/{stage}' for stage in STAGES):
                self.respond(200,entries(self.server.database,self.server.uploads,int(self.path.rsplit('/',1)[1])))
            elif self.path.startswith('/replays/'):
                self.respond(200,replay_payload(self.server.uploads,self.path.rsplit('/',1)[1]))
            else:self.respond(404,{'error':'not found'})
        except (ValueError,KeyError) as e:self.respond(404,{'error':str(e)})
    def do_POST(self):
        if not self.authorized(): self.respond(401,{'error':'token required'});return
        if self.path != '/runs': self.respond(404,{'error':'not found'});return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=32*1024*1024: raise ValueError('body too large')
            p=json.loads(self.rfile.read(n))
            self.respond(201,save_submission(self.server.database,self.server.uploads,p))
        except (ValueError,KeyError,TypeError) as e:
            self.respond(400,{'error':str(e)})

def initialize_database(database):
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY,player TEXT,stage INTEGER,score REAL,energy_j REAL,elapsed_s REAL,collisions INTEGER,rules TEXT)')
        if 'rules' not in {row[1] for row in db.execute('PRAGMA table_info(runs)')}:
            db.execute("ALTER TABLE runs ADD COLUMN rules TEXT DEFAULT 'ecowalk-game-1'")


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8091);p.add_argument('--database',default='ranking.db');p.add_argument('--uploads',default='ranking-runs');a=p.parse_args()
    token=os.environ.get('K1_RANKING_TOKEN','')
    if len(token)<24: p.error('set K1_RANKING_TOKEN to a secret with at least 24 characters')
    initialize_database(a.database)
    s=ThreadingHTTPServer((a.host,a.port),Handler);s.token=token;s.database=a.database;s.uploads=a.uploads
    print(f'Ranking API on {a.host}:{a.port}; self-reported trusted-participant mode',flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
