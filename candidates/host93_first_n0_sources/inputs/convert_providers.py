"""Fixed raw13 -> provider14 stdlib adapter. Default checks source only.
No project imports, network, reference payloads, native program or old framing.
"""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import struct
import sys
import time

PLAN_BYTES = 17884
PLAN_SHA256 = 'ab1fabb72d69f0f196dafd19fe7324a1413b000952e0ee04baa3cbaaff4a14ac'
CHUNK = 65536
MAX_RAW = 27525120
HERE = Path(__file__).resolve().parent


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def check_sources(repo):
    raw = Path(__file__).with_name('CONVERSION_SPEC.json').read_bytes()
    require(digest(raw) == {'bytes': PLAN_BYTES, 'sha256': PLAN_SHA256}, 'fixed plan bytes drift')
    plan = json.loads(raw)
    repo = Path(repo).resolve(strict=True)
    sources = {}
    for pin in plan['source_files']:
        name = pin['path']
        require(name and not name.startswith('/') and '\\' not in name and
                all(p not in ('', '.', '..') for p in name.split('/')), 'unsafe relative source')
        path = repo / name
        require(not path.is_symlink() and path.resolve().is_relative_to(repo), 'source path escape')
        require(path.stat().st_size == pin['bytes'] and pin['bytes'] < 200000, 'source size drift')
        data = path.read_bytes()
        require(digest(data) == {k: pin[k] for k in ('bytes', 'sha256')}, 'source identity drift')
        require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == pin['git_blob'],
                'source Git blob drift')
        sources[name] = data
    # Parse the exact verified buffers; execute no project FunctionDef or import.
    for pin in plan['original_function_pins']:
        data = sources[pin['source']]; lines = data.splitlines(keepends=True)
        nodes = [n for n in ast.parse(data).body
                 if isinstance(n, ast.FunctionDef) and n.name == pin['function']]
        require(len(nodes) == 1, 'function missing or duplicated')
        node = nodes[0]
        require((node.lineno, node.end_lineno) == (pin['first_line'], pin['last_line']), 'function location drift')
        require(digest(b''.join(lines[node.lineno-1:node.end_lineno])) ==
                {k: pin[k] for k in ('bytes', 'sha256')}, 'function bytes drift')
    projection = json.loads(sources[plan['identity_relative_path']])['projection']
    expected = {p['name']: p for p in projection['providers']}
    raw_by_name = {p['local_name']: p for p in projection['raw_tensors']}
    layout = json.loads(sources['development_snapshots/canonical_host_metadata_source_20261018/EXPECTED_LAYOUT.json'])
    order = [a['name'] for a in layout['allocations'] if a['readonly']]
    require(order == plan['provider_order'] == [p['name'] for p in plan['providers']], 'original provider order drift')
    for i, p in enumerate(plan['providers']):
        require(p['provider_index'] == i and p['canonical16_index'] == i+2, 'provider index drift')
        e = expected[p['name']]
        require((p['base'],p['output_bytes'],p['output_shape'],p['descriptor_dtype'],p['expected_output_sha256']) ==
                (e['base'],e['bytes'],e['shape'],e['descriptor_dtype'],e['sha256']), 'expected provider drift')
        if p['raw_tensor'] is not None:
            t = p['raw_tensor']; require(t == raw_by_name[t['local_name']], 'raw identity drift')
            if p['name'].startswith('w'):
                require(t['shape'][::-1] == p['output_shape'] and t['bytes'] == p['output_bytes'],
                        'BF16 transpose dimensions drift')
            elif p['name'] != 'x':
                require(2*t['bytes'] == p['output_bytes'], 'FP32 expansion size drift')
    require(len(raw_by_name)==13 and len(expected)==14 and
            sum(t['bytes'] for t in raw_by_name.values())==94382080 and
            sum(p['output_bytes'] for p in plan['providers'])==94916608, 'input/output inventory drift')
    require(projection['original_input']['token_ids'] == projection['original_input']['positions'] ==
            plan['fp32_contract']['token_ids'] == list(range(128)), 'token/position identity drift')
    require(projection['original_input']['rope_theta']==1000000.0 and
            projection['original_input']['rope_table_recipe']=='canonical_cpp_initialize_double_libm_then_FP32',
            'rope recipe identity drift')
    return plan


