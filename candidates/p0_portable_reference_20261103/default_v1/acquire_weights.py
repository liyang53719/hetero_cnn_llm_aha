#!/usr/bin/env python3
"""One fresh, sequential P0 acquisition; historical SHA required before acceptance.

Only the pinned header and twelve ranges are fetched, in <=8 MiB responses.
No retry/resume/reuse, no model loading, and no exported network logs.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import urllib.request
from prepare_runtime import StageFailure, failure_receipt, Redirect, allowed_url, need, read_json, safe_name, sha, unique, write_json

CREATED_OUTPUT = None
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
URL = 'https://huggingface.co/Qwen/Qwen2-1.5B-Instruct/resolve/' + REVISION + '/model.safetensors'
SHARD_BYTES = 3087467144
HEADER_BYTES = 38536
HEADER_SHA = '124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987'
WEIGHT_BYTES = 93595648
MAX_BLOCK = 8 << 20
# Exact service endpoints only, not arbitrary suffix matches or HTTP downgrades.
HOSTS = {'huggingface.co', 'cdn-lfs.huggingface.co', 'cdn-lfs-us-1.huggingface.co',
         'cdn-lfs.hf.co', 'cdn-lfs-us-1.hf.co', 'cas-bridge.xethub.hf.co', 'us.aws.cdn.hf.co'}


def weight_check(ok, reason='PRECHECK_PIN', mismatch=False):
    if not ok:
        raise StageFailure(reason, mismatch)


def progress(output, checked, mismatch_count):
    need(type(checked) is int and 0 <= checked <= 12 and mismatch_count in (0, 1), 'progress bound')
    path = output / 'WEIGHT_CHECKS.json'
    temporary = output / 'WEIGHT_CHECKS.json.next'
    need(not path.is_symlink() and not temporary.exists(), 'owned progress path')
    write_json(temporary, {'schema': 'P0_WEIGHT_CHECKS_V1', 'checked': checked,
                           'mismatch_count': mismatch_count})
    temporary.replace(path)


def fetch(opener, start, end, budget):
    n = end - start + 1
    need(type(start) is int and type(end) is int and 0 <= start <= end < SHARD_BYTES
         and n <= MAX_BLOCK, 'bounded exact range')
    need(time.monotonic() - budget['started'] < 600, 'acquisition wall limit')
    need(budget['requested'] + n <= WEIGHT_BYTES + HEADER_BYTES, 'aggregate range budget')
    budget['requested'] += n
    req = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{end}',
                                              'Accept-Encoding': 'identity'})
    with opener.open(req, timeout=60) as response:
        allowed_url(response.geturl(), HOSTS)
        need(response.status == 206, 'range status')
        need(response.headers.get('Content-Range') == f'bytes {start}-{end}/{SHARD_BYTES}', 'range identity')
        need(response.headers.get('Content-Length') == str(n), 'range length')
        need(response.headers.get('Content-Encoding', 'identity') == 'identity', 'encoded range')
        body = response.read(n + 1)
        need(len(body) == n, 'exact range body')
    budget['received'] += n
    need(time.monotonic() - budget['started'] < 600, 'acquisition wall limit')
    return body


def acquire(output, frozen):
    global CREATED_OUTPUT
    manifest = read_json(frozen)
    weights = manifest['weights']
    need(len(weights) == 12 and len({w['name'] for w in weights}) == 12, '12 unique weights')
    need(sum(w['bytes'] for w in weights) == WEIGHT_BYTES, 'weight byte budget')
    for w in weights:
        need('/' not in str(safe_name(w['name'])) and w['name'].startswith('model.layers.0.'), 'layer tensor name')
        need(w['url'] == URL and w['shard_bytes'] == SHARD_BYTES, 'fixed checkpoint source')
        weight_check(w['dtype'] == 'BF16' and all(type(d) is int and d > 0 for d in w['shape'])
             and 2 * math.prod(w['shape']) == w['bytes'] == w['end'] - w['start'] + 1,
             'WEIGHT_HASH', mismatch=True)
        need(len(w['sha256']) == 64 and all(c in '0123456789abcdef' for c in w['sha256']), 'historical hash')
    need(not output.exists() and not output.is_symlink(), 'fresh weights root required')
    output.mkdir()
    CREATED_OUTPUT = output.resolve()
    progress(output, 0, 0)
    folder = output / 'qwen2_1p5b'
    folder.mkdir()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect(HOSTS))
    budget = {'started': time.monotonic(), 'received': 0, 'requested': 0}
    header = fetch(opener, 0, HEADER_BYTES - 1, budget)
    weight_check(hashlib.sha256(header).hexdigest() == HEADER_SHA, 'PRECHECK_PIN')
    need(struct.unpack('<Q', header[:8])[0] == HEADER_BYTES - 8, 'header prefix')
    parsed = json.loads(header[8:].decode('utf-8'), object_pairs_hook=unique)
    # The pinned header is independently re-bound to every semantic range.
    for w in weights:
        h = parsed[w['name']]
        weight_check(h['dtype'] == w['dtype'] and h['shape'] == w['shape']
             and h['data_offsets'] == [w['start'] - HEADER_BYTES, w['end'] + 1 - HEADER_BYTES],
             'WEIGHT_HASH', mismatch=True)
    with (output / 'header.bin').open('xb') as f:
        f.write(header)
    records = []
    fields = ('name', 'dtype', 'shape', 'bytes', 'start', 'end', 'url', 'shard_bytes')
    for w in weights:
        partial = folder / (w['name'] + '.partial')
        final = folder / (w['name'] + '.bin')
        h = hashlib.sha256()
        count = 0
        with partial.open('xb') as dst:
            for start in range(w['start'], w['end'] + 1, MAX_BLOCK):
                body = fetch(opener, start, min(start + MAX_BLOCK - 1, w['end']), budget)
                dst.write(body)
                h.update(body)
                count += len(body)
        weight_check(count == w['bytes'] and h.hexdigest() == w['sha256'], 'WEIGHT_HASH', mismatch=True)
        partial.rename(final)
        receipt = {k: w[k] for k in fields}
        receipt.update(model='qwen2_1p5b', revision=REVISION, verification='EXACT_NAME_SHA256',
                       expected_sha256=w['sha256'], actual_sha256=h.hexdigest(), actual_bytes=count,
                       file=str(final.relative_to(output)),
                       status='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT')
        write_json(folder / (w['name'] + '.receipt.json'), receipt)
        records.append({'name': w['name'], 'bytes': count, 'sha256': h.hexdigest()})
        progress(output, len(records), 0)
    need(budget['received'] == WEIGHT_BYTES + HEADER_BYTES, 'exact aggregate acquisition')
    # Recheck all accepted raw files before issuing the aggregate receipt.
    for w in weights:
        p = folder / (w['name'] + '.bin')
        weight_check(p.stat().st_size == w['bytes'] and sha(p) == w['sha256'], 'WEIGHT_HASH', mismatch=True)
    write_json(output / 'WEIGHTS_RECEIPT.json', {
        'schema': 'P0_DEFAULT_EXACT_WEIGHTS_V1', 'status': 'EXACT_HISTORICAL_WEIGHT_HASHES',
        'checked': 12, 'bytes': WEIGHT_BYTES, 'network_bytes': budget['received'],
        'header_sha256': HEADER_SHA, 'frozen_sha256': sha(frozen),
        'source_sha256': sha(__file__), 'weights': records})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    args = parser.parse_args()
    try:
        acquire(args.output, args.frozen)
    except Exception as exc:
        if CREATED_OUTPUT is not None:
            current = args.output / 'WEIGHT_CHECKS.json'
            checked = read_json(current)['checked'] if current.is_file() else 0
            mismatch = int(isinstance(exc, StageFailure) and exc.mismatch)
            # Checked includes the failed comparison, not only accepted tensors.
            progress(args.output, min(12, checked + mismatch), mismatch)
        if CREATED_OUTPUT is not None:
            failure_receipt(CREATED_OUTPUT, exc, 'PRECHECK_PIN')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
