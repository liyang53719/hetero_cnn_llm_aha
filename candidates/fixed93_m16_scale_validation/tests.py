"""Small pure-stdlib source/authority controls. Never starts either actual arm."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import time
import types

HERE=Path(__file__).resolve().parent


def need(ok,msg):
    if not ok: raise AssertionError(msg)


def load(name):
    path=HERE/(('parent/' if name=='seal_check' else '')+name+'.py');raw=path.read_bytes()
    module=types.ModuleType(name);module.__file__=str(path);module.__package__=''
    need(name not in sys.modules,'fresh test module')
    sys.modules[name]=module
    exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),vars(module))
    return module


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);args=p.parse_args()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20));resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    start=time.monotonic();denied=[]
    def audit(event,args):
        if event.startswith(('socket.','ctypes.')) or event in ('subprocess.Popen','os.system','os.exec','os.spawn'):
            denied.append(event);raise RuntimeError('pure cold denies '+event)
        if event=='import' and args[0].split('.')[0] in ('numpy','torch','yaml','candidates','integration','observation'):
            denied.append(event+':'+args[0]);raise RuntimeError('DUT/package import denied')
    sys.addaudithook(audit)
    base=Path(args.base);cases=[]
    def ok(name,function):function();cases.append(name)
    def reject(function):
        try:function()
        except (ValueError,FileNotFoundError,OSError):return
        raise AssertionError('expected rejection')
    a=load('m2_authority')
    ok('strict JSON duplicate rejection',lambda:reject(lambda:a.parse(b'{"a":1,"a":2}')))
    ok('strict JSON nonfinite rejection',lambda:reject(lambda:a.parse(b'{"a":NaN}')))
    with tempfile.TemporaryDirectory(prefix='m2_source_cold_') as d:
        root=Path(d);f=root/'a';f.write_bytes(b'abc')
        pin=dict(bytes=3,sha256=hashlib.sha256(b'abc').hexdigest())
        ok('same-FD bounded source read',lambda:need(a.checked(f,pin)==b'abc','read'))
        ok('wrong source digest rejected',lambda:reject(lambda:a.checked(f,dict(pin,sha256='0'*64))))
        ok('read-before-cap refusal',lambda:reject(lambda:a.checked(f,pin,cap=2)))
        link=root/'link';link.symlink_to(f)
        ok('source symlink rejection',lambda:reject(lambda:a.checked(link,pin)))
        hard=root/'hard';os.link(f,hard)
        ok('source hardlink rejection',lambda:reject(lambda:a.checked(f,pin)))
    original_process=a.process
    a.process=lambda pid:dict(pid=pid,start_ticks=17)
    a._STATE=dict(pid=os.getpid(),parent=a.process(os.getppid()),arm='new',lease={'work_stop':time.monotonic()+30})
    def reset():a._PURPOSES.clear()
    ok('unrelated/fullblock authority purpose rejected',lambda:reject(lambda:a.require_actual_runtime('wholeblock_runtime')))
    ok('native before initialization rejected',lambda:reject(lambda:a.require_actual_runtime('existing_profile2_elf_load')))
    def valid_sequence():
        for x in ('initialize_m2_runtime','existing_profile2_elf_load','construct_m2_observers','success_m2_new'):
            need(a.require_actual_runtime(x) is a._STATE,'state')
    ok('exact four-stage order only',valid_sequence)
    ok('repeated arm rejected',lambda:reject(lambda:a.require_actual_runtime('success_m2_new')))
    reset();a._STATE['lease']['work_stop']=time.monotonic()-1
    ok('expired shared work deadline rejects before native',lambda:reject(lambda:a.require_actual_runtime('initialize_m2_runtime')))
    a.process=original_process;a._STATE=None;reset()
    io=load('m2_io');g=object.__new__(io.CalibrationIO)
    g.out=Path('/synthetic/new/old');g.allowed={'/synthetic/pinned.py':{}};g.allowed_proc=set();g.reads=set()
    ok('unknown external read rejected',lambda:reject(lambda:g.audit('open',('/synthetic/input.u32','r',0))))
    ok('pinned source write rejected',lambda:reject(lambda:g.audit('open',('/synthetic/pinned.py','w',os.O_WRONLY))))
    ok('relative write rejected',lambda:reject(lambda:g.audit('open',('file','w',os.O_WRONLY))))
    ok('own arm output admitted',lambda:g.audit('open',('/synthetic/new/old/result.json','w',os.O_WRONLY)))
    ok('sibling arm write rejected',lambda:reject(lambda:g.audit('open',('/synthetic/new/new/result.json','w',os.O_WRONLY))))
    def real_cleanup_route():
        # Actual stdlib cleanup with omitted audit dir_fd, synthetic new files only.
        with tempfile.TemporaryDirectory(prefix='m2_cleanup_cold_') as temporary:
            root=Path(temporary);g.out=root;g.allowed_proc=set()
            g.expected_cleanup=shutil._rmtree_safe_fd.__code__
            g.shutil_path=Path(shutil.__file__).resolve()
            raw=g.shutil_path.read_bytes();g.shutil_pin=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            g.allowed[str(g.shutil_path)]=g.shutil_pin;g.cleanup_directory_reads=[]
            sys.addaudithook(g.audit)
            parent=root/'metadata';(parent/'fp32').mkdir(parents=True)
            (parent/'fp32'/'small').write_bytes(b'synthetic')
            shutil.rmtree(parent)
            need(not parent.exists() and len(g.cleanup_directory_reads)==1,'real nested cleanup route')
    # Importing these complete inert new modules must not import any DUT/native.
    for name in ('m2_runtime','m2_context','success_driver','seal_check'):
        ok('inert source module '+name,lambda n=name:load(n))
    old=ast.parse((base/'native_reuse.py').read_bytes());new=ast.parse((HERE/'native_adapter.py').read_bytes())
    def defs(tree):return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    od,nd=defs(old),defs(new)
    need(od.keys()==nd.keys(),'same adapter functions')
    # load() loses only the old inner admission import, all arithmetic/provenance
    # helpers stay original. The bridge declares its own authority and base.
    for name in od.keys()-{'load'}:need(od[name]==nd[name],'native helper drift '+name)
    nl=next(x for x in new.body if isinstance(x,ast.FunctionDef) and x.name=='load')
    ol=next(x for x in old.body if isinstance(x,ast.FunctionDef) and x.name=='load')
    ol.body=[x for x in ol.body if not (isinstance(x,ast.ImportFrom) and x.module=='admission')]
    ok('native adapter helper and load body retained',lambda:need(ast.dump(ol)==ast.dump(nl),'load delta'))
    gate=load('m2_supervision_gate')
    budget=json.loads((HERE/'BUDGET.json').read_bytes())
    ok('exact shared budget validated',lambda:need(gate.validate_budget(budget)==budget,'budget'))
    for key,value in [('outer_wall_seconds',601),('inner_wall_seconds',571),('sample_rows',121),
                      ('cpu_count',True),('output_bytes',321<<20),('actual_execution_authorized',True)]:
        ok('reject budget drift '+key,lambda k=key,v=value:reject(lambda:gate.validate_budget(dict(budget,**{k:v}))))
    ok('601 sampler rows coupled to 600 seconds',lambda:need(gate.fixed_limits(budget)['sample_rows']==601,'rows'))
    with tempfile.TemporaryDirectory(prefix='m2_used_namespace_') as temporary:
        prior=gate.HERE;gate.HERE=Path(temporary)
        out=gate.HERE/'work'/'case';out.mkdir(parents=True)
        (out/'ADMISSION.json').write_bytes(b'SYNTHETIC PLACEHOLDER; NOT AUTHORITY')
        (out/'USED').write_bytes(b'previous evidence')
        try:
            ok('used output refuses before authority payload read',lambda:reject(lambda:
                gate.admission({'base':{'path':str(base)}},out,out/'ADMISSION.json','0'*64,'0'*64,{})))
        finally:gate.HERE=prior
    baseline=json.loads((base/'SOURCE_MANIFEST.json').read_bytes())
    decoded=gate.decoder_arguments(base,baseline,budget)
    ok('real pinned decoder dependency loading without DUT',lambda:need(
       set(decoded)=={'Decoder','Limits','decode_exp','TokenDecoder','OperandDecoder','attention_limits','whole_limits'},'decoder API'))
    own=a.parse((HERE/'SOURCE_MANIFEST.json').read_bytes())
    ok('exact source-attested frame-routing policy',lambda:need(a.frame_routing_policy(own)['sampling_enabled'] is False,'no sampler'))
    bad=dict(own,files=dict(own['files']))
    bad['files']['cached_wholeblock.py']=dict(bad['files']['cached_wholeblock.py'],sha256='0'*64)
    ok('mixed observer/frame-routing pin rejected',lambda:reject(lambda:a.frame_routing_policy(bad)))
    # Exercise the actual policy predicate with isolated synthetic JSON mutations;
    # source-pinned loader and positive real file read above remain unmodified.
    policy=a.frame_routing_policy(own);original_checked=a.checked
    for key,value in (('policy_id','callback-local-frame-code-cache-v1'),
                      ('schema','fixed93-callback-local-frame-code-cache-v1'),
                      ('policy_id','tick-boundary-metadata-integrity-v1'),
                      ('underlying_tick_policy','other'),('nonhook_line_sampling_changed',False),
                      ('transient_locals_detection_equivalent',True),('shared_dispatcher_unchanged',True),
                      ('evidence_hook_counts',{'_attention':5,'_matrix_step':4,'tick':3,'_write':True}),
                      ('evidence_hook_counts',{'_attention':5,'_matrix_step':3,'tick':3,'_write':2}),
                      ('sampling_enabled',True),('full_identity_frequency_changed',False),
                      ('event_schema_changed',True),('underlying_integrity_policy','other'),
                      ('transient_metadata_detection_equivalent',True),('scope_must_close',False),
                      ('max_tick_ancestry_frames',True),('max_tick_ancestry_frames',129),
                      ('original_full_identity_unchanged',False),
                      ('underlying_event_line_policy','other'),
                      ('frame_segment_expires_on_return',False),('generator_resume_rebinds',False),
                      ('exception_resume_line_delivered',False),('registry_identity_checked',False),
                      ('exact_two_listener_routes',False),('extra_listener_fallback',False),
                      ('no_frame_retention',False),('skipped_line_thread_owner_ancestry_sampling_changed',False),
                      ('all_control_events_preserved',False),('transient_frame_ownership_detection_equivalent',True)):
        malformed=dict(policy,**{key:value})
        a.checked=lambda *x,raw=json.dumps(malformed).encode(),**kw:raw
        try:ok('reject policy drift '+key+':'+str(value),lambda:reject(lambda:a.frame_routing_policy(own)))
        finally:a.checked=original_checked
    for key in ('policy_id','scope_must_close','original_full_identity_unchanged','evidence_hook_counts','underlying_tick_policy','frame_segment_expires_on_return','registry_identity_checked'):
        malformed=dict(policy);del malformed[key]
        a.checked=lambda *x,raw=json.dumps(malformed).encode(),**kw:raw
        try:ok('reject missing policy field '+key,lambda:reject(lambda:a.frame_routing_policy(own)))
        finally:a.checked=original_checked
    ok('manifest-policy identity mismatch rejected',lambda:reject(lambda:a.frame_routing_policy(dict(own,policy_id='op-evidence-boundary-v1'))))
    ok('old arm rejected before filesystem/authority',lambda:reject(lambda:a.admit(
        arm='old',base='',out='',admission='',admission_sha='',manifest_sha='')))
    package=types.ModuleType('capture');package.__path__=[];package.__package__='capture'
    need('capture' not in sys.modules,'fresh actual wholeblock source package')
    sys.modules['capture']=package
    F=a.load_source(base/'fullblock_runtime.py','_cold_actual_factory',baseline['preparation_files']['fullblock_runtime.py'])
    module,verify=sys.modules['m2_runtime'].whole_observer({'own':own,'source_manifest':baseline},F)
    ok('real raw overlay loader and sibling metadata without constructor',lambda:need(
        module.__name__=='capture.cached_wholeblock' and len(verify())==3,'new source module actually loaded'))
    for name in ('_dispatch','_dispatch_code','_route_frame','bind_owner_line_routes','register','unregister'):
        method=vars(module.TraceDispatcher)[name];original=method.__code__
        method.__code__=(lambda *a:None).__code__
        try:ok('changed dispatcher code rejected '+name,lambda:reject(verify))
        finally:method.__code__=original
    original_path=module.__file__;module.__file__=str(base/'capture/wholeblock.py')
    try:ok('old wholeblock alias rejected',lambda:reject(verify))
    finally:module.__file__=original_path
    ok('exact restored overlay accepted',lambda:need(len(verify())==3,'restored exact source'))
    # Source invariants cover the untouched F / native / owner and loop paths.
    oldbase=Path(own['predecessor']['path'])
    for name in ('m2_io.py','native_adapter.py','cached_wholeblock.py','narrow_fullblock_attention.py','m2_runtime.py'):
        ok('byte-identical successful baseline '+name,lambda n=name:need(
            (HERE/n).read_bytes()==(oldbase/n).read_bytes(),'old proven code changed'))
    driver=sys.modules['success_driver']
    fixture=driver.fixture()
    ok('exact fixed M16 synthetic input shapes',lambda:need(
       {k:len(v) for k,v in fixture.items()}=={0x100000:24576,0x200000:4096,0x300000:4096},'Q/K/V word counts'))
    ok('literal M16 synthetic KV token/head indexing',lambda:need(
       fixture[0x300000][2*128]==(0x3f000000+((13+5)%96)*0x10000|0x8000|0x80000000), 'token1/kv0/col0 pattern'))
    for addr,words in fixture.items():
        ok('M16 accepted first beat '+str(addr),lambda a=addr,w=words:need(driver.read_fixture(fixture,a)==w[:16],'first beat'))
        ok('M16 accepted final beat '+str(addr),lambda a=addr,w=words:need(driver.read_fixture(fixture,a+len(w)*4-64)==w[-16:],'last beat'))
        ok('M16 outside input end rejected '+str(addr),lambda a=addr,w=words:reject(lambda:driver.read_fixture(fixture,a+len(w)*4)))
    need('HISTORY.json' not in str(own) and set(own['parent_files'])=={'parent/seal_check.py'}, 'no historical M2 data binding')
    ok('M16 budget field shape cannot fallback M2',lambda:reject(lambda:gate.validate_budget(
        dict(budget,attention_trace_limits=dict(budget['attention_trace_limits'],max_m=2)))))
    ok('M16 codec cap cannot expand',lambda:reject(lambda:gate.validate_budget(
        dict(budget,attention_trace_limits=dict(budget['attention_trace_limits'],codec_limits=dict(
        budget['attention_trace_limits']['codec_limits'],max_records=300001))))))
    checker=sys.modules['seal_check']
    with tempfile.TemporaryDirectory(prefix='m16_seal_negative_') as td:
        root=Path(td)
        (root/'M16_CASE.json').write_text('{"status":"STARTED"}')
        ok('unsealed M16 result rejects before stream access',lambda:reject(lambda:checker.check_m16(root,**decoded)))
    # Tiny original r3 writer/decoder fixtures exercise the new same-FD wrapper,
    # not model execution or a fabricated complete M16 stream.
    import io as bytes_io
    codec_root=Path(budget['attention_trace_limits']['codec_root'])
    raw=(codec_root/'writer.py').read_bytes()
    codec_pin=json.loads((base/'capture/CODEC_PINS.json').read_bytes())['writer.py']
    need(hashlib.sha256(raw).hexdigest()==codec_pin,'original writer pin')
    wm=types.ModuleType('_m16_cold_writer');wm.__file__=str(codec_root/'writer.py')
    exec(compile(raw,wm.__file__,'exec',dont_inherit=True,optimize=0),vars(wm))
    limits=decoded['Limits'](**budget['attention_trace_limits']['codec_limits'])
    buf=bytes_io.BytesIO();w=wm.Writer(buf,limits,byte_order='little');w.event(b'',{'tiny':True});seal=w.finish()
    encoded=buf.getvalue()
    with tempfile.TemporaryDirectory(prefix='m16_stream_wrapper_') as td:
        root=Path(td);(root/'small.lec1').write_bytes(encoded)
        def decode_small():
            with checker._owned(root,'small.lec1',len(encoded)+1) as reader:
                d=decoded['Decoder'](reader,limits);items=list(d.records())
                need(len(items)==1 and items[0].data==b'' and d.seal==seal,'zero payload / real EOF')
                return reader.identity()
        ok('original r3 zero-payload and same-FD EOF',decode_small)
        (root/'small.lec1').write_bytes(encoded+b'x')
        ok('r3 trailing byte rejected',lambda:reject(decode_small))
        (root/'small.lec1').write_bytes(encoded[:-1])
        ok('r3 truncated FINISH rejected',lambda:reject(decode_small))
    ok('exact M16 address schedule inventory',lambda:need(
        len(list(checker._schedule()))==29184 and sum(int(w) for w,a in checker._schedule())==1536,'fixed address counts'))
    from math import prod
    ok('exact M16 field raw/presence reservation',lambda:need(
        sum(prod(shape)*5 for shape in checker.FIELD_SHAPES.values())==3305280,'fields'))
    need('main_loop_profiler' not in sys.modules,'no sampling module')
    # Last filesystem case: direct installed callback preserves the exact audit
    # stack expected by production. No forwarding hook is substituted.
    ok('actual pinned shutil cleanup inside new output only',real_cleanup_route)
    need(not denied,'no forbidden attempts')
    need(not any(k.split('.')[0] in ('numpy','torch','candidates','integration','observation','ctypes') for k in sys.modules),
         'pure source test unexpectedly loaded runtime')
    result=dict(status='PASS_LIMITED_M16_SOURCE_CONTROLS_ONLY',cases=cases,case_count=len(cases),
                wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                native_executed=False,DUT_executed=False,actual_M16_executed=False,denied_attempts=denied,
                omitted='No actual constructor, native load, owner loop, full protocol/fault matrix, or pair numerical comparison')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