def no_symlinks(path):
    path = Path(os.path.abspath(path))
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink path refused')
    return path


def tick(deadline):
    require(time.monotonic() < deadline, 'shared wall deadline exceeded')


def exact_hash(path, size, deadline):
    path = no_symlinks(path)
    hasher, count = hashlib.sha256(), 0
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'nonregular or wrong-size file')
        while count < size:
            tick(deadline)
            chunk = stream.read(min(CHUNK, size-count))
            require(chunk and len(chunk) <= size-count, 'short file read')
            hasher.update(chunk); count += len(chunk)
        require(stream.read(1) == b'', 'trailing bytes')
        after = os.fstat(stream.fileno())
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) ==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns), 'file changed during read')
    return hasher.hexdigest()


def read_raw(path, expected, deadline):
    """One owned buffer; conversion consumes exactly the buffer hashed here."""
    size = expected['bytes']
    require(type(size) is int and 0 < size <= MAX_RAW and size % 2 == 0, 'invalid raw extent')
    path = no_symlinks(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'raw file type/size mismatch')
        raw = bytearray(size); view = memoryview(raw); offset = 0
        while offset < size:
            tick(deadline)
            count = stream.readinto(view[offset:min(offset+CHUNK,size)])
            require(type(count) is int and 0 < count <= min(CHUNK,size-offset), 'short raw read')
            offset += count
        require(stream.read(1) == b'', 'raw trailing bytes')
        after = os.fstat(stream.fileno())
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) ==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns), 'raw changed during read')
    require(hashlib.sha256(raw).hexdigest() == expected['sha256'], 'raw SHA256 mismatch')
    return raw


def transpose_bf16_rows(raw, shape, deadline):
    """Byte-container adaptation of original transpose_bf16; no FP conversion."""
    require(len(shape)==2 and all(type(n) is int and n>0 for n in shape), 'bad matrix shape')
    rows, cols = shape
    require(len(raw)==2*rows*cols and 2*rows<=CHUNK, 'transpose size or row bound')
    for col in range(cols):
        tick(deadline)
        out = bytearray(2*rows)
        out[0::2] = raw[2*col::2*cols]
        out[1::2] = raw[2*col+1::2*cols]
        yield out


