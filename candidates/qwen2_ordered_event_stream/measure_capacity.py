"""Bounded stdlib synthetic storage measurement, never a DUT result."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import tracemalloc

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture',HERE/'test_stream.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
stream=fixture.stream

def deep_size(value,seen=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value));total=sys.getsizeof(value)
    if isinstance(value,dict):total+=sum(deep_size(k,seen)+deep_size(v,seen) for k,v in value.items())
    elif isinstance(value,(tuple,list,set)):total+=sum(deep_size(v,seen) for v in value)
    elif hasattr(value,'__dict__'):total+=deep_size(vars(value),seen)
    return total

p=argparse.ArgumentParser();p.add_argument('--rows',type=int,choices=(1,16,32),required=True);a=p.parse_args()
resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(45,45))
resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
started=time.monotonic();cpu=time.process_time()
tracemalloc.start()
with tempfile.TemporaryDirectory(prefix='event-stream-capacity-') as temp:
    path=Path(temp)/'synthetic.q2evt';limits=fixture.limits(a.rows)
    writer=stream.EventWriter(path,**limits)
    for event in fixture.fixture(a.rows):writer.append(event)
    receipt=writer.seal();writer_peak=tracemalloc.get_traced_memory()[1]
    recursive=deep_size(writer);tracemalloc.reset_peak()
    verified=stream.verify(path,**limits);replay_peak=tracemalloc.get_traced_memory()[1]
    if verified['sha256']!=receipt['fully_written_sha256']:raise ValueError('identity')
    output=dict(status='SYNTHETIC_STORAGE_ONLY_NOT_DUT',
        source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('stream.py','test_stream.py','measure_capacity.py')},
        rows=a.rows,events=receipt['count'],
        bytes=verified['bytes'],file_sha256=verified['sha256'],
        writer_recursive_python_size_bytes=recursive,writer_tracemalloc_peak_bytes=writer_peak,
        replay_tracemalloc_peak_bytes=replay_peak,process_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
        limits=dict(address_space_bytes=384*1024**2,cpu_seconds=45,file_bytes=64*1024**2,fd_count=64),
        notes=['Raw records generated lazily; no retained event list/canonical array/full JSON string.',
               'Synthetic hashes are 64-char strings; ticket/edge counts small, not conservative output-byte maximum.',
               'Recursive getsizeof is not RSS; tracemalloc is Python allocations; maxrss is this synthetic process only.',
               'No tensors, target imports, native, official reference, timing throughput or RTL.'])
print(json.dumps(output,sort_keys=True))
