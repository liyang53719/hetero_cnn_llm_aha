"""Plan-only CLI plus uninvoked M16 reference-preparation primitive.

There is deliberately no execute CLI. A separately reviewed bounded launcher
must call produce() in an isolated origin-environment process after approval.
This primitive never starts the Public DUT, builds a library, fetches or copies
weights, or rewrites an origin receipt. Generated outputs remain non-ready.
"""
import argparse
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

if __package__:
    from . import reuse as R
else:
    import reuse as R

OUTPUT_PROFILE = 'qwen2-public-pv16-packed-m16-reference-preparation-v1'


def plan(origin_root, output):
    """No artifact access, imports of original producers or filesystem writes."""
    pins = R.contract()
    root = Path(origin_root).absolute(); out = Path(output).absolute()
    R.need('..' not in root.parts and '..' not in out.parts and
           root != out and not out.is_relative_to(root) and not root.is_relative_to(out),
           'disjoint origin and fresh output required')
    return dict(schema=1,profile=OUTPUT_PROFILE,status='PLAN_ONLY_NO_PRODUCERS_EXECUTED',
        origin=str(root),output=str(out),rows=16,past_tokens=0,token_ids=list(range(16)),
        contract_sha256=R.PINS_SHA256,readonly=pins['m16_readonly'],
        producers=['original-rms-rope-sequential-v2','original-rms-rope-qkv-block-pair-v1'],
        raw_outputs_each=R.output_inventory(),sequential_logical_shapes=R.shapes(),
        sequential_export_shapes=R.export_shapes(),
        retained_native_producer=pins['native_producer'],origin_receipts_rewritten=False,
        payload_copy=False,download=False,install=False,library_build=False,
        proposed_work_seconds=pins['execution']['proposed_work_seconds'],
        cleanup_seconds=pins['execution']['cleanup_seconds'],
        proposed_external_seconds=pins['execution']['proposed_external_seconds'],
        producer_seconds_each=pins['execution']['producer_seconds_each'],attempts=1,
        current_backend_verified=False,packed_source_profile_linked=False,
        ready_for_actual=False,**pins['claims'])


def output_root(origin, output):
    origin = R.safe_path(origin,directory=True)
    out = Path(output).absolute()
    R.need('..' not in out.parts and not out.exists() and not out.is_symlink(), 'fresh output required')
    parent = R.safe_path(out.parent,directory=True)
    out = parent / out.name
    R.need(not out.is_relative_to(origin) and not origin.is_relative_to(out), 'origin/output overlap')
    return out


@contextmanager
def deadline(seconds):
    R.need(type(seconds) is int and 1 <= seconds <= 120 and
           threading.current_thread() is threading.main_thread(), 'bounded main-thread preparation')
    R.need(hasattr(signal,'setitimer') and hasattr(signal,'pthread_sigmask') and
           signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0),
           'dedicated process without an inherited timer required')
    previous=signal.getsignal(signal.SIGALRM)
    previous_term=signal.getsignal(signal.SIGTERM)
    def expired(_signal,_frame):
        raise TimeoutError('M16 reference preparation deadline')
    def terminated(_signal,_frame):
        raise InterruptedError('M16 reference preparation terminated')
    signal.signal(signal.SIGALRM,expired)
    signal.signal(signal.SIGTERM,terminated)
    stop=time.monotonic()+seconds
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try:
        yield stop
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)
        signal.signal(signal.SIGTERM,previous_term)


def remaining(stop, ceiling):
    value=min(ceiling,stop-time.monotonic())
    if value <= 0:
        raise TimeoutError('M16 reference preparation deadline')
    return value


@contextmanager
def protected_cleanup():
    """A terminal failure gets five seconds to reap, outside the work alarm.

    Block signals while changing handlers, discard pending work/termination
    signals by ignoring them, and keep them ignored throughout the bounded reap.
    The caller always re-raises its original failure; it never resumes work.
    """
    signals={signal.SIGALRM,signal.SIGTERM,signal.SIGINT}
    old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    previous={sig:signal.getsignal(sig) for sig in signals}
    signal.setitimer(signal.ITIMER_REAL,0)
    for sig in signals:
        signal.signal(sig,signal.SIG_IGN)
    signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,signals)
        for sig,handler in previous.items():
            signal.signal(sig,handler)
        signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)