def fp32_from_bf16_chunks(raw, deadline, first_word=0, words=None):
    """Original uint16 -> uint32 << 16; validate entire raw before selection."""
    require(len(raw)>0 and len(raw)%2==0, 'odd or empty BF16 raw')
    total = len(raw)//2
    if words is None: words = total
    require(type(first_word) is int and type(words) is int and
            0<=first_word<=total and 0<words<=total-first_word, 'BF16 selection outside raw')
    for i, (word,) in enumerate(struct.iter_unpack('<H', raw)):
        if i % 16384 == 0: tick(deadline)
        require((word & 0x7f80) != 0x7f80, 'nonfinite original BF16 input')
    start, stop = 2*first_word, 2*(first_word+words)
    while start < stop:
        tick(deadline)
        end = min(stop, start+CHUNK//2)
        out = bytearray(2*(end-start))
        out[2::4] = raw[start:end:2]
        out[3::4] = raw[start+1:end:2]
        yield out
        start = end


def rope_chunks(rows, deadline):
    """Original rope_bytes formula/layout; only NumPy storage is replaced."""
    require(rows in (16,128), 'public trig rows differ')
    tables = bytearray(2*1024*64*4)
    for t in range(rows):
        tick(deadline)
        for j in range(64):
            angle = t / math.pow(1000000.0, 2.0 * j / 128)
            struct.pack_into('<f', tables, ((0*1024+t)*64+j)*4, math.cos(angle))
            struct.pack_into('<f', tables, ((1*1024+t)*64+j)*4, math.sin(angle))
    for offset in range(0,len(tables),CHUNK):
        yield memoryview(tables)[offset:offset+CHUNK]


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def commit_new(part, final):
    # Same-filesystem link fails if final exists; never overwrites caller data.
    os.link(part, final)
    part.unlink()
    sync_dir(final.parent)


def write_provider(directory, name, chunks, expected, deadline):
    require(name and all(c.isascii() and (c.isalnum() or c=='_') for c in name), 'bad provider name')
    part, final = directory/(name+'.part'), directory/(name+'.bin')
    require(not final.exists() and not final.is_symlink(), 'provider destination exists')
    hasher, count = hashlib.sha256(), 0
    with part.open('xb') as stream:
        for chunk in chunks:
            tick(deadline)
            require(isinstance(chunk,(bytes,bytearray,memoryview)) and 0<len(chunk)<=CHUNK,
                    'bad provider chunk')
            require(count+len(chunk)<=expected['output_bytes'], 'provider overflow')
            require(stream.write(chunk)==len(chunk), 'short provider write')
            hasher.update(chunk); count += len(chunk)
        require(count==expected['output_bytes'], 'provider output short')
        require(hasher.hexdigest()==expected['expected_output_sha256'], 'provider SHA256 mismatch')
        stream.flush(); os.fsync(stream.fileno())
    require(exact_hash(part,count,deadline)==expected['expected_output_sha256'], 'provider readback SHA256 mismatch')
    commit_new(part,final)
    return {'name':name,'file':final.name,'bytes':count,'sha256':hasher.hexdigest()}


def check_receipt(raw_root, spec, deadline):
    pin = spec['raw_receipt']; path = no_symlinks(raw_root/pin['filename'])
    tick(deadline)
    with path.open('rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size==pin['bytes'] and pin['bytes']<65536,
                'raw receipt file type/size mismatch')
        data=stream.read(pin['bytes']+1)
        require(stream.read(1)==b'', 'raw receipt trailing bytes')
    require(digest(data)=={k:pin[k] for k in ('bytes','sha256')}, 'raw completion receipt drift')
    receipt = json.loads(data)
    require(receipt['status']==pin['status'] and receipt['plan_sha256']==pin['plan_sha256'] and
            receipt['model_id']==spec['model_id'] and receipt['revision']==spec['revision'] and
            receipt['payload_bytes']==spec['raw_payload_bytes'], 'raw receipt identity mismatch')
    expected = {p['raw_tensor']['local_name']:p['raw_tensor'] for p in spec['providers'] if p['raw_tensor']}
    require(len(receipt['tensors'])==13 and len({t['local_name'] for t in receipt['tensors']})==13,
            'raw receipt missing/duplicate tensor')
    for actual in receipt['tensors']:
        require(actual['local_name'] in expected, 'raw receipt unknown tensor')
        want = expected[actual['local_name']]
        require(all(actual[k]==want[k] for k in ('local_name','dtype','shape','bytes','sha256')),
                'raw receipt tensor identity mismatch')


def prepare_output(repo, raw_root, output, spec):
    output = no_symlinks(output)
    require(not output.exists(), 'fresh output directory required')
    parent = no_symlinks(output.parent).resolve(strict=True)
    output = parent/output.name
    require(not any(output.is_relative_to(p) for p in (repo,raw_root,HERE)), 'output must be outside input/source trees')
    limits = spec['limits']
    require(spec['provider_payload_bytes']+limits['metadata_reserve_bytes']<=limits['output_disk_bytes'],
            'fixed output exceeds disk cap')
    require(shutil.disk_usage(parent).free>=limits['minimum_free_disk_bytes'], 'insufficient free disk')
    output.mkdir(mode=0o700)
    sync_dir(parent)
    return output


def collect(spec, raw_root, output, deadline):
    completed = []
    for provider in spec['providers']:
        tick(deadline); name = provider['name']
        if name=='rope':
            chunks = rope_chunks(128,deadline)
        else:
            raw = read_raw(raw_root/provider['raw_relative_path'],provider['raw_tensor'],deadline)
            if name.startswith('w'):
                chunks = transpose_bf16_rows(raw,provider['raw_tensor']['shape'],deadline)
            elif name=='x':
                require(spec['fp32_contract']['token_ids']==list(range(128)), 'fixed token IDs changed')
                chunks = fp32_from_bf16_chunks(raw,deadline,first_word=0,words=128*1536)
            else:
                chunks = fp32_from_bf16_chunks(raw,deadline)
        completed.append(write_provider(output,name,chunks,provider,deadline))
        del chunks
        if name!='rope': del raw
    require([p['name'] for p in completed]==spec['provider_order'] and len(completed)==14,
            'provider completion order differs')
    report = {'schema':1,'status':'FIXED_PROVIDER14_BYTES_VERIFIED','conversion_spec_sha256':PLAN_SHA256,
              'raw_receipt_sha256':spec['raw_receipt']['sha256'],'providers':completed,
              'provider_payload_bytes':sum(p['bytes'] for p in completed),
              'canonical_loader_executed':False,'full_host_ready':False,'launch_ready':False,
              'reference_payload_used':False,'network_or_native_executed':False}
    data=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
    require(len(data)<spec['limits']['metadata_reserve_bytes'], 'completion metadata too large')
    part=output/'PROVIDERS.part'
    with part.open('xb') as stream:
        require(stream.write(data)==len(data), 'short completion metadata write')
        stream.flush();os.fsync(stream.fileno())
    tick(deadline);commit_new(part,output/'PROVIDERS.json')
    return report


def activate_limits(spec, deadline):
    require(hasattr(signal,'pthread_sigmask') and
            signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]), 'blocked deadline signal')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0), 'existing timer conflict')
    tick(deadline)
    for kind,ceiling in ((resource.RLIMIT_AS,spec['limits']['address_space_bytes']),
                         (resource.RLIMIT_CPU,spec['limits']['cpu_seconds'])):
        soft,hard=resource.getrlimit(kind)
        caps=[ceiling]+[n for n in (soft,hard) if n!=resource.RLIM_INFINITY]
        new_hard = min([ceiling]+([hard] if hard!=resource.RLIM_INFINITY else [])) if kind==resource.RLIMIT_CPU else hard
        resource.setrlimit(kind,(min(caps),new_hard))
    def expired(_signum,_frame): raise TimeoutError('shared wall deadline exceeded')
    old=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,max(0.001,deadline-time.monotonic()))
    return old


def main(argv=None):
    start=time.monotonic()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--raw-root',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    spec=check_sources(args.repo)
    if not args.execute:
        print(json.dumps({'status':'SOURCE_CHECK_ONLY','raw_tensors':13,'providers':14,
                          'raw_payload_read':False,'conversion_executed':False}))
        return 0
    require(args.raw_root is not None and args.output is not None, 'execute requires raw root and fresh output')
    repo=no_symlinks(args.repo).resolve(strict=True)
    raw_root=no_symlinks(args.raw_root).resolve(strict=True)
    deadline=start+spec['limits']['wall_seconds']
    old=activate_limits(spec,deadline)
    try:
        check_receipt(raw_root,spec,deadline)
        output=prepare_output(repo,raw_root,args.output,spec)
        result=collect(spec,raw_root,output,deadline)
        print(json.dumps({'status':result['status'],'providers':14,'bytes':result['provider_payload_bytes']}))
        return 0
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'FAILED_NO_COMPLETION_CLAIM','error_type':type(error).__name__,
                          'message':str(error)}),file=sys.stderr)
        raise SystemExit(1)
