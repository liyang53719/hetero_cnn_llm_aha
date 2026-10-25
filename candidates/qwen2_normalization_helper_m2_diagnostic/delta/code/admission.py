"""Exact static-review identity gate. Does not grant authority to execute."""
import hashlib,json
from pathlib import Path
from policy import LIMITS, EXECUTABLES, PROFILE, ARMS

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
    need(review['limits']==LIMITS and config['limits']==LIMITS,'reviewed immutable pair limits')
    need(config['profile']==PROFILE and config['rows']==2 and config['arm_order']==list(ARMS),'exact reviewed two-fresh M2 profile')
    need(set(review['executable_sources'])==set(EXECUTABLES),'complete executable source review')
    for name,digest in review['executable_sources'].items():
        path=here/name
        need(sha(path)==digest,'executable source differs from review: '+name)
        need(config['files'][str(path.resolve())]['sha256']==digest,'source not bound by reviewed config')
    expected={name:pin['sha256'] for name,pin in config['reused_executable_sources'].items()}
    need(review['reused_executable_sources']==expected,'exact identity derivative and source-gate closure review')
    for name,digest in expected.items():
        need(sha(name)==digest and config['files'][name]['sha256']==digest,'reused source pin')
    return config,review