def run_original(command, directory, stop):
    """One process group, capped wait, kill and reap on every interruption."""
    timeout=remaining(stop,30)
    started=time.monotonic()
    with (directory/'stdout.log').open('xb') as stdout, (directory/'stderr.log').open('xb') as stderr:
        process=subprocess.Popen(command,cwd=directory,stdout=stdout,stderr=stderr,
                                 start_new_session=True)
        try:
            code=process.wait(timeout=timeout)
        except BaseException as original:
            cleanup_error=None
            with protected_cleanup():
                try:
                    try:
                        os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                except BaseException as error:
                    cleanup_error=error
            if cleanup_error is not None:
                original.add_note('Reference process-group cleanup did not finish within its bound.')
                raise original from cleanup_error
            raise
    R.need(code == 0,'original reference producer failed')
    R.need((directory/'stdout.log').stat().st_size <= 16384 and
           (directory/'stderr.log').stat().st_size <= 16384, 'producer log bound')
    return dict(returncode=code,elapsed_seconds=time.monotonic()-started,
                requested_timeout_seconds=timeout)


def record(root,path):
    path=R.safe_path(path)
    R.need(path.is_relative_to(root),'fresh record outside output')
    return dict(path=str(path.relative_to(root)),bytes=path.stat().st_size,sha256=R.file_hash(path))


def save(path,value):
    raw=R.encoded(value)
    R.need(len(raw) <= R.MAX_JSON,'receipt byte bound')
    temporary=path.with_name(path.name+'.pending')
    R.need(not path.exists() and not path.is_symlink() and not temporary.exists()
           and not temporary.is_symlink(),'fresh receipt destination required')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


@contextmanager
def failed_publication(output):
    """A caught failure after publication revokes this run's completion marker."""
    try:
        yield
    except BaseException:
        (output/'M16_REFERENCES.json').unlink(missing_ok=True)
        raise


def _original_modules(source):
    # Origin source imports must not reuse modules from the packed composed tree.
    allowed = 'candidates.qwen2_resident_matrix.attention_packed_m16_assets'
    for name,module in tuple(sys.modules.items()):
        if (name.startswith(('scripts.','qwen2_','heteronpu.')) or
            (name.startswith('candidates.') and not name.startswith(allowed))):
            path=getattr(module,'__file__',None)
            R.need(path is None or Path(path).resolve().is_relative_to(source),
                   'isolated origin producer process required')
    sys.dont_write_bytecode=True
    for path in (source,source/'src',source/'scripts'):
        sys.path.insert(0,str(path))
    payload=importlib.import_module('qwen2_layer0_payload')
    rms=importlib.import_module('scripts.qwen2_rms_rope_prefill_candidate')
    setup=importlib.import_module('candidates.qwen2_resident_matrix.raw_kv_public_fresh.setup')
    for module in (payload,rms,setup):
        R.need(Path(module.__file__).resolve().is_relative_to(source),'original producer import path')
    return payload,rms,setup


