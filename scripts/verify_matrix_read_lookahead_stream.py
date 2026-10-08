#!/usr/bin/env python3
"""Verify every full512-lane record as a bounded stream; retain hash and summary.

This worker never grants numerical acceptance from a digest alone. The complete
raw stream must pass the independent source/oracle consumer through EOF. No
trace records or lane values are dropped, sampled, or replaced with a checksum.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from verify_matrix_norm_rope_tile16_trace import verify_trace

class DigestStream:
    def __init__(self, stream):
        self.stream=stream;self.digest=hashlib.sha256();self.bytes=0;self.lines=0
    def __iter__(self):return self
    def __next__(self):
        line=next(self.stream);raw=line.encode('utf-8')
        self.digest.update(raw);self.bytes+=len(raw);self.lines+=1
        return line


def verify_stream(stream,vectors,*,suite):
    wrapped=DigestStream(stream)
    result=verify_trace(wrapped,vectors,suite=suite,require_inputs=True)
    return {'independent_trace':result,'trace_sha256':wrapped.digest.hexdigest(),
            'trace_bytes':wrapped.bytes,'trace_records':wrapped.lines,
            'raw_trace_retained':False,'replay_requires_regeneration':True,
            'verification':'complete_raw_stream_all512_lanes_through_EOF'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fifo',type=Path,required=True);p.add_argument('--vectors',type=Path,required=True)
    p.add_argument('--suite',choices=('main','all'),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    with a.fifo.open('r',encoding='utf-8',newline='') as stream:result=verify_stream(stream,a.vectors,suite=a.suite)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
