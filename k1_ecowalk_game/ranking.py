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
from .rules import Run, RULES

def validate(payload):
    r = payload['result']
    name = payload['player']
    if not isinstance(name,str) or not 1 <= len(name) <= 40 or any(ord(c)<32 for c in name):
        raise ValueError('invalid player')
    if r.get('rules') != RULES or r.get('outcome') != 'finished' or r.get('stage') not in (1,2):
        raise ValueError('only finished compatible runs accepted')
    e,t,c = r['energy_j'],r['elapsed_s'],r['collisions']
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (e,t,c)):
        raise ValueError('invalid metrics')
    if not 0 <= e <= 1e8 or not 1 <= t <= 300 or int(c) != c or not 0 <= c <= 100000:
        raise ValueError('invalid metrics range')
    # Ignore client score: derive score from fixed rules.
    result = Run(int(r['stage']),energy_j=e,elapsed=t,collisions=int(c),outcome='finished').result()
    return name,result

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
        if self.path not in ('/ranking/1','/ranking/2'): self.respond(404,{'error':'not found'});return
        with sqlite3.connect(self.server.database) as db:
            data=db.execute('SELECT player,score,energy_j,elapsed_s,collisions,run_id FROM runs WHERE stage=? ORDER BY score DESC,energy_j ASC LIMIT 100',(int(self.path[-1]),)).fetchall()
        self.respond(200,{'verification':'self-reported / trusted participants only','entries':data})
    def do_POST(self):
        if not self.authorized(): self.respond(401,{'error':'token required'});return
        if self.path != '/runs': self.respond(404,{'error':'not found'});return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=32*1024*1024: raise ValueError('body too large')
            p=json.loads(self.rfile.read(n));name,r=validate(p)
            states=p.get('states','')
            if not isinstance(states,str): raise ValueError('invalid replay')
            run_id=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
            # Optional replay upload: store as data, never execute or trust its physics.
            directory=Path(self.server.uploads)/run_id;directory.mkdir(parents=True,exist_ok=True)
            (directory/'submission.json').write_text(json.dumps(p,ensure_ascii=False))
            with sqlite3.connect(self.server.database) as db:
                db.execute('INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?)',(run_id,name,r['stage'],r['score'],r['energy_j'],r['elapsed_s'],r['collisions']))
            self.respond(201,{'run_id':run_id,'score':r['score'],'verification':'self-reported'})
        except (ValueError,KeyError,TypeError) as e:
            self.respond(400,{'error':str(e)})

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8091);p.add_argument('--database',default='ranking.db');p.add_argument('--uploads',default='ranking-runs');a=p.parse_args()
    token=os.environ.get('K1_RANKING_TOKEN','')
    if len(token)<24: p.error('set K1_RANKING_TOKEN to a secret with at least 24 characters')
    with sqlite3.connect(a.database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY,player TEXT,stage INTEGER,score REAL,energy_j REAL,elapsed_s REAL,collisions INTEGER)')
    s=ThreadingHTTPServer((a.host,a.port),Handler);s.token=token;s.database=a.database;s.uploads=a.uploads
    print(f'Ranking API on {a.host}:{a.port}; self-reported trusted-participant mode',flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
