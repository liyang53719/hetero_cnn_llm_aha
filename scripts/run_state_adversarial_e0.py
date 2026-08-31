#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.state_adversarial_vectors import adversarial_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--transactions',type=int,default=5000);a=p.parse_args();r=adversarial_report(a.transactions);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'transactions':r['transactions'],'counters':r['counters']},indent=2))
