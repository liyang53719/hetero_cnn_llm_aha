#!/usr/bin/env python3
"""Offline-safe helper for freezing an official model config.

Network fetching is intentionally not embedded in validation. Supply a locally
reviewed config JSON, official model ID and immutable revision.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--config',required=True,type=Path)
    ap.add_argument('--model-id',required=True)
    ap.add_argument('--revision',required=True)
    ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args()
    raw=args.config.read_bytes(); cfg=json.loads(raw)
    profile={'profile_schema':1,'requested_name':args.model_id.split('/')[-1],
      'model_id':args.model_id,'revision':args.revision,'source_status':'official_config_frozen',
      'config_sha256':hashlib.sha256(raw).hexdigest(),'architectures':cfg.get('architectures',[]),
      'model_type':cfg.get('model_type'),'raw_relevant':{k:v for k,v in cfg.items() if any(s in k.lower() for s in
        ('layer','head','expert','moe','delta','conv','rope','hidden','intermediate','context','window'))},
      'claim_boundary':'profile_imported_operator_classification_requires_review'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(profile,indent=2,ensure_ascii=False)+'\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
