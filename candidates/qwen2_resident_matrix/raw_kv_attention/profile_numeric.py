"""Separate M4/M8 calibration preparation; original M1/M2 receipts are unchanged.

No M128 launch entry point is enabled here. Runtime and event work are software
measurements, never hardware timing. Numerical dependencies are imported lazily.
"""

def scalar_schedule(tokens):
    """All original PV16 scalar nodes in order; annotate semantic checkpoints.

    Restricted fixture guarantees every exp executes its original 17 nodes.
    Each entry is (operation, policy, stage-or-None, coordinates, select-input).
    """
    if type(tokens) is not int or tokens not in (1,2,4,8,128):
        raise ValueError('supported source profile')
    def event(op,stage=None,coords=(),input_value=False,policy='legacy_scalar'):
        return (op,policy,stage,coords,input_value)
    for token in range(tokens):
        for head in range(12):
            for key in range(token+1):
                for _ in range(8*32):yield event('bf')
                for _ in range(16):yield event('add')
                yield event('bf','dots',(token,head,key),True)
                yield event('mul')
                yield event('bf','scores',(token,head,key))
            for key in range(token+1):
                yield event('add')
                yield event('mul',policy='vector')
                yield event('add',policy='vector')
                for _ in range(7):
                    yield event('mul',policy='vector')
                    yield event('add',policy='vector')
                yield event('mul','weights',(token,head,key),policy='vector')
                yield event('add','prefix_totals',(token,head,key))
            yield event('div','inverses',(token,head))
            for col in range(8):
                for key in range(token+1):
                    yield event('mul')
                    yield event('bf','probabilities',(token,head,key))
                    for _ in range(31):yield event('bf')
                for lane in range(16):
                    yield event('bf','output',(token,head,col*16+lane))


class Checkpoints:
    """Compare semantic intermediates as emitted; retain no scalar event history."""
    def __init__(self,tokens,reference):
        self.schedule=iter(scalar_schedule(tokens));self.reference=reference;self.count=0

    def __call__(self,event):
        operation,a,b,value,policy=event
        try:op,expected_policy,stage,coords,select_input=next(self.schedule)
        except StopIteration:raise ValueError('extra scalar event') from None
        if (operation,policy)!=(op,expected_policy):raise ValueError('scalar schedule changed')
        self.count+=1
        if stage is None:return
        token,head=coords[:2];ref=self.reference
        if stage=='output':expected=int(ref.output[token*1536+head*128+coords[2]])
        elif stage=='inverses':expected=int(ref.inverses[token,head])
        else:
            name='normalized' if stage=='probabilities' else stage
            expected=int(getattr(ref,name)[token][head,coords[2]])
        if (a if select_input else value)!=expected:raise ValueError('independent intermediate mismatch: '+stage)
        if stage=='dots' and value!=int(ref.materialized_dots[token][head,coords[2]]):
            raise ValueError('materialized dot mismatch')
        if stage=='probabilities' and a!=int(ref.normalized_fp32[token][head,coords[2]]):
            raise ValueError('normalized probability mismatch')
        if stage=='output' and a!=int(ref.pv[token,head,coords[2]]):
            raise ValueError('PV final accumulator mismatch')

    def finish(self):
        if next(self.schedule,None) is not None:raise ValueError('missing scalar events')



def source_snapshot():
    from .run_numeric_ci import source_snapshot as previous,digest,repository_path,PREFIX
    result=previous()
    for name in ('streaming.py','test_streaming.py','reference_profile.py',
                 'test_reference_profile.py','profile_numeric.py','test_profile_numeric.py'):
        relative=PREFIX+name;result[relative]=digest(repository_path(relative))
    return dict(sorted(result.items()))

