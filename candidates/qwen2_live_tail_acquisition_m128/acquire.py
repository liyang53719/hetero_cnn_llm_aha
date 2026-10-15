#!/usr/bin/env python3
"""Fresh pinned Qwen2 tail HTTP206 acquisition only; default is metadata-only."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'candidates/qwen2_live_tail_acquisition_m128'
PREFIX = 'work/qwen2_live_tail_acquisition_m128'
OLD = 'candidates/qwen2_live_tail_inputs_m128'
OLD_RECIPE_SHA256 = 'cf1a4ff9b12f9047f034a12f3660b3fa6b6af8c071e50f925c75c3f01ad7296b'
PIN_SHA256 = 'b521249da785c6a221a03a1dac9b2eda385ecac45dc945b3814716422c6fa3a0'
URL = 'https://huggingface.co/Qwen/Qwen2-1.5B-Instruct/resolve/ba1cf1846d7df0a0591d6c00649f57e798519da8/model.safetensors'
STATUS = 'FRESH_PINNED_TAIL_SUBSET_ONLY'
SEAL = 'FRESH_ACQUISITION.json'
BOUNDARIES = dict(historical_pass_inherited=False, old_manifest_recreated=False,
    full_checkpoint_sha256_verified=False, official_forward_executed=False,
    numerical_model_executed=False, rtl_executed=False, materialization_executed=False)


class Rejected(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise Rejected(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def safe_path(root, relative):
    need(type(relative) is str and relative and '\\' not in relative, 'path spelling')
    path = Path(relative)
    need(not path.is_absolute() and all(p not in ('', '.', '..') for p in relative.split('/')),
         'canonical repository-relative path required')
    current = root.resolve()
    for part in path.parts:
        current /= part
        need(not current.is_symlink(), 'symlink path refused')
    need(current.resolve().is_relative_to(root.resolve()), 'path escaped root')
    return current


def stage_path(root, relative):
    path = safe_path(root, relative)
    parts = relative.split('/')
    need(len(parts) == 4 and '/'.join(parts[:2]) == PREFIX and
         all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', p) for p in parts[2:]),
         'fresh sibling namespace/run/stage required')
    return path


def identity(path):
    need(path.is_file() and not path.is_symlink(), 'regular file required')
    h, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''):
            size += len(part)
            h.update(part)
    return dict(bytes=size, sha256=h.hexdigest())


def load_contract(root=ROOT):
    """Reuse the unchanged, hash-bound metadata validator, never its old loader."""
    source_path = safe_path(root, OLD+'/recipe.py')
    source = source_path.read_bytes()
    need(digest(source) == OLD_RECIPE_SHA256, 'original validator identity drift')
    namespace = dict(__name__='tail_acquisition_metadata_only', __file__=str(source_path))
    exec(compile(source, str(source_path), 'exec'), namespace)
    pins = namespace['load_pins'](root)
    need(namespace['PINS_SHA256'] == PIN_SHA256, 'fixed pin identity drift')
    namespace['source_check'](root, pins)
    need(pins['shard']['url'] == URL and pins['shard']['checkpoint_file_bytes'] == 3087467144,
         'fixed official shard drift')
    need(pins['raw_bytes'] == 87297024 and len(pins['tensors']) == 5 and
         sum(len(t['segments']) for t in pins['tensors']) == 14, 'bounded inventory drift')
    return namespace, pins


def snapshot(root, pins):
    paths = set(pins['sources']) | {OLD+'/recipe.py', OLD+'/pins.json', PACKAGE+'/acquire.py'}
    return {name: identity(safe_path(root, name)) for name in sorted(paths)}


def response_bytes(response, segment, pins):
    """Validate status and range before accepting any response body."""
    size, start, end = segment['bytes'], segment['start'], segment['end']
    need(type(size) is int and 0 < size <= 8388608 and end-start+1 == size, 'bounded segment')
    expected = f"bytes {start}-{end}/{pins['shard']['checkpoint_file_bytes']}"
    need(response.status == 206, 'HTTP206 required; body refused')
    need(response.headers.get('Content-Range') == expected, 'Content-Range drift; body refused')
    need(response.headers.get('Content-Length') == str(size), 'Content-Length drift; body refused')
    need(response.headers.get('Content-Encoding', 'identity') == 'identity', 'encoded body refused')
    raw = response.read(size+1)
    need(len(raw) == size and digest(raw) == segment['sha256'], 'segment byte/hash mismatch')
    return raw, dict(acquired_at=stamp(), requested_url=URL,
        request_range=f'bytes={start}-{end}', status=206, content_range=expected,
        bytes=len(raw), sha256=digest(raw))


def download(segment, pins):
    import urllib.request
    need(pins['shard']['url'] == URL, 'official URL required')
    request = urllib.request.Request(URL, headers={
        'Range': f"bytes={segment['start']}-{segment['end']}",
        'Accept-Encoding': 'identity', 'User-Agent': 'hetero-qwen2-tail-acquisition/1'})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response_bytes(response, segment, pins)


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def parse_time(value):
    need(type(value) is str, 'timestamp type')
    time = dt.datetime.fromisoformat(value)
    need(time.utcoffset() == dt.timedelta(0), 'UTC timestamp required')
    return time


def read_new(root, relative, namespace, pins):
    directory = stage_path(root, relative)
    raw_seal = safe_path(root, relative+'/'+SEAL).read_bytes()
    manifest = namespace['parse'](raw_seal)
    expected = dict(schema=1, status=STATUS, acquisition='fresh_HTTP206',
        model_id=pins['model_id'], revision=pins['revision'], pins_sha256=PIN_SHA256,
        output_directory=relative, payload_bytes=87297024, http_range_count=14,
        boundaries=BOUNDARIES)
    need(type(manifest) is dict and set(manifest) == set(expected)|{
         'started_at','completed_at','before','after','tensors'}, 'manifest exact fields')
    namespace['fields'](manifest, expected, 'new acquisition manifest')
    before, after = parse_time(manifest['started_at']), parse_time(manifest['completed_at'])
    need(before <= after, 'timestamp ordering')
    current = snapshot(root, pins)
    need(namespace['same'](manifest['before'],current) and namespace['same'](manifest['after'],current),
         'source boundary drift')
    expected_files = {SEAL}
    need(type(manifest['tensors']) is list and len(manifest['tensors']) == 5, 'five tensor records')
    for entry, tensor in zip(manifest['tensors'], pins['tensors']):
        need(set(entry) == set(tensor)|{'file','http_ranges'}, 'tensor record exact fields')
        namespace['fields'](entry,tensor,'tensor record')
        name = tensor['local_name']+'.bin'
        need(entry['file'] == name, 'fixed tensor filename')
        expected_files.add(name)
        need(type(entry['http_ranges']) is list and len(entry['http_ranges']) == len(tensor['segments']),
             'receipt coverage')
        for receipt, segment in zip(entry['http_ranges'],tensor['segments']):
            namespace['verify_http'](receipt,segment,pins)
            need(before <= parse_time(receipt['acquired_at']) <= after, 'receipt acquisition interval')
        namespace['validate_raw_bytes'](safe_path(root,relative+'/'+name).read_bytes(),tensor)
    need({p.name for p in directory.iterdir()} == expected_files, 'unexpected or missing acquisition file')
    need(namespace['same'](snapshot(root,pins),current), 'source drift during readback')
    return dict(status='VERIFIED_FRESH_TAIL_RAW_BYTES_ONLY', directory=relative,
        payload_bytes=87297024, tensor_count=5, http_range_count=14,
        manifest_sha256=digest(raw_seal), boundaries=BOUNDARIES)


def acquire(root, relative, namespace, pins):
    output = stage_path(root,relative)
    need(not output.exists(), 'output must be absent; no resume/overwrite')
    before = snapshot(root,pins)
    started = stamp()
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(exist_ok=False)
    records = []
    for tensor in pins['tensors']:
        data, receipts = bytearray(), []
        for segment in tensor['segments']:
            raw, receipt = download(segment,pins)
            namespace['verify_http'](receipt,segment,pins)
            data.extend(raw)
            receipts.append(receipt)
        namespace['validate_raw_bytes'](bytes(data),tensor)
        name = tensor['local_name']+'.bin'
        write_new(output/name,data)
        need(identity(output/name) == {k:tensor[k] for k in ('bytes','sha256')}, 'tensor readback drift')
        records.append({**tensor,'file':name,'http_ranges':receipts})
    after = snapshot(root,pins)
    need(namespace['same'](before,after), 'source drift during acquisition')
    manifest = dict(schema=1,status=STATUS,acquisition='fresh_HTTP206',
        model_id=pins['model_id'],revision=pins['revision'],pins_sha256=PIN_SHA256,
        output_directory=relative,payload_bytes=87297024,http_range_count=14,
        started_at=started,completed_at=stamp(),before=before,after=after,
        tensors=records,boundaries=BOUNDARIES)
    write_new(output/SEAL,encode(manifest))
    return read_new(root,relative,namespace,pins)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=('check','acquire','audit'),default='check')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--out')
    parser.add_argument('--subset')
    args = parser.parse_args(argv)
    if args.action == 'check':
        need(not any((args.execute,args.download,args.out,args.subset)), 'cold check has no execution options')
    elif args.action == 'acquire':
        need(args.execute and args.download and args.out and not args.subset,
             'acquire requires --execute --download --out only')
    else:
        need(args.execute and args.subset and not args.download and not args.out,
             'audit requires --execute --subset only')
    namespace,pins = load_contract()
    if args.action == 'check':
        result = dict(status='NOT_EXECUTED',cold_check='PASS',network_used=False,
            raw_payload_read=False,outputs_written=False,tensor_count=5,http_range_count=14,
            payload_bytes=87297024,boundaries=BOUNDARIES)
    elif args.action == 'acquire':
        result = acquire(ROOT,args.out,namespace,pins)
    else:
        result = read_new(ROOT,args.subset,namespace,pins)
    print(json.dumps(result,sort_keys=True))
    return result


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,KeyError,TypeError,ImportError) as error:
        print(json.dumps(dict(status='REJECTED',reason=str(error))),file=sys.stderr)
        raise SystemExit(2)
