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
from .rules import Run, STAGES, RULES, public_course
from .recording import Recorder, rows
from .backend import Backend, PUBLIC_SHA, TELEOP_SHA
from .obstacles import SCENERY_VERSION
from .archive import bundle, check_bundle, recordings, identifier, MAX_BYTES
from .ranking import initialize_database, entries, save_submission, replay_payload

class Game:
    def __init__(self, args):
        self.args = args
        self.observation_only = getattr(args, 'observation_only', False)
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
        self.frame_condition = threading.Condition()
        self.frame_seq = 0
        self.render_fps = 0.
        self.real_time_factor = 1.
        self.current_power = 0.
        self.worker_error = None
        self.playback = None
        self.local_database = Path(args.output)/'ranking.db'
        self.local_uploads = Path(args.output)/'ranking-uploads'
        self.local_database.parent.mkdir(parents=True,exist_ok=True)
        initialize_database(self.local_database)

    def request_start(self, stage):
        if self.worker_error:
            raise RuntimeError(self.worker_error)
        future = Future()
        self.jobs.put(("start",stage,future))
        return future.result(timeout=60)

    def request_replay(self, payload):
        if self.worker_error:raise RuntimeError(self.worker_error)
        data=check_bundle(payload)
        future=Future();self.jobs.put(('replay',(payload,data),future))
        return future.result(timeout=60)

    def load_replay(self, payload, data):
        meta=payload['metadata']
        backend=Backend(self.args.ecowalk_root,self.args.teleop_root,meta['stage'],meta.get('course'))
        if len(data[0]['state'])!=len(backend.sim.env.state[0]):
            backend.close(close_renderer=False)
            raise ValueError('再生データのモデル状態サイズが一致しません')
        with self.lock:
            self.finish('aborted')
            if self.backend:self.backend.close(close_renderer=False)
            self.backend=backend;self.run=None;self.replay=None;self.directory=None
            self.command=(0.,0.,False);self.frame_bytes=None
            self.playback=dict(data=data,index=0,paused=False,speed=1.,name=payload.get('player','保存した記録'))
            self.apply_replay(0)

    def apply_replay(self, index):
        p=self.playback;p['index']=max(0,min(len(p['data'])-1,int(index)))
        row=p['data'][p['index']];self.replay_row=row
        self.result=row.get('result');self.current_power=row.get('power_w',0.)
        self.backend.sim.sim_time=row['t'];self.backend.sim.g.mode[0]=row['mode']
        self.backend.sim.env.state[0]=row['state']

    def replay_control(self, body):
        with self.lock:
            if not self.playback:raise ValueError('再生中の記録がありません')
            p=self.playback
            if 'paused' in body:p['paused']=bool(body['paused'])
            if 'speed' in body:
                speed=float(body['speed'])
                if speed not in (.5,1.,2.):raise ValueError('invalid replay speed')
                p['speed']=speed
            if 'fraction' in body:
                import math
                value=float(body['fraction'])
                if not math.isfinite(value) or not 0<=value<=1:raise ValueError('invalid seek')
                self.apply_replay(round(value*(len(p['data'])-1)))

    def start(self, stage):
        if stage not in STAGES:
            raise ValueError('unknown stage')
        with self.lock:
            self.finish('aborted')
            if self.backend:
                self.backend.close(close_renderer=False)
            self.backend = Backend(self.args.ecowalk_root,self.args.teleop_root,stage)
            if self.observation_only:
                self.backend.camera_mode = 'first'
            self.replay = None
            self.playback = None
            self.replay_row = None
            self.frame_bytes = None
            self.run = Run(stage)
            self.result = None
            self.command = (0.,0.,False)
            self.last_command = 0.
            self.directory = Path(self.args.output)/str(uuid.uuid4())
            metadata = dict(stage=stage,policy='v5.6.3',public_commit=PUBLIC_SHA,teleop_commit=TELEOP_SHA,
                            rules=RULES,course=public_course(STAGES[stage]),scenery_version=SCENERY_VERSION if stage == 4 else None,battery_wh=self.args.battery_wh,usable_fraction=self.args.usable_fraction,auxiliary_w=self.args.auxiliary_w,physics_dt=self.backend.sim.m.opt.timestep,
                            seed=5,mujoco_version=self.backend.mj.__version__,numpy_version=__import__('numpy').__version__,torch_version=__import__('torch').__version__,power_model='sum(tau^2/Km^2 + max(tau*qd,0)); no regeneration; all 23 motors')
            self.recorder = Recorder(self.directory,metadata,self.args.rosbag)
            self.capture(0.,0.,set())

    def capture(self, power, dt, contacts):
        b = self.backend
        row = dict(t=b.sim.sim_time,mode=int(b.sim.g.mode[0]),state=b.sim.env.state[0].tolist(),
                   command=list(self.command),power_w=power,dt=dt,contacts=sorted(contacts),result=self.run.result(self.args.battery_wh,self.args.usable_fraction,self.args.auxiliary_w))
        self.recorder.append(row)

    def finish(self, outcome=None):
        if self.recorder:
            if outcome and self.run.outcome == 'playing':
                self.run.outcome = outcome
            self.result = self.run.result(self.args.battery_wh,self.args.usable_fraction,self.args.auxiliary_w)
            self.recorder.close(self.result)
            self.recorder = None

    def loop(self):
        try:
            self.physics_loop()
        except Exception as e:
            with self.lock:
                self.worker_error = f'シミュレーションエラー：{e}'
                self.command = (0.,0.,False)
                self.finish('aborted')
            while not self.jobs.empty():
                _,_,future = self.jobs.get()
                future.set_exception(e)

    def physics_loop(self):
        import torch
        torch.set_num_threads(1)
        while self.running:
            while not self.jobs.empty():
                kind, argument, future = self.jobs.get()
                try:
                    if kind=="start":self.start(argument)
                    else:self.load_replay(*argument)
                    future.set_result(True)
                except Exception as e:
                    future.set_exception(e)
            start = time.monotonic()
            dt = .02
            with self.lock:
                if self.playback is not None:
                    p=self.playback
                    if not p['paused']:
                        if p['index']<len(p['data'])-1:
                            previous=p['data'][p['index']]['t']
                            self.apply_replay(p['index']+1)
                            dt=max(.001,(p['data'][p['index']]['t']-previous)/p['speed'])
                        else:p['paused']=True
                elif self.replay is not None:
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
                    self.current_power = power
                    q, qv = b.sim.qpos(), b.sim.qvel()
                    stopped = b.sim.status()['mode'] == 'stand' and cmd[:2] == (0.,0.)
                    self.run.update(dt,power,q[:3],float((qv[:2]**2).sum()**.5),float(qv[5]),contacts,b.sim.fallen,stopped,b.collision_stop)
                    self.capture(power,dt,contacts)
                    if self.run.outcome != 'playing':
                        self.finish()
            self.real_time_factor = min(1., dt / max(dt,time.monotonic()-start))
            time.sleep(max(0.,dt-(time.monotonic()-start)))

        if self.backend:
            self.backend.close(close_renderer=False)

    def render_loop(self):
        # Only this thread owns OpenGL resources; physics never waits for JPEG rendering.
        previous = None
        count, window = 0, time.monotonic()
        fps = getattr(self.args,'render_fps',30)
        deadline = time.monotonic()
        try:
            while self.running:
                with self.lock:
                    backend = self.backend
                    if backend:
                        mode = int(backend.sim.g.mode[0])
                        state = backend.sim.env.state[0].copy()
                        camera = 'first' if self.observation_only else backend.camera_mode
                if backend is not previous:
                    if previous:
                        previous.close_renderer()
                    previous = backend
                if backend:
                    try:
                        from PIL import Image
                        buf = io.BytesIO()
                        Image.fromarray(backend.frame(state,mode,camera)).save(buf,format='JPEG',quality=90)
                        frame = buf.getvalue()
                        with self.lock:
                            if backend is self.backend:
                                self.frame_bytes = frame
                                self.render_error = None
                                self.last_frame = time.monotonic()
                        with self.frame_condition:
                            self.frame_seq += 1
                            self.frame_condition.notify_all()
                        count += 1
                    except Exception as e:
                        with self.lock:
                            self.render_error = f'{e}（MUJOCO_GL=osmesa で再起動を試してください）'
                        time.sleep(.1)
                now = time.monotonic()
                if now-window >= 1:
                    self.render_fps = count/(now-window)
                    count,window = 0,now
                deadline += 1/fps
                if deadline < now:
                    deadline = now
                time.sleep(max(0.,deadline-time.monotonic()))
        finally:
            if previous:
                previous.close_renderer()
            with self.frame_condition:
                self.frame_condition.notify_all()

    def status(self):
        with self.lock:
            return dict(rules=RULES,result=self.result or (self.run.result(self.args.battery_wh,self.args.usable_fraction,self.args.auxiliary_w) if self.run else None),
                        sim=self.backend.sim.status() if self.backend else None,
                        directory=str(self.directory) if self.directory and not self.observation_only else None,
                        replay=(dict(paused=self.playback['paused'],speed=self.playback['speed'],name=self.playback['name'],
                                     time=self.replay_row['t'],duration=self.playback['data'][-1]['t'],
                                     fraction=self.playback['index']/max(1,len(self.playback['data'])-1)) if self.playback else (dict(time=self.replay_row['t']) if self.replay_row else None)),render_error=('描画エラー' if self.observation_only and self.render_error else self.render_error),render_fps=round(self.render_fps,1),
                        render_target_fps=getattr(self.args,"render_fps",30),real_time_factor=round(self.real_time_factor,2),
                        current_power_w=self.current_power,worker_error=('シミュレーションエラー' if self.observation_only and self.worker_error else self.worker_error),
                        ranking_enabled=not self.observation_only,ranking_remote=bool(getattr(self.args,'ranking_url',None)),
                        observation_only=self.observation_only,
                        course=public_course(self.backend.course) if self.backend else None)

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
            if getattr(g,'observation_only',False) and self.path not in (
                    '/', '/game.js','/controls.js','/minimap.js','/archive.js','/style.css',
                    '/status','/frame.jpg','/stream.mjpg'):
                self.send(403,{'error':'観測限定モードではこの操作を利用できません'}); return
            if self.path == '/':
                self.send(200,(Path(__file__).parent/'web/index.html').read_bytes(),'text/html; charset=utf-8')
            elif self.path in ('/game.js','/controls.js','/minimap.js','/archive.js','/style.css'):
                mime = 'text/css' if self.path.endswith('.css') else 'text/javascript'
                self.send(200,(Path(__file__).parent/'web'/self.path[1:]).read_bytes(),mime+'; charset=utf-8')
            elif self.path == '/status':
                self.send(200,g.status())
            elif self.path == '/recordings':
                self.send(200,{'entries':recordings(g.args.output)})
            elif self.path.startswith('/recordings/'):
                run_id=identifier(self.path.rsplit('/',1)[1])
                self.send(200,bundle(Path(g.args.output)/run_id))
            elif self.path in tuple(f'/ranking/{stage}' for stage in STAGES):
                if g.args.ranking_url:
                    req = Request(g.args.ranking_url.rstrip('/')+self.path,headers={'Authorization':'Bearer '+os.environ.get('K1_RANKING_TOKEN','')})
                    with urlopen(req,timeout=10) as response:self.send(200,response.read())
                else:self.send(200,entries(g.local_database,g.local_uploads,int(self.path.rsplit('/',1)[1])))
            elif self.path == '/stream.mjpg':
                self.stream_frames()
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
            self.send(500,{'error':'要求を処理できません' if getattr(g,'observation_only',False) else str(e)})

    def stream_frames(self):
        g = self.server.game
        self.send_response(200)
        self.send_header('Content-Type','multipart/x-mixed-replace; boundary=k1frame')
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        seq = -1
        try:
            while g.running:
                with g.frame_condition:
                    g.frame_condition.wait_for(lambda: g.frame_seq != seq or not g.running,timeout=1)
                    if not g.running:
                        break
                    if g.frame_seq == seq:
                        continue
                    seq = g.frame_seq
                with g.lock:
                    frame = g.frame_bytes
                if frame:
                    self.wfile.write(b'--k1frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(frame)).encode()+b'\r\n\r\n'+frame+b'\r\n')
                    self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):
            pass

    def do_POST(self):
        g = self.server.game
        try:
            if getattr(g,'observation_only',False) and self.path not in (
                    '/start','/command','/camera','/abort'):
                self.send(403,{'error':'観測限定モードではこの操作を利用できません'}); return
            # Local control API: same-origin requests only, no external website control.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):
                self.send(403,{'error':'origin rejected'}); return
            n = int(self.headers.get('Content-Length','0'))
            if not 0 < n <= (MAX_BYTES if self.path=='/replay-import' else 4096):
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
                import math
                yaw = float(body.get('yaw', 0))
                pitch = float(body.get('pitch', 0))
                if not math.isfinite(yaw) or not math.isfinite(pitch):
                    raise ValueError('invalid camera angles')
                with g.lock:
                    if g.backend:
                        g.backend.camera_mode = 'first' if g.observation_only or body.get('mode') == 'first' else 'third'
                        g.backend.camera_yaw = max(-90., min(90., yaw))
                        g.backend.camera_pitch = max(-65., min(45., pitch))
            elif self.path == '/submit':
                with g.lock:
                    if body.get('id'):
                        payload=bundle(Path(g.args.output)/identifier(body['id']))
                    elif g.directory and g.result and not g.recorder:
                        payload=bundle(g.directory)
                    else:raise ValueError('保存済みの完走記録が必要です')
                if payload['result']['outcome']!='finished':raise ValueError('完走した記録だけ登録できます')
                payload['player']=str(body['player'])
                if not body.get('include_replay'):payload.pop('states',None)
                data=json.dumps(payload,allow_nan=False).encode()
                if len(data)>MAX_BYTES:raise ValueError('replay too large')
                if g.args.ranking_url:
                    req=Request(g.args.ranking_url.rstrip('/')+'/runs',data=data,headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ.get('K1_RANKING_TOKEN','')})
                    with urlopen(req,timeout=30) as response:self.send(200,response.read())
                else:self.send(200,save_submission(g.local_database,g.local_uploads,payload))
                return
            elif self.path == '/replay-local':
                g.request_replay(bundle(Path(g.args.output)/identifier(body['id'])))
            elif self.path == '/replay-ranking':
                run_id=identifier(body['id'])
                if g.args.ranking_url:
                    req=Request(g.args.ranking_url.rstrip('/')+'/replays/'+run_id,headers={'Authorization':'Bearer '+os.environ.get('K1_RANKING_TOKEN','')})
                    with urlopen(req,timeout=30) as response:
                        content=response.read(MAX_BYTES+1)
                        if len(content)>MAX_BYTES:raise ValueError('replay too large')
                        payload=json.loads(content)
                else:payload=replay_payload(g.local_uploads,run_id)
                g.request_replay(payload)
            elif self.path == '/replay-import':
                check_bundle(body)
                g.request_replay(body)
                directory=Path(g.args.output)/str(uuid.uuid4());directory.mkdir(parents=True)
                (directory/'metadata.json').write_text(json.dumps(body['metadata'],allow_nan=False))
                (directory/'result.json').write_text(json.dumps(body['result'],allow_nan=False))
                (directory/'states.jsonl').write_text(body['states'])
            elif self.path == '/replay-control':
                g.replay_control(body)
            elif self.path == '/abort':
                with g.lock:
                    g.finish('aborted')
                    if g.playback:g.playback['paused']=True
            else:
                self.send(404,{'error':'not found'}); return
            self.send(200,{'ok':True})
        except Exception as e:
            self.send(400,{'error':'要求を処理できません' if getattr(g,'observation_only',False) else str(e)})

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ecowalk-root',default=os.environ.get('ECOWALK_ROOT','vendor/k1-mp-ecowalk-public'))
    p.add_argument('--teleop-root',default=os.environ.get('TELEOP_ROOT','vendor/k1-mp-ecowalk-teleop'))
    p.add_argument('--port',type=int,default=8090)
    p.add_argument('--ranking-url')
    p.add_argument('--render-fps',type=int,default=30,choices=range(5,61),metavar='5..60')
    p.add_argument('--output',default='runs')
    p.add_argument('--rosbag',action='store_true')
    p.add_argument('--observation-only',action='store_true',
                   help='first-person images and normal controls only; block archives/replays/ranking APIs')
    p.add_argument('--replay')
    p.add_argument('--stage',type=int,choices=sorted(STAGES),default=1,help='stage for rosbag-only replay')
    p.add_argument('--battery-wh',type=float,default=400.,help='battery capacity in Wh (default: 400)')
    p.add_argument('--usable-fraction',type=float,default=.8)
    p.add_argument('--auxiliary-w',type=float,default=0.)
    args = p.parse_args()
    if args.observation_only and args.replay:
        p.error('--observation-only cannot be combined with --replay')
    import math
    if not all(math.isfinite(v) for v in (args.battery_wh,args.usable_fraction,args.auxiliary_w)) or args.battery_wh <= 0 or not 0 < args.usable_fraction <= 1 or args.auxiliary_w < 0:
        p.error('invalid battery/power configuration')
    g = Game(args)
    if args.replay:
        if (Path(args.replay)/'states.jsonl').exists():
            payload=bundle(args.replay);g.load_replay(payload,check_bundle(payload))
        else:
            source=Path(args.replay);data=list(rows(source))
            if not data:p.error('empty replay')
            meta_path=source.parent/'metadata.json';result_path=source.parent/'result.json'
            metadata=json.loads(meta_path.read_text()) if meta_path.exists() else dict(stage=args.stage,public_commit=PUBLIC_SHA,rules=RULES,course=STAGES[args.stage],scenery_version=SCENERY_VERSION if args.stage == 4 else None)
            payload=dict(metadata=metadata,result=json.loads(result_path.read_text()) if result_path.exists() else data[-1]['result'],states=''.join(json.dumps(row)+'\n' for row in data))
            g.load_replay(payload,check_bundle(payload))
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.game = g
    thread = threading.Thread(target=g.loop,daemon=True); thread.start()
    render_thread = threading.Thread(target=g.render_loop,daemon=True); render_thread.start()
    print(f'K1 EcoWalk Game: http://localhost:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        g.running = False
        with g.frame_condition:
            g.frame_condition.notify_all()
        thread.join(timeout=5); render_thread.join(timeout=5)
        with g.lock:
            g.finish('aborted')

        server.server_close()
