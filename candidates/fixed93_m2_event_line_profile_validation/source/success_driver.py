"""SOURCE ONLY: one actual success-M2 case after independent root admission.

No CLI, runtime imports, CDLL, compiler, subprocess, oracle or admission creation.
Caller supplies a newly constructed exact owner and original, already bound
WholeblockObservation. This helper cannot grant execution authority. Never call
0936 run_owner_cases, startup_probe.run, a public advance, or wholeblock.seal.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
from loop_sampler import LoopSampler
from sampling_report import classify

QBASE, KBASE, VBASE, OBASE = 0x100000, 0x200000, 0x300000, 0x400000
_USED = set()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def timed(timings, name, function):
    wall, cpu = time.monotonic(), time.process_time()
    try:
        return function()
    finally:
        timings[name] = dict(wall_seconds=time.monotonic()-wall,
                             cpu_seconds=time.process_time()-cpu)


def identity(path):
    p = Path(path)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for raw in iter(lambda: f.read(65536), b''):
            h.update(raw)
    return dict(bytes=p.stat().st_size, sha256=h.hexdigest())


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()
    need(len(raw) <= 4*1024*1024, 'small report byte cap')
    with Path(path).open('xb') as f:
        f.write(raw)


def fixture():
    """Literal N1 input recipe; generated before observation, never from outputs."""
    qp = (0x3e818001, 0xbe418000, 0x3f018001, 0x3f218000,
          0xbdc18000, 0x3ec18001, 0x3e018000)
    kp = (0x3f418001, 0x3ec18000, 0xbe018001, 0x3e818000, 0xbf018000)
    q = tuple(qp[(i*3+i//128+1) % len(qp)] for i in range(3072))
    key = tuple(kp[(i*2+i//128+1) % len(kp)] for i in range(256))
    v = []
    for token in range(2):
        for kv in range(2):
            for col in range(128):
                word = 0x3f000000 + ((token*13+kv*7+col*3+5) % 96)*0x10000
                word |= 0x8000 if col % 3 == 0 else 0x8001 if col % 3 == 1 else 1
                if col % 5 == 0:
                    word |= 0x80000000
                v.append(word)
    return {QBASE:q, KBASE:key*2, VBASE:tuple(v)}


def read_fixture(inputs, address):
    for base, words in inputs.items():
        if base <= address and address+64 <= base+4*len(words):
            need((address-base) % 64 == 0, 'unaligned synthetic input request')
            i = (address-base)//4
            return words[i:i+16]
    raise ValueError('read outside predeclared synthetic Q/K/V')


def run_loop(owner, job, Response, inputs, deadline):
    """Only original owner.tick plus actual MemoryResponse handshakes.

    Fixed success branch of 0936 _drive. No expected_case graph and no fault
    injection. Read data is only the predeclared Q/K/V fixture. Every accepted
    write is persisted, never replaced by a reference value.
    """
    pending = None
    reads = writes = acks = held_ack = held_terminal = 0
    transactions, controls, output = [], [], bytearray(job.write_bytes)
    written = set()
    scalar_before = dict(owner.scalar.calls)
    matrix_before = dict(owner.matrix.counts)
    edge = owner.tick(job=job)
    need(edge['job_fire'], 'declared M2 job was not accepted')
    for tick in range(60000):
        need(time.monotonic() < deadline, 'total calibration deadline exhausted')
        response = None
        last = pending is not None and pending.write and pending.address == OBASE+job.write_bytes-64
        if pending is not None:
            if last and held_ack < 4:
                held_ack += 1
                need(owner.result is None and owner.ack_bytes < job.write_bytes, 'premature terminal before ACK')
                controls.append(dict(kind='last_ack_held', tick=tick, tag=pending.tag))
            else:
                response = Response(pending.tag, None if pending.write else read_fixture(inputs, pending.address))
        ready = True
        if owner.result is not None and held_terminal < 4:
            held_terminal += 1
            ready = False
            need(owner.matrix.owner is owner, 'Matrix release before owner terminal handshake')
            controls.append(dict(kind='owner_response_held', tick=tick, tag=owner.result.tag,
                                 status=owner.result.status))
        edge = owner.tick(memory_ready=tick%5 != 0, memory_response=response, response_ready=ready,
                          matrix_request_ready=tick%7 != 0, matrix_result_ready=tick%11 != 0,
                          service_result_ready=tick%13 != 0, service_done_ready=tick%17 != 0)
        if edge['memory_response_fire']:
            need(pending is not None and response is not None and response.tag == pending.tag,
                 'matched response without pending request')
            if pending.write:
                acks += 1
            pending = None
        if edge['memory_fire']:
            need(pending is None and len(transactions) < 960, 'overlapping/excess accepted requests')
            pending = edge['memory']
            need(pending.tag == ((job.tag >> 16) << 32) | len(transactions), 'memory serial tag mismatch')
            row = dict(index=len(transactions), tick=tick, tag=pending.tag,
                       address=pending.address, write=pending.write, mask=pending.mask)
            if pending.write:
                need(pending.mask == (1<<64)-1 and type(pending.data) is bytes and len(pending.data) == 64,
                     'accepted write packet fields')
                off = pending.address-OBASE
                need(0 <= off <= job.write_bytes-64 and off%64 == 0 and off not in written,
                     'output extent/alignment/duplicate write')
                output[off:off+64] = pending.data
                row['data_hex'] = pending.data.hex()
                written.add(off)
                writes += 1
            else:
                need(pending.mask == 0 and pending.data is None, 'read packet fields')
                row['response_words'] = read_fixture(inputs, pending.address)
                reads += 1
            transactions.append(row)
        if edge['response_fire']:
            result = edge['response']
            need(result.status is None and result.tag == job.tag, 'M2 success terminal required')
            need(pending is None and not owner.memory_pending and owner.state == 'idle' and not owner.poison,
                 'terminal debt or poisoned owner')
            need(owner.matrix.owner is None and owner.scalar.client is None, 'terminal service lease debt')
            need((reads,writes,acks,held_ack,held_terminal) == (768,192,192,4,4),
                 'successful M2 transport coverage differs')
            need(result.write_bytes == job.write_bytes == len(output) == 12288 and
                 written == set(range(0,12288,64)), 'complete accepted M2 output coverage')
            def delta(after,before):
                return {k:after.get(k,0)-before.get(k,0) for k in sorted(set(after)|set(before))}
            return dict(terminal=asdict(result), ticks=tick+1, reads=reads,writes=writes,write_acks=acks,
                        matrix_counts=delta(dict(owner.matrix.counts),matrix_before),
                        scalar_counts=delta(dict(owner.scalar.calls),scalar_before), owner_counts=dict(owner.counts),
                        controls=controls, transactions=transactions), bytes(output)
    raise ValueError('bounded M2 driver tick limit')


def idle_fence(whole, owner):
    whole.check()
    x, p, s = whole.objects['x'], whole.objects['physical'], whole.objects['silu']
    need(x.attention_owner is owner and x.matrix_service is owner.matrix and x.prefix_owner.scalar is owner.scalar,
         'detached owner/wholeblock identity')
    need(x.host.pc == x.host.completed == x.host.jobs == 0 and not x.completions and x.launch_result is None,
         'public21 execution was not requested')
    need(not dict(p.counts) and p.pending is None and s.calls == 0 and
         whole._silu_calls == whole._silu_returns == 0 and whole._silu_active is None,
         'physical/public/SiLU work outside success-M2 scope')
    need(owner.state == x.owner.state == x.prefix_owner.state == 'idle' and not owner.memory_pending and
         owner.matrix.owner is None and owner.scalar.client is None and not owner.poison,
         'M2 terminal debt/lease fence')
    need(not whole._exceptions and not whole._dense_payloads and whole._semantic_operands is None,
         'open wholeblock trace frame/payload')
    return dict(public_pc=0, public_completed=0,public_jobs=0,physical_counts=dict(p.counts),silu_calls=s.calls,
                m128_numeric_executed=False, public_advance_calls=0, fullblock_complete=False)


def finite_scope_seal(whole, owner):
    """Finish the real codec, NOT WholeblockObservation.seal or a fullblock seal."""
    fence = idle_fence(whole,owner)
    need(not whole.trace_dispatcher.active and not whole._sealed and not whole._closed,
         'finite codec finish must follow real dispatcher stop')
    for path,digest in whole.sources.items():
        need(identity(path)['sha256'] == digest, 'terminal source drift: '+path)
    for path,digest in whole.admission['codec']['source_sha256'].items():
        need(identity(path)['sha256'] == digest, 'terminal codec drift: '+path)
    sealed = whole.writer.finish()
    whole.sink.flush()
    whole.close()
    return dict(status='SEALED_ACTUAL_M2_SUBCHAIN_ONLY',scope='INCOMPLETE_WHOLEBLOCK',
                codec_seal=asdict(sealed), artifact=identity(whole.path),
                counts=dict(whole.counts),fence=fence,fullblock_seal_called=False,
                terminal_sources_rehashed=len(whole.sources),terminal_codec_files_rehashed=3,
                complete_declared_schedule=False,complete_declared_cache=False)


def run_one(*, variant, Capture, whole, owner, Job, Response, source_root, source_manifest,
            trace_limits, out, deadline, root_guard):
    """One case only; root_guard is root-owned current live authority, not a bool.

    Root initializes/loads/binds a fresh exact original WholeblockObservation and
    owner before entry, measures that separately, enforces outer resource limits,
    and supplies a finite absolute total deadline. The helper never loads native.
    """
    need(variant in ('old','new') and variant not in _USED and len(_USED)<2, 'one execution per variant')
    root_guard('success_m2_'+variant)
    _USED.add(variant)
    need(trace_limits['max_m'] == 2 and deadline > time.monotonic(), 'explicit M2 deadline/limits required')
    need(whole.objects['x'].attention_owner is owner and whole._bound and not whole._closed,
         'fresh real bound wholeblock context required')
    out = Path(out)
    need(out.is_dir() and not out.is_symlink(), 'root creates fresh bounded output directory')
    inputs, timings = fixture(), {}
    input_identity = {hex(k):identity_bytes(struct.pack('<%dI'%len(v),*v)) for k,v in inputs.items()}
    job = Job('Attention',0x1000a,QBASE,KBASE,OBASE,2,1536,128,12288,c=VBASE)
    capture = timed(timings,'attention_constructor',lambda:Capture(owner,source_root,source_manifest,
        out/'attention',trace_limits=trace_limits,trace_dispatcher=whole.trace_dispatcher))
    whole_entered = attention_entered = False
    try:
        timed(timings,'wholeblock_enter',whole.__enter__); whole_entered = True
        timed(timings,'attention_enter_and_source_io',capture.__enter__); attention_entered = True
        sampler = LoopSampler()
        sampler.start()
        try:
            result, raw = timed(timings,'main_loop',lambda:run_loop(owner,job,Response,inputs,deadline))
        finally:
            sampler.stop()
        sampling = sampler.report()
        sampling['diagnostic_quality'] = classify(sampling)
        sampling['main_evidence_qualification_independent'] = True
        save(out/'MAIN_LOOP_PROFILE.json', sampling)
        sampling = {k:v for k,v in sampling.items() if k not in ('code_table','stacks','leaf_counts','inclusive_counts')}
        sampling['artifact'] = identity(out/'MAIN_LOOP_PROFILE.json')
        save(out/'SAMPLING_SUMMARY.json', sampling)
        whole.check()
        attention_entered = False
        timed(timings,'attention_exit_source_io_and_codec_seal',lambda:capture.__exit__(None,None,None))
        whole_entered = False
        timed(timings,'wholeblock_exit',lambda:whole.__exit__(None,None,None))
        attention = timed(timings,'attention_report_and_field_export',lambda:capture.save(out/'attention'))
        need(attention['complete_observation'] is True,'M2 attention observation incomplete')
        seal = timed(timings,'wholeblock_finite_codec_seal',lambda:finite_scope_seal(whole,owner))
        with (out/'actual_output.u32le').open('xb') as f:
            f.write(raw)
        save(out/'actual_transport.json',result)
        report = dict(status='ACTUAL_SUCCESS_M2_CAPTURED_PENDING_PAIR_COMPARISON',scope='INCOMPLETE_WHOLEBLOCK',
            variant=variant,inputs=input_identity,input_provenance='PREDECLARED_N1_SYNTHETIC_NOT_REFERENCE',
            m=2,wholeblock=seal,attention_complete=True,timings=timings,
            output=identity(out/'actual_output.u32le'), fullblock_pass=False,M128_execution=False,
            numerical_acceptance=False,hardware_cycles=None,initialization_timing_authority='root separately measures',
            loop_includes='real owner + both real callbacks + codec + transport checks; no constructor or seal IO',
            observer_identity=identity(Path(sys.modules[Capture.__module__].__file__)))
        save(out/'M2_CASE.json',report)
        return report
    finally:
        exc = sys.exc_info()
        if attention_entered:
            capture.__exit__(*exc)
        if whole_entered:
            whole.__exit__(*exc)
        whole.close()


def identity_bytes(raw):
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