def produce(origin_root, output, *, work_seconds=120):
    """Future authorized-launcher primitive, not called by tests or CLI.

    Must run in a new process using the retained verified Python environment.
    Work is capped at 120 s; only two original runtime-M16 references execute.
    No success receipt is published until source/artifact/backend rechecks finish.
    This still does not yield a packed numerical-admission manifest.
    """
    pins=R.contract(); origin=R.safe_path(origin_root,directory=True)
    out=output_root(origin,output); start=time.monotonic()
    proposal_sources=R.snapshot()
    with failed_publication(out), deadline(work_seconds) as stop:
        before=R.verify_reuse(origin,metadata_only=False)
        out.mkdir(mode=0o700)
        for name in ('tmp','readonly','sequential','reduced'):
            (out/name).mkdir(mode=0o700)
        # Avoid writes to the retained environment/source through import caches.
        os.environ['PYTHONDONTWRITEBYTECODE']='1'
        os.environ['TMPDIR']=str(out/'tmp')
        os.environ['HF_HOME']=str(out/'tmp/hf')
        R.need(os.environ.get('ATEN_CPU_CAPABILITY') is None,'backend override prohibited')
        for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
            R.need(os.environ.get(name) == '4','original four-thread environment required')
        source=origin/'private/checkout'; assets=origin/'private/assets'
        payload_module,rms,setup=_original_modules(source)
        torch,identity=setup.backend_identity()
        backend=R.read_metadata(origin,'private/assets/backend.json',pins['metadata']['private/assets/backend.json'])
        R.need(R.strict_json(R.encoded(identity)) == backend['identity'],'current runtime/source/build changed')
        torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
        setup.backend_threads(torch)
        manifest=R.read_metadata(origin,'private/assets/ASSETS.json',pins['metadata']['private/assets/ASSETS.json'])
        _,payload=payload_module.load_payload(source,assets/'payload')
        layout=rms.R.make_layout();rms.G.validate_layout(layout)
        table=R.checked(assets,manifest['readonly']['table'],content=True)
        arena_identity=rms.write_arena(layout,payload,16,0,out/'readonly',table)
        del payload
        for key,name in (('arena','readonly_arena.f32le'),('input_x','input_x.f32le')):
            item=record(out,out/'readonly'/name)
            R.need({k:item[k] for k in ('bytes','sha256')} == pins['m16_readonly'][key], 'fresh M16 readonly identity')
        producers={}
        for role in ('sequential','reduced'):
            directory=out/role;rawdir=directory/'raw_stages';rawdir.mkdir()
            empty=directory/'empty_cache.bin';empty.touch(exist_ok=False)
            binary=R.checked(assets,manifest[role]['executable'],content=True)
            command=[str(binary),str(out/'readonly/readonly_arena.f32le'),'16',str(rawdir),'0',str(empty),str(empty)]
            run=run_original(command,directory,stop)
            stdout=(directory/'stdout.log').read_text()
            ack=rms.software_ack(stdout,16,run['returncode'])
            R.need({p.name for p in rawdir.iterdir()} == set(R.output_inventory()),'fresh producer output inventory')
            outputs={name:record(out,rawdir/name) for name in R.output_inventory()}
            R.need(all(item['bytes'] == R.output_inventory()[name] for name,item in outputs.items()),'fresh producer output sizes')
            actual=rms.C.load_actual(rawdir,out/'readonly/readonly_arena.f32le',out/'readonly/input_x.f32le',layout,16)
            for name in ('cache_k','cache_v'):
                R.need(actual[name].transpose(0,2,1,3).copy().tobytes() == (rawdir/(name+'.f32le')).read_bytes(),
                       'original cache/export order')
            R.need(all(rms.N.audit_semantics(actual,None,rms.G.config_for(layout),'bf16').values()),'original semantic checks')
            receipt=dict(schema=1,status='FRESH_M16_REFERENCE_ONLY',producer=manifest[role]['producer'],
                origin_compile_receipt=manifest[role]['compile'],origin_executable=manifest[role]['executable'],
                origin_receipts_rewritten=False,argv=command,software_ack=ack,outputs=outputs,
                stdout=record(out,directory/'stdout.log'),stderr=record(out,directory/'stderr.log'),
                empty_cache=record(out,empty),readonly=arena_identity,actual_chain_executed=False,**run)
            if role=='sequential':
                tensors=directory/'tensors';tensors.mkdir()
                exported=rms.C.export_actual(actual,tensors)
                R.need([item['name'] for item in exported] == sorted(R.shapes()),'sequential export inventory')
                for item in exported:
                    R.need(item['shape'] == R.shapes()[item['name']] and
                           item['export_shape'] == R.export_shapes()[item['name']], 'sequential export shape')
                save(directory/'export.json',exported)
                receipt['export_receipt']=record(out,directory/'export.json')
                receipt['tensors']={name:record(out,tensors/('candidate_'+name+'.f32le')) for name in R.shapes()}
            del actual
            save(directory/'run.json',receipt)
            producers[role]=dict(run=record(out,directory/'run.json'),**receipt)
        setup.backend_threads(torch)
        _,after_identity=setup.backend_identity()
        R.need(R.strict_json(R.encoded(after_identity)) == backend['identity'],'backend changed during preparation')
        R.need(R.verify_reuse(origin,metadata_only=False) == before,'origin changed during preparation')
        readonly={key:record(out,out/'readonly'/name) for key,name in
                  (('arena','readonly_arena.f32le'),('input_x','input_x.f32le'))}
        fresh_records=list(R.records(readonly))
        for producer in producers.values():
            fresh_records.extend(R.records({key:producer[key] for key in
                ('run','outputs','stdout','stderr','empty_cache','export_receipt','tensors') if key in producer}))
        R.no_aliases([R.below(out,item['path']) for item in fresh_records])
        for item in fresh_records:
            R.checked(out,item,content=True)
        R.need(R.snapshot() == proposal_sources,'preparation proposal source drift')
        remaining(stop,1)
        result=dict(schema=1,profile=OUTPUT_PROFILE,status='REFERENCE_PREPARATION_ONLY_NOT_NUMERICALLY_ADMITTED',
            rows=16,past_tokens=0,contract_sha256=R.PINS_SHA256,
            preparation_source_sha256=proposal_sources,origin=before,readonly=readonly,
            origin_table=manifest['readonly']['table'],origin_native_m16=manifest['native_m16'],
            producers=producers,current_backend_verified=True,packed_source_profile_linked=False,
            ready_for_actual=False,elapsed_seconds=time.monotonic()-start,**pins['claims'])
        save(out/'M16_REFERENCES.json',result)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Preparation proposal only; never executes producers.')
    parser.add_argument('--origin',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--check-metadata',action='store_true',help='Read source/JSON and stat artifact sizes; never open payload/ELF bytes.')
    args=parser.parse_args(argv)
    result=plan(args.origin,args.output)
    if args.check_metadata:
        result['origin_metadata']=R.verify_reuse(args.origin,metadata_only=True)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__ == '__main__':
    main()
