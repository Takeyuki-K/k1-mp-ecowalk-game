"""Explicit submission; never uploads automatically."""
import argparse,json,os
from pathlib import Path
from urllib.request import Request,urlopen
p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('--url',required=True);p.add_argument('--player',required=True);p.add_argument('--include-replay',action='store_true');a=p.parse_args()
r=Path(a.run)
payload={'player':a.player,'result':json.loads((r/'result.json').read_text()),'metadata':json.loads((r/'metadata.json').read_text())}
if a.include_replay:payload['states']=(r/'states.jsonl').read_text()
req=Request(a.url.rstrip('/')+'/runs',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['K1_RANKING_TOKEN']})
with urlopen(req,timeout=30) as response:print(response.read().decode())
