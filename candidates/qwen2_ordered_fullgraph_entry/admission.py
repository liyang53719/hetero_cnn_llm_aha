"""Source/metadata preparation only. No loader, payload reader or execution gate.

The generated document is intentionally NOT_READY even if every metadata check
passes. A future independently reviewed run must rehash actual payloads, bind a
real reference and new resource/launch limits. Historical PASS is never copied.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ELF_SHA = 'c03ab303a6d0780f379a13f8f0339872a6b00e066c8481b8e8f39a16243cf5b8'
PINS_SHA = '48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
RUNTIME_SHA = '793635db42c92f03ea022cafed313f49a40b6d6de05b33fb8baff60f33056030'
SOURCE_SHA = '4ac834617f8566a9467f702faf81c730f2e23dcb1b97dbdd5ebdd33821a8d923'
COMMIT = '8b3c5a2ea6e9615f5a2a8c37ad5392c6d4a7941a'
ROLES = {'x': ([128,1536],4), 'gamma0': ([1536],4), 'gamma1': ([1,1536],4),
         'wq': ([1536,1536],2), 'wk': ([1536,256],2), 'wv': ([1536,256],2),
         'bq': ([1536],4), 'bk': ([256],4), 'bv': ([256],4),
         'rope': ([2,1024,64],4), 'wo': ([1536,1536],2),
         'wg': ([1536,8960],2), 'wu': ([1536,8960],2), 'wd': ([8960,1536],2)}


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    need(type(value) is str and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), 'invalid SHA256')
    return value


def safe_relative(value):
    need(type(value) is str and value and '\\' not in value and
         not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts,
         'non-relative public source path')
    return value


def prepare(source, pins, runtime, *, rows=16, enabled=False,
            qk_profile=2, pv_profile=0, raw_kv_transport=False):
    need(type(rows) is int and rows == 16, 'this preparation is M16 only')
    need(enabled is False, 'preparation cannot enable execution')
    need(type(qk_profile) is int and qk_profile == 2 and
         type(pv_profile) is int and pv_profile == 0 and raw_kv_transport is False,
         'requires QK-only profile2 and legacy PV0, without rawKV')
    files = source['source_files']
    need(len(files) == source['source_file_count'] == 316 and
         source['default_enabled'] is False and source['inherited_runtime_pass'] is False,
         'exact new composed source manifest required')
    sources = {}
    for name, record in files.items():
        need(type(record['bytes']) is int and record['bytes'] >= 0, 'source extent')
        sources[safe_relative(name)] = dict(bytes=record['bytes'],sha256=digest(record['sha256']))
    producers = pins['producer_roles']
    need(set(producers) == set(ROLES), 'requires full provider14, not component qr/kr/v')
    providers = {}
    for name, (shape, itemsize) in ROLES.items():
        p, total = producers[name], itemsize
        for dimension in shape: total *= dimension
        record = p['record']
        need(record['shape'] == shape and p['bytes'] == record['bytes'] == total and
             record['dtype'] == ('float32' if itemsize == 4 else 'uint16') and
             p['sha256'] == record['sha256'], 'provider shape/dtype/extent/hash: ' + name)
        providers[name] = dict(bytes=total, sha256=digest(p['sha256']), shape=shape,
                               dtype=record['dtype'], payload_rehashed=False)
    providers['x']['active_view'] = dict(shape=[rows,1536],byte_offset=0,bytes=rows*1536*4,
                                        sha256=None, status='VIEW_HASH_PENDING')
    raw = pins['raw_tensors']
    need(len(raw) == 13 and len({p['local_name'] for p in raw}) == 13, 'raw13 closure')
    raw_records = {}
    for p in raw:
        total = 2
        for dimension in p['shape']: total *= dimension
        need(p['dtype'] == 'BF16' and total == p['bytes'], 'raw BF16 shape/extent')
        raw_records[p['local_name']] = dict(bytes=total, sha256=digest(p['sha256']),
                                            shape=p['shape'], payload_rehashed=False)
    graph = runtime['runtime_graph']
    need(len(graph['roots']) == 5 and len(graph['files']) == 19 and len(graph['edges']) == 51,
         'original R2c runtime DT_NEEDED closure')
    need(runtime['elf'] in graph['files'] and
         graph['files'][runtime['elf']]['sha256'] == ELF_SHA, 'wrong reused combined ELF')
    ids = {p: 'elf%02d' % i for i,p in enumerate(sorted(graph['files']))}
    native = {ids[p]: dict(bytes=r['bytes'],sha256=digest(r['sha256']),
                           needed=list(r.get('needed',[]))) for p,r in graph['files'].items()}
    edges = []
    for e in graph['edges']:
        need(e['from'] in ids and e['target'] in ids, 'unclosed runtime edge')
        edges.append(dict(source=ids[e['from']],target=ids[e['target']],needed=e['needed'],kind=e['kind']))
    return dict(schema='qwen2-fullgraph-preparation-v1',status='NOT_READY_PREPARATION_ONLY',
        parent_commit=COMMIT,default_enabled=False,rows=rows,qk_profile=2,pv_profile=0,
        raw_kv_transport=False,source_files=sources,provider14=providers,raw13=raw_records,
        reuse_elf_sha256=ELF_SHA,runtime_dependency_files=native,runtime_edges=edges,
        payload_bytes_rehashed=False,runtime_files_rehashed=False,native_loaded=False,
        native_executed=False,reference_executed=False,full_numeric_status='TEMP_NOT_EXECUTED',
        reference_metadata_status=pins['reference_freeze']['status'],
        blockers=['full provider14/raw13 paths and streamed hashes not verified in this preparation',
          'M16 input x view hash and independent reference input/layout identity not sealed',
          'new normal fullgraph import inventory and exact runtime mappings not qualified',
          'full reference payload/recipe closure not bound; full29 pins contain uncaptured references',
          'official29 actual observation incomplete: x/repeat_k/repeat_v/logits/cos/sin/mask',
          'whole-block resource limits, exact launch config and independent review not approved',
          'no fullgraph native execution authorization in this profile'],
        fixed_physical_macs=4096,legacy_pv_upper_bound_percent=63.57,
        hardware_cycles=None,full_wall_mac_utilization=None)


def read_pinned(path, expected):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, 'metadata source identity changed')
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',required=True)
    parser.add_argument('--reference-pins',required=True)
    parser.add_argument('--runtime-config',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    result = prepare(read_pinned(args.source_manifest,SOURCE_SHA),
                     read_pinned(args.reference_pins,PINS_SHA),
                     read_pinned(args.runtime_config,RUNTIME_SHA))
    # Exclusive creation prevents overwriting evidence, including prior failures.
    with Path(args.output).open('x') as out:
        json.dump(result,out,sort_keys=True,indent=2); out.write('\n')
    print(json.dumps(dict(status=result['status'],native_executed=False)))


if __name__ == '__main__':
    main()