def run_calibration():
    """Only M4/M8 can execute; M128 remains a counted, unlaunched profile."""
    import os,time,resource,hashlib,json
    from .numeric_bridge import dependencies,AttentionKvBridge,require
    if not all(os.environ.get(name) for name in ('MATRIX_SERVICE_LIBRARY','MATRIX_SERVICE_COMPILE_RECEIPT')):
        return 2,{'status':'NOT_RUN','reason':'verified_library_required','m128_executed':False}
    # Original verification is retained; there is no build or arithmetic fallback.
    before=source_snapshot()
    from .run_numeric_ci import library_snapshot
    native_before=library_snapshot(os.environ)[2]
    d=dependencies();library=d.verified_library()
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
    from .streaming import make_observers,CoreDigest,MemoryDigest,profile
    from .reference_profile import fixture,reference
    Scalar,Matrix=make_observers(ScalarService,d.MatrixService)
    deadline=time.monotonic()+120.0
    reports=[]
    def bounded(events,limit):
        if time.monotonic()>=deadline or events>=limit:raise TimeoutError('calibration bound')
    class AddressCount:
        def __init__(self):self.count=0
        def append(self,address):
            require(type(address) is int and 0<=address<1<<64,'address observer')
            self.count+=1
    class BusTrace:
        def __init__(self):self.core=CoreDigest();self.writes=MemoryDigest()
        def append(self,q):
            self.core.append((q.tag,q.address,q.write))
            if q.write:self.writes.append(q)
    for tokens in (4,8):
        bounded(0,1)
        started=time.monotonic();data=fixture(tokens);ref=reference(tokens,*data)
        bounded(0,1)
        reference_seconds=time.monotonic()-started
        j=d.p.Job('Attention',(9<<16)|12,0x100000,0x200000,0x400000,tokens,1536,128,tokens*6144,c=0x200000+tokens*1024)
        expected_profile=profile(tokens)
        executions=[]
        for loan in (False,True):
            bounded(0,1)
            require(library.td_reset()==0,'original Matrix reset failed')
            check=Checkpoints(tokens,ref)
            scalar=Scalar(observer_callback=check);matrix=Matrix(library)
            owner=d.OfficialAttentionOwner(matrix,scalar)
            bus=d.Bus();trace=BusTrace();bus.trace=trace
            bus.reads=AddressCount();bus.writes=AddressCount()
            for base,words in zip((j.a,j.b,j.c),data):bus.input(base,tuple(int(x) for x in words))
            bus.output(j.dst,j.write_bytes)
            h=AttentionKvBridge(owner,bus,j) if loan else d.Harness(owner,bus)
            if loan:h.core_trace=CoreDigest()
            start=time.monotonic();events=1
            require(h.tick(job=j)['job_fire'],'calibration admission failed')
            ports=h.ports if loan else owner.ports
            limit=32*(192*tokens*(tokens+1)//2)+10000
            while ports()['response'] is None:
                bounded(events,limit);h.tick();events+=1
            result=ports()['response']
            require(result.status is None,'calibration owner error')
            for _ in range(3):
                bounded(events,limit);h.tick();events+=1
                require(ports()['response']==result,'held terminal changed')
            bounded(events,limit)
            require(h.tick(response_ready=True)['response_fire'],'calibration terminal not retired')
            require(owner.state=='idle' and owner.ack_bytes==j.write_bytes,'write ACK fence')
            require(bus.outputs[j.dst]<=bus.acked,'missing output ACK')
            bus.publish(owner,j);check.finish()
            require(bus.raw(j.dst)==ref.output.astype('<u4',copy=False).tobytes(),'output reference mismatch')
            counts={k:v for k,v in owner.matrix_counts.items() if k!='legacy_model_ticks'}
            for name in ('normal_steps','normal_results','legacy_replies'):
                require(counts.get(name)==expected_profile['matrix_packets'],'Matrix packet count mismatch')
            for name in ('normal_groups','normal_done'):
                require(counts.get(name)==expected_profile['matrix_groups'],'Matrix group count mismatch')
            for name in ('owner_acquires','owner_responses','owner_releases'):
                require(counts.get(name)==1,'Matrix ownership count mismatch')
            require(dict(owner.scalar_counts)==expected_profile['scalar_counts_no_cutoff'],'scalar primitive count mismatch')
            require(matrix.stream.count==expected_profile['matrix_packets'],'Matrix digest coverage mismatch')
            require(scalar.stream.count==expected_profile['scalar_total_no_cutoff'],'scalar digest coverage mismatch')
            require(result.useful_macs==expected_profile['useful_fmas'],'useful FMA count mismatch')
            report={'loan':loan,'seconds':time.monotonic()-start,'events':events,
                    'scalar':scalar.stream.report(),'matrix':matrix.stream.report(),
                    'core':(h.core_trace if loan else trace.core).report(),
                    'writes':trace.writes.report(),'accepted_matrix':counts,
                    'useful_macs':result.useful_macs,'executed_macs':result.executed_macs,
                    'scalar_checkpoints':check.count,'ddr_read_count':bus.reads.count,
                    'ddr_write_count':bus.writes.count}
            require(bus.reads.count==expected_profile['loan_ddr_reads' if loan else 'q_reads']+(0 if loan else expected_profile['kv_reads']),'DDR read count mismatch')
            require(bus.writes.count==expected_profile['output_writes'],'DDR write count mismatch')
            require(check.count==6696*tokens*(tokens+1)//2+1548*tokens,'scalar count mismatch')
            require(result.executed_macs==192*tokens*(tokens+1)//2*512,'native FMA count mismatch')
            if loan:
                for name,expected in (('ddr_requests',expected_profile['unique_kv_lines']),
                                      ('core_requests',expected_profile['kv_reads']),
                                      ('hits',expected_profile['kv_hits']),
                                      ('fills',expected_profile['unique_kv_lines']),('releases',1)):
                    require(h.supply.counts[name]==expected,'KV count mismatch: '+name)
                report['kv']={k:h.supply.counts[k] for k in ('core_requests','ddr_requests','hits','fills','releases')}
            executions.append(report)
            # Native accumulator ownership is retired before the next pass.
            del h,owner,scalar,matrix,bus,trace
        for key in ('scalar','matrix','core','writes','accepted_matrix','useful_macs','executed_macs','scalar_checkpoints','ddr_write_count'):
            require(executions[0][key]==executions[1][key],'direct/loan stream mismatch: '+key)
        reports.append({'tokens':tokens,'status':'PASS','reference_seconds':reference_seconds,
                        'reference_bytes':ref.nbytes,'work':expected_profile,'passes':executions})
    require(source_snapshot()==before and library_snapshot(os.environ)[2]==native_before,'calibration source/library drift')
    return 0,{'status':'PASS_CALIBRATION_ONLY','profiles':reports,'m128_executed':False,
              'hardware_simulation':False,'model_ticks_are_hardware_cycles':False,
              'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'source_manifest_sha256':hashlib.sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
              'native_hashes':native_before,'inputs_unchanged':True}


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibrate',action='store_true',required=True)
    parser.parse_args(argv)
    try:code,result=run_calibration()
    except Exception as error:
        code,result=1,{'status':'FAIL','reason':type(error).__name__,'m128_executed':False}
    print(json.dumps(result,sort_keys=True));return code

if __name__=='__main__':raise SystemExit(main())
