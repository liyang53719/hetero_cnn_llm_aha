"""Stdlib-only boundary, observation and one-use execution contracts."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

WORK = 'work/qwen2_fullblock_reference_capture_20261014'
WALL_SECONDS = 120
RSS_BYTES = 1536 * (1 << 20)
LOG_RETAIN_BYTES = 65536
LOG_EMITTED_LIMIT = 16 * (1 << 20)
POLL_SECONDS = 0.02


def identity(path):
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return {'bytes':size,'sha256':digest.hexdigest()}


def snapshot(R,pins):
    R.need(R.same(pins,R.load_pins()), 'in-memory pin drift')
    R.source_check(R.ROOT,pins)
    own = R.source_manifest()
    result = {'source_manifest':own,'pins':identity(R.HERE/'pins.json'),
              'sources':{},'raw13':{},'native_files':{}}
    for path,pin in pins['sources'].items():
        actual = identity(R.safe_path(R.ROOT,path))
        R.fields(actual,{k:pin[k] for k in ('bytes','sha256')},'source '+path)
        result['sources'][path] = actual
    for pin in pins['raw_tensors']:
        actual = identity(R.safe_path(R.ROOT,pin['path']))
        R.fields(actual,{k:pin[k] for k in ('bytes','sha256')},'raw '+pin['path'])
        result['raw13'][pin['path']] = actual
    for name,pin in pins['runtime_native_files'].items():
        path = Path(pin['path']) if Path(pin['path']).is_absolute() else R.safe_path(R.ROOT,pin['path'])
        actual = identity(path)
        R.fields(actual,{k:pin[k] for k in ('bytes','sha256')},'runtime '+name)
        result['native_files'][name] = {'path':pin['path'],**actual}
    R.need(Path(sys.executable).resolve() == Path(pins['runtime_native_files']['python']['path']).resolve(),
           'exact pinned CPython executable required')
    return result


def run_path(R,run_id,mode):
    R.need(type(run_id) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',run_id), 'canonical run id required')
    R.need(mode in ('bootstrap','frozen'), 'only explicit bootstrap/frozen modes')
    return R.safe_path(R.ROOT,WORK+'/'+run_id+'/'+mode)


def write_new(R,path,value):
    raw = R.encoded(value)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def progress(R,out,stage):
    # Only a fresh run's bounded progress journal is mutable. Payloads are xb-only.
    R.need(type(stage) is str and len(stage) < 80, 'bounded execution stage')
    with (out/'STAGES.jsonl').open('ab') as stream:
        R.need(stream.tell() < 16384, 'stage journal cap')
        stream.write(R.encoded({'stage':stage}).replace(b'\n',b'')+b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def last_stage(R,out):
    path = out/'STAGES.jsonl'
    if not path.exists():
        return 'wrapper-preflight'
    raw = path.read_bytes()
    R.need(len(raw) <= 16384, 'stage journal oversized')
    lines = raw.splitlines()
    return R.parse(lines[-1])['stage'] if lines else 'worker-not-started'


def validate_go(R,pins,path,run_id,mode):
    # This receipt is created by the parent only after independent review and go.
    # It supplies authority, never numeric expectations or tunable resource limits.
    path = R.safe_path(R.ROOT,path)
    R.need(path.is_relative_to(R.ROOT/WORK) and path.stat().st_size <= 16384, 'bounded local go receipt')
    go = R.parse(path.read_bytes())
    R.exact_keys(go, ('schema','action','run_id','source_manifest','source_review','issued_by',
                     'maximum_invocations','no_retry','exclusive_numeric_slot'), 'single go')
    R.fields(go, {'schema':1,'action':'single-'+mode,'run_id':run_id,'source_manifest':R.source_manifest(),
                  'maximum_invocations':1,'no_retry':True,'exclusive_numeric_slot':True}, 'single go')
    R.need(type(go['issued_by']) is str and go['issued_by'].strip(), 'explicit go issuer required')
    review_spec = go['source_review']
    R.exact_keys(review_spec, ('path','bytes','sha256'), 'review identity')
    R.need(type(review_spec['bytes']) is int and 0 < review_spec['bytes'] <= 262144, 'bounded source review')
    review_path = R.safe_path(R.ROOT,review_spec['path'])
    R.need((review_path.is_relative_to(R.ROOT/WORK) or review_path.is_relative_to(R.ROOT/'work/qwen2_fullblock_reference_capture_review_20261014')), 'review must be in this capture work area')
    review = R.parse(R.checked(R.ROOT,review_spec['path'],review_spec))
    R.fields(review, {'status':'APPROVED_SOURCE_FOR_SINGLE_'+mode.upper(),
        'source_manifest':go['source_manifest'],'mode':mode,'numeric_executed':False}, 'independent source review')
    R.need(type(review.get('reviewer')) is str and review['reviewer'].strip()
           and review['reviewer'] != go['issued_by'], 'distinct independent reviewer required')
    R.fields(review.get('tool_identity'), {'python_executable':pins['runtime_native_files']['python'],
        'implementation':'cpython','python_major_minor':[3,12],'source_manifest':go['source_manifest']},
        'review tool/source identity')
    if mode == 'frozen':
        R.require_frozen_references(pins)
    return {'receipt':{'path':str(path.relative_to(R.ROOT)),**identity(path)},'content':go}


def verify_parent_entry(R,pins,args,cwd,executable,cap,go):
    """Verify the actual script slot, not arbitrary argv membership or basename."""
    R.need(type(args) is list and len(args) == 9 and args[1] == '-B', 'exact Python -B guard CLI required')
    R.need(args[3:] == ['--mode',cap['mode'],'--run-id',cap['run_id'],'--go',go['receipt']['path']],
           'parent guard mode/run-id/go binding mismatch')
    R.need(Path(cwd).resolve() == R.ROOT, 'parent guard cwd must be the pinned checkout')
    R.need(Path(executable).resolve() == Path(pins['runtime_native_files']['python']['path']).resolve(),
           'parent executable must be pinned CPython')
    script = Path(args[2])
    script = script if script.is_absolute() else Path(cwd)/script
    R.need(script.resolve(strict=True) == R.HERE/'guard.py', 'parent script is not the pinned guard')
    manifest = R.parse((R.HERE/'SOURCE_MANIFEST.json').read_bytes())
    R.need(R.same(identity(script),manifest['files']['guard.py']), 'parent guard source identity drift')


def claim_capability(R,pins,out,mode,fd):
    """Reject direct API calls and flag-only bypasses before opening raw/Torch."""
    R.need(type(fd) is int and fd >= 3, 'capture requires live bounded-wrapper capability')
    R.need(stat.S_ISFIFO(os.fstat(fd).st_mode), 'wrapper capability must be an inherited pipe')
    with os.fdopen(fd,'rb',closefd=True) as stream:
        raw = stream.read(16385)
    R.need(len(raw) <= 16384, 'bounded capability')
    cap = R.parse(raw)
    R.exact_keys(cap, ('schema','parent_pid','run_id','mode','out','source_manifest','go_sha256'), 'capability')
    R.fields(cap, {'schema':1,'parent_pid':os.getppid(),'mode':mode,'out':str(out.relative_to(R.ROOT)),
                  'source_manifest':R.source_manifest()}, 'live wrapper capability')
    R.need(os.getpgrp() == os.getpid(), 'capture must lead an isolated process group')
    R.need(out == run_path(R,cap['run_id'],mode) and out.is_dir(), 'wrapper-reserved output identity')
    go = R.parse((out/'GO.json').read_bytes())
    R.need(identity(out/'GO.json')['sha256'] == cap['go_sha256'], 'go changed after admission')
    R.fields(go['content'], {'action':'single-'+mode,'run_id':cap['run_id'],'source_manifest':cap['source_manifest']},
             'capability go binding')
    parent = Path('/proc/'+str(os.getppid()))
    args = [os.fsdecode(value) for value in (parent/'cmdline').read_bytes().split(b'\0') if value]
    verify_parent_entry(R,pins,args,os.readlink(parent/'cwd'),os.readlink(parent/'exe'),cap,go)
    R.need(not (out/'OBSERVATIONS.json').exists() and not (out/'SEAL.json').exists(), 'one use worker')
    return cap


def directory_inventory(R,path):
    result = {}
    if not path.exists():
        return result
    for p in sorted(path.rglob('*')):
        R.need(not p.is_symlink(), 'output symlink refused')
        if p.is_file():
            result[str(p.relative_to(path))] = identity(p)
        else:
            R.need(p.is_dir(), 'nonregular output refused')
    return result


def bytes_under(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())


def validate_payload_inventory(R,pins,out,observations):
    R.validate_observations(observations['outputs'],pins)
    for name,spec in observations['outputs'].items():
        R.fields(identity(out/spec['file']), {k:spec[k] for k in ('bytes','sha256')}, 'output '+name)
    R.fields(identity(out/'mask.bf16le'), {'bytes':32768,'sha256':pins['mask_contract']['native_sha256']}, 'mask sidecar')
    expected = {n+'.f32le' for n in R.NAMES} | {'mask.bf16le','BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json',
        'WRAPPER_BEFORE.json','GO.json','STAGES.jsonl','OBSERVATIONS.json','stdout.log','stderr.log'}
    R.exact_keys(directory_inventory(R,out),expected,'successful preseal inventory')
    R.need(bytes_under(out) <= pins['budget']['per_capture_cap_bytes'], '34 MiB run cap')
    R.need(bytes_under(out.parent) <= pins['budget']['total_cap_bytes'], '69 MiB pair cap')
