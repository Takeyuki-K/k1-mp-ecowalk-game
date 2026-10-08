"""Persistent local runs and portable, data-only replay bundles."""
import json
import math
import re
from pathlib import Path

MAX_BYTES = 32*1024*1024

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',value):
        raise ValueError('invalid recording ID')
    return value

def bundle(directory):
    path=Path(directory)
    return dict(metadata=json.loads((path/'metadata.json').read_text()),
                result=json.loads((path/'result.json').read_text()),states=(path/'states.jsonl').read_text())

def check_bundle(payload):
    from .backend import PUBLIC_SHA
    from .rules import STAGES
    meta=payload['metadata']
    if meta.get('stage') not in STAGES or meta.get('public_commit')!=PUBLIC_SHA:
        raise ValueError('この再生データは対応するv5.6.3モデルの記録ではありません')
    if not isinstance(payload.get('result'),dict) or payload['result'].get('stage')!=meta['stage']:raise ValueError('invalid replay result')
    states=payload['states']
    if not isinstance(states,str) or len(states.encode())>MAX_BYTES:
        raise ValueError('invalid replay size')
    data=[json.loads(line) for line in states.splitlines() if line.strip()]
    if not data or len(data)>15002:raise ValueError('invalid replay length')
    previous=-1
    size=None
    for row in data:
        t=row['t'];state=row['state']
        if not isinstance(t,(int,float)) or not math.isfinite(t) or not previous<=t<=301:
            raise ValueError('invalid replay time')
        if row['mode'] not in (0,1) or not isinstance(state,list) or not 7<=len(state)<=2000:
            raise ValueError('invalid replay state')
        if size is None:size=len(state)
        if len(state)!=size or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in state):
            raise ValueError('invalid replay values')
        result=row.get('result')
        if result is not None:
            if result.get('stage')!=meta['stage'] or result.get('outcome') not in ('playing','finished','fallen','out_of_bounds','timeout','aborted'):raise ValueError('invalid frame result')
            for key in ('energy_wh','average_power_w','elapsed_s','collisions','score'):
                value=result[key]
                if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('invalid frame metrics')
        previous=t
    course=meta.get('course')
    if course is not None:
        for key,length in [('goal',2),('goal_half_size',2),('bounds',4)]:
            v=course[key]
            if len(v)!=length or any(not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>1000 for x in v):raise ValueError('invalid course')
        for key,length in [('obstacles',4),('walls',6),('centerline',2)]:
            v=course[key]
            if not isinstance(v,list) or len(v)>1000:raise ValueError('invalid course')
            for item in v:
                if len(item)!=length or any(not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>1000 for x in item):raise ValueError('invalid course')
        if any(w[4]<=0 or w[5]<=0 for w in course['walls']) or any(o[2]<=0 or o[3]<=0 for o in course['obstacles']):raise ValueError('invalid geometry')
        if len(course['centerline'])<2 or course['bounds'][0]>=course['bounds'][1] or course['bounds'][2]>=course['bounds'][3] or min(course['goal_half_size'])<=0:raise ValueError('invalid course bounds')
    elif meta.get('rules')!='ecowalk-game-3':
        raise ValueError('旧コースの記録にはコース情報が必要です')
    return data

def recordings(root):
    result=[]
    for path in Path(root).glob('*/result.json'):
        try:
            r=json.loads(path.read_text());meta=json.loads((path.parent/'metadata.json').read_text())
            result.append(dict(id=path.parent.name,stage=meta['stage'],outcome=r['outcome'],score=r.get('score',0),energy_wh=r.get('energy_wh',0),elapsed_s=r.get('elapsed_s',0),saved_at=path.stat().st_mtime,rules=meta.get('rules')))
        except (OSError,ValueError,KeyError):continue
    return sorted(result,key=lambda r:r['saved_at'],reverse=True)[:100]
