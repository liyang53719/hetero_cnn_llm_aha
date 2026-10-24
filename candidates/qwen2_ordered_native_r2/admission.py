"""Exact static-review identity gate. Does not grant authority to execute."""
import hashlib,json
from pathlib import Path

def need(value,message):
    if not value:raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1<<20):h.update(block)
    return h.hexdigest()

def validate_review(config_path,review_path,review_sha,here):
    config_path=Path(config_path);review_path=Path(review_path);here=Path(here)
    need(sha(review_path)==review_sha,'independent review receipt identity')
    review=json.loads(review_path.read_text());actual=sha(config_path)
    need(review['status']=='PASS_STATIC_REVIEW_REQUIRES_ROOT_EXECUTION_AUTHORIZATION','static review state')
    need(review['config_sha256']==actual,'config differs from exact reviewed bytes')
    config=json.loads(config_path.read_text())
    need(review['limits']==dict(cpu_seconds=30,address_space_bytes=1<<30,wall_seconds=45,cpus=1),'reviewed immutable limits')
    need(set(review['executable_sources'])=={'admission.py','harness.py','worker.py','launch.py','runtime_closure.py'},'complete executable source review')
    for name,digest in review['executable_sources'].items():
        path=here/name
        need(sha(path)==digest,'executable source differs from review: '+name)
        need(config['files'][str(path.resolve())]['sha256']==digest,'source not bound by reviewed config')
    return config,review
