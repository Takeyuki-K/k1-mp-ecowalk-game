import argparse
import io
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import uuid
import queue
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .rules import Run, STAGES
from .recording import Recorder, rows
from .backend import Backend, PUBLIC_SHA, TELEOP_SHA

class Game:
    def __init__(self, args):
        self.args = args
        self.lock = threading.RLock()
        self.jobs = queue.Queue()
        self.backend = None
        self.run = None
        self.recorder = None
        self.result = None
        self.command = (0.,0.,False)
        self.last_command = 0.
        self.running = True
        self.replay = None
        self.replay_row = None
        self.directory = None
        self.frame_bytes = None
        self.render_error = None
        self.last_frame = 0.

    def request_start(self, stage):
        future = Future()
        self.jobs.put((stage,future))
        return future.result(timeout=60)

    def start(self, stage):
        if stage not in STAGES:
            raise ValueError('unknown stage')
        with self.lock:
            self.finish('aborted')
            if self.backend:
                self.backend.close()
            self.backend = Backend(self.args.ecowalk_root,self.args.teleop_root,stage)
            self.replay = None
            self.replay_row = None
            self.frame_bytes = None
            self.run = Run(stage)
            self.result = None
            self.command = (0.,0.,False)
            self.last_command = 0.
            self.directory = Path(self.args.output)/str(uuid.uuid4())
            metadata = dict(stage=stage,policy='v5.6.3',public_commit=PUBLIC_SHA,teleop_commit=TELEOP_SHA,
                            rules='ecowalk-game-1',physics_dt=self.backend.sim.m.opt.timestep,
                            seed=5,mujoco_version=self.backend.mj.__version__,numpy_version=__import__('numpy').__version__,torch_version=__import__('torch').__version__,power_model='sum(tau^2/Km^2 + max(tau*qd,0)); no regeneration; all 23 motors')
            self.recorder = Recorder(self.directory,metadata,self.args.rosbag)
            self.capture(0.,0.,set())

    def capture(self, power, dt, contacts):
        b = self.backend
        row = dict(t=b.sim.sim_time,mode=int(b.sim.g.mode[0]),state=b.sim.env.state[0].tolist(),
                   command=list(self.command),power_w=power,dt=dt,contacts=sorted(contacts),result=self.run.result())
        self.recorder.append(row)

    def finish(self, outcome=None):
        if self.recorder:
            if outcome and self.run.outcome == 'playing':
                self.run.outcome = outcome
            self.result = self.run.result(self.args.battery_wh,self.args.usable_fraction,self.args.auxiliary_w)
            self.recorder.close(self.result)
            self.recorder = None

    def loop(self):
        import torch
        torch.set_num_threads(1)
        while self.running:
            while not self.jobs.empty():
                stage, future = self.jobs.get()
                try:
                    self.start(stage)
                    future.set_result(True)
                except Exception as e:
                    future.set_exception(e)
            start = time.monotonic()
            dt = .02
            with self.lock:
                if self.replay is not None:
                    try:
                        row = next(self.replay)
                        self.replay_row = row
                        self.result = row.get('result')
                        self.backend.sim.sim_time = row['t']
                        self.backend.sim.g.mode[0] = row['mode']
                        self.backend.sim.env.state[0] = row['state']
                    except StopIteration:
                        self.replay = None
                elif self.recorder:
                    b = self.backend
                    dt = b.sim.dt
                    cmd = self.command if time.monotonic()-self.last_command < .5 else (0.,0.,False)
                    self.command = cmd
                    power, contacts, _ = b.step(*cmd)
                    q, qv = b.sim.qpos(), b.sim.qvel()
                    stopped = b.sim.status()['mode'] == 'stand' and cmd[:2] == (0.,0.)
                    self.run.update(dt,power,q[:3],float((qv[:2]**2).sum()**.5),float(qv[5]),contacts,b.sim.fallen,stopped)
                    self.capture(power,dt,contacts)
                    if self.run.outcome != 'playing':
                        self.finish()
                if self.backend and time.monotonic()-self.last_frame >= .1:
                    try:
                        from PIL import Image
                        buf = io.BytesIO()
                        Image.fromarray(self.backend.frame()).save(buf,format='JPEG',quality=80)
                        self.frame_bytes = buf.getvalue()
                        self.render_error = None
                    except Exception as e:
                        self.render_error = str(e)
                    self.last_frame = time.monotonic()
            time.sleep(max(0.,dt-(time.monotonic()-start)))

        if self.backend:
            self.backend.close()

    def status(self):
        with self.lock:
            return dict(result=self.result or (self.run.result(self.args.battery_wh,self.args.usable_fraction,self.args.auxiliary_w) if self.run else None),
                        sim=self.backend.sim.status() if self.backend else None,
                        directory=str(self.directory) if self.directory else None,replay=self.replay_row,render_error=self.render_error)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self, status, content, mime='application/json'):
        if not isinstance(content,bytes):
            content = json.dumps(content,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content))); self.send_header('Cache-Control','no-store'); self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        g = self.server.game
        self.path = urlsplit(self.path).path
        try:
            if self.path == '/':
                self.send(200,(Path(__file__).parent/'web/index.html').read_bytes(),'text/html; charset=utf-8')
            elif self.path == '/status':
                self.send(200,g.status())
            elif self.path in ('/ranking/1','/ranking/2'):
                if not g.args.ranking_url:
                    self.send(400,{'error':'ランキング接続先が未設定です'}); return
                req = Request(g.args.ranking_url.rstrip('/')+self.path,headers={'Authorization':'Bearer '+os.environ.get('K1_RANKING_TOKEN','')})
                with urlopen(req,timeout=10) as response:
                    self.send(200,response.read())
            elif self.path == '/frame.jpg':
                with g.lock:
                    frame = g.frame_bytes
                if frame is None:
                    self.send(503,{'error':g.render_error or 'frame pending'})
                else:
                    self.send(200,frame,'image/jpeg')
            else:
                self.send(404,{'error':'not found'})
        except Exception as e:
            self.send(500,{'error':str(e)})

    def do_POST(self):
        g = self.server.game
        try:
            # Local control API: same-origin requests only, no external website control.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):
                self.send(403,{'error':'origin rejected'}); return
            n = int(self.headers.get('Content-Length','0'))
            if not 0 < n <= 4096:
                raise ValueError('invalid body size')
            body = json.loads(self.rfile.read(n))
            if self.path == '/start':
                g.request_start(int(body['stage']))
            elif self.path == '/command':
                import math
                v,w = float(body.get('v',0)),float(body.get('w',0))
                if not math.isfinite(v) or not math.isfinite(w):
                    raise ValueError('nonfinite command')
                with g.lock:
                    g.command = (max(0.,min(4.5,v)),max(-1.,min(1.,w)),bool(body.get('brake',False)))
                    g.last_command = time.monotonic()
            elif self.path == '/camera':
                with g.lock:
                    if g.backend:
                        g.backend.camera_mode = 'first' if body.get('mode') == 'first' else 'third'
            elif self.path == '/submit':
                if not g.args.ranking_url or not g.result or g.result['outcome'] != 'finished':
                    raise ValueError('完走記録と --ranking-url が必要です')
                payload = {'player':str(body['player']), 'result':g.result,
                           'metadata':json.loads((g.directory/'metadata.json').read_text())}
                if body.get('include_replay'):
                    payload['states']=(g.directory/'states.jsonl').read_text()
                data=json.dumps(payload).encode()
                if len(data)>32*1024*1024: raise ValueError('replay too large')
                req=Request(g.args.ranking_url.rstrip('/')+'/runs',data=data,headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ.get('K1_RANKING_TOKEN','')})
                with urlopen(req,timeout=30) as response:
                    self.send(200,response.read())
                return
            elif self.path == '/abort':
                with g.lock:
                    g.finish('aborted')
            else:
                self.send(404,{'error':'not found'}); return
            self.send(200,{'ok':True})
        except Exception as e:
            self.send(400,{'error':str(e)})

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ecowalk-root',default=os.environ.get('ECOWALK_ROOT','vendor/k1-mp-ecowalk-public'))
    p.add_argument('--teleop-root',default=os.environ.get('TELEOP_ROOT','vendor/k1-mp-ecowalk-teleop'))
    p.add_argument('--port',type=int,default=8090)
    p.add_argument('--ranking-url')
    p.add_argument('--output',default='runs')
    p.add_argument('--rosbag',action='store_true')
    p.add_argument('--replay')
    p.add_argument('--stage',type=int,choices=[1,2],default=1,help='stage for rosbag-only replay')
    p.add_argument('--battery-wh',type=float)
    p.add_argument('--usable-fraction',type=float,default=.8)
    p.add_argument('--auxiliary-w',type=float,default=0.)
    args = p.parse_args()
    if args.battery_wh is not None and args.battery_wh <= 0 or not 0 < args.usable_fraction <= 1 or args.auxiliary_w < 0:
        p.error('invalid battery/power configuration')
    g = Game(args)
    if args.replay:
        metadata = Path(args.replay)/'metadata.json'
        stage = json.loads(metadata.read_text())['stage'] if metadata.exists() else args.stage
        g.backend = Backend(args.ecowalk_root,args.teleop_root,stage)
        g.replay = iter(rows(args.replay))
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.game = g
    thread = threading.Thread(target=g.loop,daemon=True); thread.start()
    print(f'K1 EcoWalk Game: http://localhost:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        g.running = False; thread.join(timeout=5)
        with g.lock:
            g.finish('aborted')

        server.server_close()
