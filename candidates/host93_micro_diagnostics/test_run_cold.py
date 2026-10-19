#!/usr/bin/env python3
"""Cold-only tests. No network, HDL, C++, build, or native tool execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before test project loads')
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import types
import unittest

HERE=Path(__file__).absolute().parent
RUN_BYTES=53278
RUN_SHA='235a619fc7d304578ff78a958c173a33cb50d1a860dbf56fe2051fd4396ba3b8'

def load():
    raw=(HERE/'run.py').read_bytes()
    if len(raw)!=RUN_BYTES or hashlib.sha256(raw).hexdigest()!=RUN_SHA:
        raise ValueError('cold loader fixed same-buffer source identity')
    m=types.ModuleType('verified_micro_runner_cold');m.__file__=str(HERE/'run.py')
    exec(compile(raw,m.__file__,'exec',dont_inherit=True),m.__dict__)
    return m

m=load()

def observation(ok=True):
    return {'exit_code':0 if ok else 1,'final_reap_signal':None,'receipt_timed_out':False,'cleanup_confirmed':True,'waitid_code':1,'waitid_status':0 if ok else 1,'kill_attempted':True,'kill_result':'SIGNAL_SENT_BEFORE_REAP','native_record_status':'PASS' if ok else 'FAIL','failure_code':'NONE' if ok else 'CHILD_EXIT_NONZERO','failure_boundary':'NONE' if ok else 'NATIVE_SUPERVISION','child_user_cpu_seconds':0.01,'child_system_cpu_seconds':0.01,'child_maxrss_kib_cumulative':1024}

OPAQUE=(b'%Warning-UNOPTFLAT: /private/host_handshake_micro.sv:16:21: Signal unoptimizable\n'
 b'  /private/host_handshake_micro.sv:16:21:      Example path: host_handshake_micro.cmd_valid\n'
 b'  /private/leaf_opaque_model.sv:30:3:      Example path: ALWAYS\n'
 b'%Error: Exiting due to 1 warning(s)\n')
FIFO=('\n'.join(sorted(m.FIFO_LINES))+'\n'+m.FIFO_PASS+'\n').encode()

@contextlib.contextmanager
def patched(**changes):
    old={name:getattr(m,name) for name in changes}
    for name,value in changes.items(): setattr(m,name,value)
    try: yield
    finally:
        for name,value in old.items(): setattr(m,name,value)

class MockRun:
    def __init__(self,fail=None,opaque=OPAQUE,timeout=False,wrong_budget=False,transparent=b'',parent_fail=None,parent_error=None):
        self.parent_fail,self.parent_error=parent_fail,parent_error
        self.fail,self.opaque,self.timeout=fail,opaque,timeout
        self.wrong_budget,self.transparent=wrong_budget,transparent
        self.calls=[];self.deadlines=[];self.argv={};self.tool_calls=0
    def run(self,repo,out):
        self.out=out
        original_contract=m.contract_check
        @contextlib.contextmanager
        def injected_contract(boundary):
            with original_contract(boundary):
                if boundary==self.parent_fail:
                    raise self.parent_error if self.parent_error is not None else ValueError('CANARY /private/credential?secret=never_export')
                yield
        def ident(p,cap):
            raw=Path(p).read_bytes()
            return {'bytes':len(raw),'sha256':m.sha(raw),'mode':oct(Path(p).stat().st_mode&0o777)}
        base=types.SimpleNamespace(identity=ident,tree_inventory=lambda *a,**k:{},checked_read=lambda p,n,h:m.exact(Path(p),{'bytes':n,'sha256':h}))
        def supervised(support,plan,name,argv,cwd,evidence,environment,bound,stop,owner,diagnostics):
            self.calls.append(name);self.deadlines.append((stop,owner['deadline']));self.argv[name]=argv
            if signal.getsignal(signal.SIGALRM) is not owner['handler'] or signal.getitimer(signal.ITIMER_REAL)[0]<=0: raise AssertionError('same owned alarm')
            evidence.mkdir(mode=0o700)
            raw=self.opaque if name=='host_opaque' else FIFO if name=='fifo_run' else self.transparent if name=='host_transparent' else b''
            if name=='fifo_run':raw+=(str(out/'fixtures/fifo_valid_split_cases.sv')+':229: $finish called at 1296000 (1ps)\n').encode()
            (evidence/'native.log').write_bytes(raw)
            ok=name!='host_opaque' and name!=self.fail
            diagnostics.update(observation(ok))
            if name==self.fail and self.timeout:
                diagnostics.update(exit_code=-9,final_reap_signal=9,waitid_code=2,waitid_status=9,receipt_timed_out=True,failure_code='SUPERVISOR_TIMEOUT_CLASSIFICATION')
            if not ok:
                if self.timeout and name==self.fail: raise TimeoutError('mock timeout')
                raise ValueError('mock failed native stage')
            if name=='icarus_acquire':
                stage=out/'icarus';(stage/'usr/bin').mkdir(parents=True)
                members=[]
                for alias in ('iverilog','vvp'):
                    target=stage/'usr/bin'/alias;target.write_bytes(b'cold fixture, not executable');target.chmod(0o600)
                    members.append({'path':'usr/bin/'+alias,**m.ICARUS_IDENTITIES['icarus' if alias=='iverilog' else alias]})
                (stage/'RECEIPT.json').write_text(json.dumps({'selected':members}))
            if name=='fifo_compile': (out/'fifo/fifo.vvp').write_text(':vpi_module "'+str(out/'icarus/usr/lib/x86_64-linux-gnu/ivl/system.vpi')+'";\n')
            return {'exit_code':0,'cleanup_confirmed':True},raw,{'child_user_cpu_seconds':0.01,'child_system_cpu_seconds':0.01}
        supervisor=types.SimpleNamespace(fixed_support=lambda repo:(base,{},{}),diagnostic_defaults=lambda:{k:None for k in m.OBS_KEYS},run_phase=supervised)
        generic=m.MICRO_LIMITS.copy()
        tool=types.SimpleNamespace(SOURCE_LIMITS=generic,HEADER_LIMITS=generic,PROBE_LIMITS=generic,FIVE=('autoconf','autom4te','m4','flex','bison'),BUILD_LIMITS={n:generic for n in ('autoconf','configure','make')},TINY_LIMITS={n:generic for n in ('version','generate','compile','run')},TRANSPORT_KEYS=(),write_fixture=lambda p,raw:p.write_bytes(raw),environment=lambda *a:{},unchanged_tools=lambda *a:None,verify_runtime=lambda *a:None)
        def toolrun(repo,work,call):
            self.tool_calls+=1;work.mkdir();root=work/'verilator';(root/'bin').mkdir(parents=True)
            binary=root/'bin/verilator_bin';binary.write_bytes(b'mock backend, no native');binary.chmod(0o600)
            runtime=work/'configured_runtime.json';runtime.write_text('{}')
            for n in m.TOOL_STAGES:
                budget=dict(m.expected_tool_limits(tool)[n])
                if self.wrong_budget and n=='official_source473':budget['work_seconds']+=1
                call(n,['mock-native-not-run'],work,{},budget)
            return {'backend':{'path':str(binary),**ident(binary,99)},'verilator_root':str(root),'configured_runtime':{'path':str(runtime),**ident(runtime,99)},'host_programs':{}}
        tool.run=toolrun
        sanitizer=types.SimpleNamespace(sanitize_build_context=lambda *a:m.empty_context('AVAILABLE'))
        acquisition=types.SimpleNamespace(verify_stage=lambda stage,receipt:receipt)
        pins={m.PREFIX+'fixtures/'+n:{'bytes':len((HERE/'fixtures'/n).read_bytes()),'sha256':m.sha((HERE/'fixtures'/n).read_bytes())} for n in m.FIXTURES}
        buffers={n:(HERE/n[len(m.PREFIX):]).read_bytes() for n in pins}
        buffers[m.PREFIX+'icarus_stage.py']=b'# cold acquisition mock never executed\n'
        modules={m.BASE+'ci_support_v3.py':supervisor,m.BASE+'toolchain/ci_toolchain.py':tool,m.BASE+'safe_build_diagnostics.py':sanitizer,m.PREFIX+'icarus_stage.py':acquisition}
        sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]
        env=dict(os.environ);deadline=time.monotonic()+120
        os.environ.update(GITHUB_ACTIONS='true',HOST93_WORK_DEADLINE=str(deadline),HOST93_JOB_DEADLINE=str(deadline+120))
        try:
            with patched(pin_map=lambda:pins,public_sources=sources,load_sources=lambda repo:(pins,buffers,lambda n,label:modules[n]),library_identities=lambda:{},verify_package_elf=lambda *a:None,contract_check=injected_contract):
                with contextlib.redirect_stdout(io.StringIO()): code=m.execute(repo,out,deadline)
                objects={n:m.decode((out/'evidence'/n).read_bytes()) for n in m.EVIDENCE}
                m.validate_evidence(objects)
                return code,objects,pins
        finally:os.environ.clear();os.environ.update(env)

class Cold(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=HERE,prefix='cold_tmp_');self.root=Path(self.temp.name);self.repo=self.root/'repo';self.repo.mkdir()
    def tearDown(self):self.temp.cleanup()
    def runmock(self,**kw):
        case=MockRun(**kw);result=case.run(self.repo,self.root/'out');return case,result
    def test_full_mock_sequence(self):
        case,(code,objects,_)=self.runmock()
        self.assertEqual(code,0);self.assertEqual(case.calls,list(m.STAGES));self.assertEqual(case.tool_calls,1)
        self.assertEqual(len(set(case.deadlines)),1)
        self.assertEqual(objects['summary.json']['status'],'DIAGNOSTIC_OBSERVED')
        row=objects['stage_exits.json']['stages'][-1]
        self.assertEqual(row['status'],'FAILED');self.assertEqual(row['exit_code'],1)
        argv=case.argv['fifo_compile'];self.assertEqual(argv[2:7],['-g2012','-s','fifo_valid_split_tb','-o',str(self.root/'out/fifo/fifo.vvp')])
        self.assertEqual(case.argv['fifo_run'][1:3],['-N','-M'+str(self.root/'out/icarus/usr/lib/x86_64-linux-gnu/ivl')])
        for name in ('host_transparent','host_opaque'):
            self.assertFalse(any(a.startswith('-Wno') or a in ('--build','--exe','--binary') for a in case.argv[name]))
    def test_every_early_failure_stops(self):
        for index,name in enumerate(m.STAGES[:-1]):
            with self.subTest(name=name):
                out=self.root/('out'+str(index));case=MockRun(fail=name);code,obj,_=case.run(self.repo,out)
                self.assertEqual(code,1);self.assertEqual(case.calls,list(m.STAGES[:index+1]));self.assertEqual(obj['summary.json']['status'],'INCOMPLETE')
                self.assertEqual(obj['stage_exits.json']['stages'][-1]['status'],'FAILED')
    def test_timeout_does_not_become_expected(self):
        case,(code,obj,_)=self.runmock(fail='host_opaque',timeout=True)
        self.assertEqual(code,1);self.assertEqual(obj['summary.json']['host_pair']['opaque_warning_count'],0)
        self.assertEqual(obj['stage_exits.json']['stages'][-1]['receipt_timed_out'],True)
    def test_other_opaque_error_stops(self):
        _,(code,obj,_)=self.runmock(opaque=OPAQUE.replace(b'UNOPTFLAT',b'WIDTH'))
        self.assertEqual(code,1);self.assertEqual(obj['summary.json']['host_pair']['opaque_warning_count'],0)
    def test_transparent_warning_stops(self):
        case,(code,obj,_)=self.runmock(transparent=b'%Warning-UNOPTFLAT: unexpected\n')
        self.assertEqual(code,1);self.assertEqual(case.calls[-1],'host_transparent')
    def test_unchanged_toolchain_budget(self):
        case,(code,obj,_)=self.runmock(wrong_budget=True)
        self.assertEqual(code,1);self.assertEqual(case.calls,list(m.STAGES[:3]))
    def test_opaque_strict_parser(self):
        self.assertEqual(m.opaque_observation(OPAQUE,observation(False)),1)
        variants=[OPAQUE.replace(b'UNOPTFLAT',b'WIDTH'),OPAQUE.replace(b'%Warning-',b'%Warning '),OPAQUE.replace(b'1 warning',b'2 warning'),OPAQUE+b'%Error: failure\n',OPAQUE.replace(b'ALWAYS',b'ASSIGNW'),OPAQUE.replace(b'cmd_valid',b'arbitrary'),OPAQUE.replace(b':30:',b':29:'),OPAQUE+b'extra\n',OPAQUE+b'\x00',b'x'*65536]
        for raw in variants:
            with self.assertRaises((ValueError,UnicodeError)):m.opaque_observation(raw,observation(False))
        for key,value in [('exit_code',0),('exit_code',-9),('cleanup_confirmed',False),('receipt_timed_out',True),('waitid_code',2),('failure_code','LOG_LIMIT'),('failure_boundary','USAGE_OR_POSTFLIGHT')]:
            obs=observation(False);obs[key]=value
            with self.assertRaises(ValueError):m.opaque_observation(OPAQUE,obs)
    def test_exact_fifo_counts(self):
        fixture=self.root/'fifo_valid_split_cases.sv'
        complete=FIFO+(str(fixture)+':229: $finish called at 1296000 (1ps)\n').encode()
        self.assertEqual(m.fifo_observation(complete,fixture),{'cases':4,'comparisons':5180})
        for raw in (complete.replace(b'1294',b'1295'),complete+complete,complete.replace(b'SameCycleRW=0',b'SameCycleRW=1'),complete+b'ERROR\n',FIFO,complete.replace(b':229:',b':228:'),complete.replace(b'1296000 (1ps)',b'10000000 (1ps)'),complete.replace(b'(1ps)',b'(1s)')):
            with self.assertRaises(ValueError):m.fifo_observation(raw,fixture)
    def test_schema_tamper(self):
        _,(_,obj,pins)=self.runmock()
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            for mutate in (lambda x:x['summary.json'].update(extra='bad'),lambda x:x['summary.json'].update(seconds=float('nan')),lambda x:x['summary.json'].update(production_host_qualified=True),lambda x:x['stage_exits.json']['stages'].reverse(),lambda x:x['stage_exits.json']['stages'][-1].update(status='EXIT0_CLEANED'),lambda x:x['source_hashes.json']['tools'].update(secret={'bytes':1,'sha256':'0'*64}),lambda x:x['source_hashes.json']['project_sources'][0].update(path='/private/path'),lambda x:x['summary.json']['host_pair'].update(opaque_warning_count=0)):
                bad=copy.deepcopy(obj);mutate(bad)
                with self.assertRaises((ValueError,TypeError)):m.validate_evidence(bad)
    def test_duplicate_json_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(ValueError):m.decode(raw)
    def test_same_buffer_load(self):
        raw=b'answer=41\n';p=self.root/'module.py';p.write_bytes(raw);pin={'bytes':len(raw),'sha256':m.sha(raw)}
        verified=m.exact(p,pin);p.write_bytes(b'answer=99\n');loaded=m.module(verified,p,'cold_samebuffer')
        self.assertEqual(loaded.answer,41)
        with self.assertRaises(ValueError):m.exact(p,pin)
    def test_symlink_and_oversize_rejected(self):
        p=self.root/'source';p.write_bytes(b'abc');link=self.root/'link';link.symlink_to(p)
        with self.assertRaises(ValueError):m.read(link,3)
        with self.assertRaises(ValueError):m.read(p,2)
    def test_deadline_not_restarted(self):
        old=dict(os.environ);now=time.monotonic();stop=now+30
        try:
            os.environ.update(GITHUB_ACTIONS='true',HOST93_WORK_DEADLINE=str(stop),HOST93_JOB_DEADLINE=str(stop+120))
            self.assertEqual(m.deadline(stop),stop)
            for bad in (now-1,now+6600,float('inf'),float('nan'),True):
                with self.assertRaises(ValueError):m.deadline(bad)
            os.environ['HOST93_WORK_DEADLINE']=str(stop+1)
            with self.assertRaises(ValueError):m.deadline(stop)
        finally:os.environ.clear();os.environ.update(old)
    def test_flags_before_project_loads(self):
        for flags in ([],['-I'],['-I','-S'],['-I','-B'],['-S','-B']):
            result=subprocess.run([sys.executable,*flags,str(HERE/'run.py'),'--out',str(self.root/'unused')],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertIn(b'require Python -I -S -B',result.stderr)
        self.assertFalse((self.root/'unused').exists())
    def test_default_refuses_actual(self):
        result=subprocess.run([sys.executable,'-I','-S','-B',str(HERE/'run.py'),'--repo',str(self.repo),'--out',str(self.root/'unused')],capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b'{"status":"INCOMPLETE"}\n');self.assertFalse((self.root/'unused').exists())
    def test_acquisition_child_embeds_verified_buffer(self):
        argv=m.acquisition_argv(b'x=1\n',self.root/'stage',self.root/'stage.py')
        self.assertEqual(argv[:5],['/usr/bin/python3','-I','-S','-B','-c']);self.assertIn("b'x=1\\n'",argv[5]);self.assertNotIn('read_bytes',argv[5])

    def test_vvp_module_witness(self):
        ivl=self.root/'ivl'
        raw=(':vpi_module "'+str(ivl/'system.vpi')+'";\n').encode()
        self.assertEqual(m.verify_vvp_modules(raw,ivl),['system.vpi'])
        for bad in (raw.replace(str(ivl).encode(),b'/usr/lib/x86_64-linux-gnu/ivl'),raw+raw,raw.replace(b'system.vpi',b'unknown.vpi'),raw.replace(b';',b''),b'no modules\n'):
            with self.assertRaises(ValueError):m.verify_vvp_modules(bad,ivl)
    def test_static_elf_parser(self):
        import struct
        raw=bytearray(512);raw[:64]=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,3,62,1,0,64,0,0,64,56,2,0,0,0)
        struct.pack_into('<IIQQQQQQ',raw,64,1,4,0,0,0,512,512,4096)
        struct.pack_into('<IIQQQQQQ',raw,120,2,4,176,176,0,80,80,8)
        table=b'\0libc.so.6\0';raw[300:300+len(table)]=table
        for index,(tag,value) in enumerate(((5,300),(10,len(table)),(1,1),(0,0))):struct.pack_into('<qQ',raw,176+16*index,tag,value)
        self.assertEqual(m.elf_dependencies(bytes(raw)),{'needed':['libc.so.6'],'interpreter':None})
        bad=bytearray(raw);struct.pack_into('<qQ',bad,224,29,0)
        with self.assertRaises(ValueError):m.elf_dependencies(bytes(bad))
        bad=bytearray(raw);bad[301:310]=b'evil.so.1'
        with self.assertRaises(ValueError):m.elf_dependencies(bytes(bad))
        with self.assertRaises(ValueError):m.elf_dependencies(b'not ELF')

    def test_real_source_map_is_pinned(self):
        repo=HERE.parents[1]
        if not (repo/'candidates/host93_ci_recovery').is_dir():repo=repo/'hetero_ci_recovery_20261019T0039'
        pins,buffers,_=m.load_sources(repo)
        self.assertEqual(len(pins),31);self.assertEqual(set(pins),set(buffers))
        self.assertEqual(pins[m.BASE+'ci_support_v3.py']['sha256'],'653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1')
        self.assertEqual(pins[m.BASE+'toolchain/ci_toolchain.py']['sha256'],'5b0923a5f72dd9ecb34380aac176c86d5bf99010938cb6e6cb97a11299fe9a0a')
    def test_log_tail_keeps_only_bounded_suffix(self):
        p=self.root/'native.log';p.write_bytes(b'prefix\n'+b'a'*(m.MIB+40)+b'\nfinal error\n')
        raw,truncated=m.log_tail(p);self.assertTrue(truncated);self.assertEqual(raw,b'final error\n')
        p.write_bytes(b'short\n');self.assertEqual(m.log_tail(p),(b'short\n',False))
    def test_package_elf_fixed_count_and_needed(self):
        rows=[{'path':'p'+str(i),'bytes':4,'sha256':'0'*64} for i in range(21)]
        with patched(exact=lambda *a:b'\x7fELF',elf_dependencies=lambda raw:{'needed':list(m.LIBRARIES[:7]),'interpreter':None}):
            m.verify_package_elf(self.root,{'selected':rows})
            with self.assertRaises(ValueError):m.verify_package_elf(self.root,{'selected':rows[:-1]})
        with patched(exact=lambda *a:b'\x7fELF',elf_dependencies=lambda raw:{'needed':['libc.so.6'],'interpreter':None}):
            with self.assertRaises(ValueError):m.verify_package_elf(self.root,{'selected':rows})

    def test_verify_evidence_rejects_extra_file(self):
        _,(_,obj,pins)=self.runmock()
        (self.root/'out/evidence/private.log').write_text('not eligible')
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            with self.assertRaises(ValueError):m.verify_evidence(self.root/'out')
    def test_workroot_must_be_fresh_and_disjoint(self):
        stop=time.monotonic()+20
        with patched(deadline=lambda value:stop):
            for out in (self.repo,self.repo/'nested',self.root):
                with self.assertRaises(ValueError):m.execute(self.repo,out,float(stop))
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
    def test_safe_evidence_bounds(self):
        _,(_,obj,pins)=self.runmock()
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            for mutate in (lambda x:x['source_hashes.json']['tools']['icarus'].update(sha256='1'*64),lambda x:x['stage_exits.json']['stages'][-1]['diagnostics'].update(merged_log_tail='x'*513),lambda x:x['stage_exits.json']['stages'][-1]['diagnostics'].update(merged_log_tail='\n'*80),lambda x:x['stage_exits.json']['stages'][-1].update(exit_code=True),lambda x:x['stage_exits.json']['stages'][-1].update(child_user_cpu_seconds=float('inf'))):
                bad=copy.deepcopy(obj);mutate(bad)
                with self.assertRaises((ValueError,TypeError)):m.validate_evidence(bad)

    def test_F01_fifo_claim_requires_both_tool_identities(self):
        _,(_,obj,pins)=self.runmock(fail='official_source473')
        self.assertEqual(obj['summary.json']['fifo'],{'cases':4,'comparisons':5180})
        self.assertFalse(obj['summary.json']['toolchain'])
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            m.validate_evidence(obj)
            for aliases in ((),('icarus',),('vvp',)):
                bad=copy.deepcopy(obj)
                bad['source_hashes.json']['tools']={k:obj['source_hashes.json']['tools'][k] for k in aliases}
                with self.assertRaises(ValueError):m.validate_evidence(bad)
    def test_F02_clean_exit_requires_reap_and_cleanup_tuple(self):
        _,(_,obj,pins)=self.runmock()
        mutations=({'waitid_code':2,'waitid_status':9},{'waitid_code':None,'waitid_status':None},
                   {'kill_attempted':False,'kill_result':'NOT_REQUESTED'},
                   {'waitid_code':None,'waitid_status':None,'kill_attempted':False,'kill_result':'NOT_REQUESTED'},
                   {'waitid_code':1,'waitid_status':9},{'kill_attempted':None},{'kill_result':'UNKNOWN'})
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            m.validate_evidence(obj)
            for index in (2,23):
                for changes in mutations:
                    bad=copy.deepcopy(obj);bad['stage_exits.json']['stages'][index].update(changes)
                    with self.assertRaises(ValueError):m.validate_evidence(bad)
                allowed=copy.deepcopy(obj);allowed['stage_exits.json']['stages'][index]['kill_result']='GROUP_ALREADY_ABSENT'
                m.validate_evidence(allowed)
    def test_F03_positive_opaque_requires_available_context(self):
        _,(_,obj,pins)=self.runmock()
        self.assertGreater(obj['summary.json']['host_pair']['opaque_warning_count'],0)
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            m.validate_evidence(obj)
            for state in ('READ_ERROR','SANITIZER_ERROR','NOT_COLLECTED'):
                bad=copy.deepcopy(obj);bad['stage_exits.json']['stages'][-1]['diagnostics']=m.empty_context(state)
                with self.assertRaises(ValueError):m.validate_evidence(bad)


    def test_all_parent_gate_labels_without_native_execution(self):
        tested=[]
        for boundary,code in m.PARENT_CONTRACTS.items():
            if boundary.startswith('LIBRARY_'): continue
            with self.subTest(boundary=boundary):
                case=MockRun(parent_fail=boundary)
                result,obj,_=case.run(self.repo,self.root/('gate_'+boundary))
                self.assertEqual(result,1)
                summary=obj['summary.json']
                self.assertEqual(summary['contract_failure'],{'boundary':boundary,'code':code})
                self.assertEqual(summary['failure_category'],'INPUT_OR_CONTRACT')
                self.assertNotIn('CANARY',json.dumps(obj));self.assertNotIn('/private/credential',json.dumps(obj))
                tested.append(boundary)
        self.assertEqual(len(tested),63)

    def test_parent_failure_categories_and_toolchain_safe_attributes(self):
        for index,(error,category) in enumerate(((ValueError('CANARY'),'INPUT_OR_CONTRACT'),(KeyError('CANARY'),'INPUT_OR_CONTRACT'),(OSError('CANARY'),'SYSTEM'),(TimeoutError('CANARY'),'TIMEOUT'),(KeyboardInterrupt('CANARY'),'INTERRUPTED'),(RuntimeError('CANARY'),'UNEXPECTED'))):
            case=MockRun(parent_fail='ICARUS_RECEIPT_READ',parent_error=error)
            result,obj,_=case.run(self.repo,self.root/('category_'+str(index)))
            self.assertEqual(result,1)
            self.assertEqual(obj['summary.json']['failure_category'],category)
            self.assertEqual(obj['summary.json']['contract_failure'],{'boundary':'ICARUS_RECEIPT_READ','code':'RECEIPT_READ'})
            self.assertEqual(obj['stage_exits.json']['stages'][0]['status'],'EXIT0_CLEANED')
            self.assertEqual(obj['stage_exits.json']['stages'][0]['failure_code'],'NONE')
            self.assertNotIn('CANARY',json.dumps(obj))
        error=ValueError('CANARY');error.safe_contract_boundary='BUILD_CONFIGURE_CPPFLAGS_AFTER';error.safe_contract_code='CPPFLAGS_VALUE'
        case=MockRun(parent_fail='TOOLCHAIN_STAGE_COUNT',parent_error=error)
        _,obj,_=case.run(self.repo,self.root/'safe_toolchain')
        self.assertEqual(obj['summary.json']['contract_failure'],{'boundary':'BUILD_CONFIGURE_CPPFLAGS_AFTER','code':'CPPFLAGS_VALUE'})

    def test_safe_contract_fallback_never_uses_exception_text(self):
        self.assertEqual(m.contract_failure_observation(None),{'boundary':'NONE','code':'NONE'})
        for error in (ValueError('CANARY'),OSError('CANARY'),TimeoutError('CANARY'),KeyboardInterrupt('CANARY'),AssertionError('CANARY')):
            category=m.failure_category(error)
            self.assertEqual(m.contract_failure_observation(error),{'boundary':'UNREPORTED','code':m.FALLBACK_CODES[category]})
            error.safe_contract_boundary='/private/CANARY';error.safe_contract_code='CANARY'
            self.assertEqual(m.contract_failure_observation(error),{'boundary':'UNREPORTED','code':m.FALLBACK_CODES[category]})
        error=ValueError('CANARY');error.safe_contract_boundary=[];error.safe_contract_code={}
        self.assertEqual(m.contract_failure_observation(error),{'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})

    def test_strict_contract_tuple_and_stage_correlation(self):
        _,(_,obj,pins)=self.runmock(parent_fail='ICARUS_RECEIPT_READ')
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            mutations=(
                lambda x:x['summary.json']['contract_failure'].update(extra='CANARY'),
                lambda x:x['summary.json'].update(contract_failure={'boundary':'NONE','code':'NONE'}),
                lambda x:x['summary.json']['contract_failure'].update(boundary='/private/CANARY'),
                lambda x:x['summary.json']['contract_failure'].update(code='CANARY'),
                lambda x:x['summary.json'].update(contract_failure={'boundary':'HOST_TRANSPARENT_LOG','code':'TRANSPARENT_DIAGNOSTIC'}),
                lambda x:x['summary.json'].update(contract_failure={'boundary':'UNREPORTED','code':'SYSTEM_FAILURE'}),
                lambda x:x['summary.json'].update(contract_failure={'boundary':'ICARUS_RECEIPT_READ','code':'TRANSPARENT_DIAGNOSTIC'}),
                lambda x:x['summary.json'].update(failure_category='NONE'),
            )
            for mutate in mutations:
                bad=copy.deepcopy(obj);mutate(bad)
                with self.assertRaises(ValueError):m.validate_evidence(bad)
        _,good,pins=MockRun().run(self.repo,self.root/'positive_labels')
        self.assertEqual(good['summary.json']['contract_failure'],{'boundary':'NONE','code':'NONE'})
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            good['summary.json']['contract_failure']={'boundary':'FINAL_SOURCE_IDENTITIES','code':'SOURCE_CHANGED'}
            with self.assertRaises(ValueError):m.validate_evidence(good)

    def test_library_alias_and_nested_fixed_codes(self):
        # All reads below remain mocked. This verifies distinct public aliases and
        # precise nested codes without uploading or executing library contents.
        old=m.contract_check
        aliases=m.LIBRARY_ALIASES
        def fail(reason):m.require(False,reason)
        for name,alias in aliases.items():
            boundary='LIBRARY_'+alias+'_READ'
            for reason,code in (('absolute normalized ASCII path','INPUT_PATH_SYNTAX'),('bounded regular input','INPUT_REGULAR'),('stable same-buffer input','INPUT_CHANGED')):
                with self.subTest(alias=alias,code=code):
                    try:
                        with old('ICARUS_LIBRARY_IDENTITIES'):
                            with old(boundary):fail(reason)
                    except ValueError as error:
                        self.assertEqual(m.contract_failure_observation(error),{'boundary':boundary,'code':code})
                    else:self.fail('required rejection')
        for reason,code in m.REQUIRE_CODES.items():
            if not code.startswith(('ELF_','LIBRARY_')):continue
            try:
                with old('LIBRARY_STDCXX_ELF'):fail(reason)
            except ValueError as error:
                self.assertEqual(m.contract_failure_observation(error),{'boundary':'LIBRARY_STDCXX_ELF','code':code})
            else:self.fail('required rejection')

    def test_fixed_libstdcxx_path_grammar_and_same_fd_read(self):
        fixed='/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.999'
        self.assertEqual(m.path(fixed),Path(fixed))
        for bad in ('/tmp/libstdc++.so.6.0.33','/usr/lib/x86_64-linux-gnu/other++.so.6','/usr/lib/x86_64-linux-gnu/libstdc++.so.7','/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.1000','/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33.extra','/usr/lib/x86_64-linux-gnu/../libstdc++.so.6','/usr/lib/x86_64-linux-gnu/libstdc++.so.6?secret','/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33/child'):
            with self.assertRaises(ValueError):m.path(bad)
        target=self.root/'plain';target.write_bytes(b'cold bytes');link=self.root/'link';link.symlink_to(target)
        with self.assertRaises(ValueError):m.read(link,64)
        # A read-only same-descriptor integration check; no loader/native call.
        resolved=Path(os.path.realpath('/usr/lib/x86_64-linux-gnu/libstdc++.so.6'))
        self.assertRegex(str(resolved),r'^/usr/lib/x86_64-linux-gnu/libstdc\+\+\.so\.6(?:\.[0-9]{1,3}){0,2}$')
        raw=m.read(resolved,32*m.MIB)
        self.assertTrue(raw.startswith(b'\x7fELF'))
        self.assertEqual(m.sha(raw),hashlib.sha256(resolved.read_bytes()).hexdigest())


    def test_each_library_gate_uses_fixed_alias(self):
        original=m.contract_check
        info=types.SimpleNamespace(st_uid=0,st_nlink=1,st_mode=0o100644,st_dev=1,st_ino=2,st_size=4,st_mtime_ns=1,st_ctime_ns=1)
        class FakePath:
            def __init__(self,value):self.value=str(value)
            def __str__(self):return self.value
            def __eq__(self,other):return isinstance(other,FakePath) and self.value==other.value
            def stat(self):return info
        old_realpath=m.os.path.realpath
        try:
            m.os.path.realpath=lambda p:'/usr/lib/x86_64-linux-gnu/'+str(p).split('/')[-1]
            with patched(Path=FakePath,read=lambda *a:b'ELF',elf_dependencies=lambda raw:{'needed':['libtinfo.so.6'],'interpreter':None}):
                self.assertEqual(len(m.library_identities()),9)
                count=0
                for target,code in m.PARENT_CONTRACTS.items():
                    if not target.startswith('LIBRARY_'):continue
                    @contextlib.contextmanager
                    def reject(boundary):
                        with original(boundary):
                            if boundary==target:raise ValueError('CANARY/private/library')
                            yield
                    with patched(contract_check=reject):
                        with self.assertRaises(ValueError) as caught:m.library_identities()
                    self.assertEqual(m.contract_failure_observation(caught.exception),{'boundary':target,'code':code})
                    count+=1
                self.assertEqual(count,46)
        finally:m.os.path.realpath=old_realpath

    def test_diagnostic_annotation_failure_preserves_original(self):
        class RejectAnnotations(ValueError):
            def __setattr__(self,name,value):
                if name.startswith('safe_contract_'):raise RuntimeError('annotation CANARY')
                return super().__setattr__(name,value)
        error=RejectAnnotations('original CANARY')
        with self.assertRaises(RejectAnnotations) as caught:
            with m.contract_check('ICARUS_RECEIPT_READ'):raise error
        self.assertIs(caught.exception,error)
        self.assertEqual(m.contract_failure_observation(error),{'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})
        class RejectReads(ValueError):
            def __getattribute__(self,name):
                if name.startswith('safe_contract_'):raise RuntimeError('read CANARY')
                return super().__getattribute__(name)
        error=RejectReads('original CANARY')
        with self.assertRaises(RejectReads) as caught:
            with m.contract_check('ICARUS_RECEIPT_READ'):raise error
        self.assertIs(caught.exception,error)
        self.assertEqual(m.contract_failure_observation(error),{'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})


    def test_PC01_actual_short_toolchain_persists_three_files(self):
        original=m.TOOL_STAGES
        for completed in range(21):
            with self.subTest(toolchain_phases=completed):
                out=self.root/('short_'+str(completed))
                with patched(TOOL_STAGES=original[:completed]):
                    case=MockRun();code,obj,pins=case.run(self.repo,out)
                self.assertEqual(set(p.name for p in (out/'evidence').iterdir()),set(m.EVIDENCE))
                if completed<20:
                    self.assertEqual(code,1)
                    self.assertEqual(len(obj['stage_exits.json']['stages']),3+completed)
                    self.assertEqual(obj['summary.json']['status'],'INCOMPLETE')
                    self.assertEqual(obj['summary.json']['contract_failure'],{'boundary':'TOOLCHAIN_STAGE_COUNT','code':'TOOLCHAIN_STAGE_COUNT'})
                    self.assertFalse(obj['summary.json']['toolchain'])
                    self.assertTrue(all(row['status']=='EXIT0_CLEANED' for row in obj['stage_exits.json']['stages']))
                    self.assertEqual(case.calls,list(m.STAGES[:3+completed]))
                else:
                    self.assertEqual(code,0)
                    self.assertEqual(obj['summary.json']['contract_failure'],{'boundary':'NONE','code':'NONE'})
                with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
                    self.assertEqual(m.verify_evidence(out),0)

    def test_PC01_finite_count_edges_do_not_expand_success(self):
        _,(_,complete,pins)=self.runmock()
        def trace(count,boundary):
            obj=copy.deepcopy(complete)
            obj['summary.json'].update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',contract_failure={'boundary':boundary,'code':m.PARENT_CONTRACTS[boundary]},toolchain=False,host_pair={'transparent_exit0':False,'opaque_warning_count':0,'opaque_combo_handshake_path':False})
            obj['summary.json']['fifo']={'cases':4,'comparisons':5180} if count>=3 else {'cases':0,'comparisons':0}
            obj['source_hashes.json']['tools']={k:v for k,v in obj['source_hashes.json']['tools'].items() if k!='derived_backend'} if count else {}
            obj['stage_exits.json']['stages']=obj['stage_exits.json']['stages'][:count]
            return obj
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            # Failed cardinality checks must accept their rejected counts,
            # including count 23 when the check itself raises before comparison.
            for count in range(3,26):m.validate_evidence(trace(count,'TOOLCHAIN_STAGE_COUNT'))
            for count in range(3):
                with self.assertRaises(ValueError):m.validate_evidence(trace(count,'TOOLCHAIN_STAGE_COUNT'))
            for count in range(26):m.validate_evidence(trace(count,'PHASE_ORDER'))
            # The phase-budget check follows the strict phase-order guard.
            m.validate_evidence(trace(24,'PHASE_BUDGET'))
            with self.assertRaises(ValueError):m.validate_evidence(trace(25,'PHASE_BUDGET'))
            for count in (3,22,23,24,25):
                bad=trace(count,'TOOLCHAIN_STAGE_COUNT');bad['summary.json'].update(status='DIAGNOSTIC_OBSERVED',failure_category='NONE',contract_failure={'boundary':'NONE','code':'NONE'})
                with self.assertRaises(ValueError):m.validate_evidence(bad)
            bad=trace(25,'TOOLCHAIN_STAGE_COUNT');bad['stage_exits.json']['stages'].append(copy.deepcopy(bad['stage_exits.json']['stages'][-1]))
            with self.assertRaises(ValueError):m.validate_evidence(bad)
            bad=trace(24,'TOOLCHAIN_STAGE_COUNT');bad['stage_exits.json']['stages'][1].update(observation(False),status='FAILED',diagnostics=m.empty_context('AVAILABLE'))
            with self.assertRaises(ValueError):m.validate_evidence(bad)
            bad=trace(22,'TOOLCHAIN_STAGE_COUNT');bad['stage_exits.json']['stages'].reverse()
            with self.assertRaises(ValueError):m.validate_evidence(bad)

    def test_PC02_rejects_three_contradictory_trace_bundles(self):
        cases=[]
        _,obj,pins=MockRun(parent_fail='ICARUS_RECEIPT_READ').run(self.repo,self.root/'receipt_trace')
        bad=copy.deepcopy(obj);bad['stage_exits.json']['stages'][0].update(observation(False),status='FAILED',diagnostics=m.empty_context('AVAILABLE'));cases.append((bad,pins))
        _,obj,pins=MockRun(parent_fail='PHASE_LOG_POSTFLIGHT').run(self.repo,self.root/'log_trace')
        bad=copy.deepcopy(obj);bad['stage_exits.json']['stages'][0].update(observation(True),status='EXIT0_CLEANED',diagnostics=m.empty_context());cases.append((bad,pins))
        _,obj,pins=MockRun().run(self.repo,self.root/'opaque_trace')
        bad=copy.deepcopy(obj);bad['summary.json'].update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',contract_failure={'boundary':'OPAQUE_CONTEXT','code':'OPAQUE_CONTEXT'});cases.append((bad,pins))
        self.assertEqual(bad['stage_exits.json']['stages'][-1]['diagnostics']['context_state'],'AVAILABLE')
        self.assertGreater(bad['summary.json']['host_pair']['opaque_warning_count'],0)
        for bad,pins in cases:
            with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
                with self.assertRaises(ValueError):m.validate_evidence(bad)


    def test_PC02_all_ordinary_postflight_groups_require_clean_prefix(self):
        checked=0
        for boundary in m.PARENT_CONTRACTS:
            if boundary.startswith(('LIBRARY_','OPAQUE_','FINAL_')) or boundary in ('PHASE_ORDER','PHASE_LOG_POSTFLIGHT','PHASE_BUDGET') or boundary.startswith('HOST_OPAQUE_') and '_BEFORE_' not in boundary:continue
            case=MockRun(parent_fail=boundary)
            _,obj,pins=case.run(self.repo,self.root/('clean_group_'+boundary))
            bad=copy.deepcopy(obj)
            bad['stage_exits.json']['stages'][-1].update(observation(False),status='FAILED',diagnostics=m.empty_context('AVAILABLE'))
            # Remove later positive claims to isolate the parent/prefix link.
            bad['summary.json'].update(fifo={'cases':0,'comparisons':0},toolchain=False,host_pair={'transparent_exit0':False,'opaque_warning_count':0,'opaque_combo_handshake_path':False})
            bad['source_hashes.json']['tools']={k:v for k,v in bad['source_hashes.json']['tools'].items() if k!='derived_backend'}
            with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
                with self.assertRaises(ValueError):m.validate_evidence(bad)
            checked+=1
        self.assertGreater(checked,40)
        _,obj,pins=MockRun(parent_fail='ICARUS_LIBRARY_IDENTITIES').run(self.repo,self.root/'library_prefix')
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            for boundary,code in m.PARENT_CONTRACTS.items():
                if not boundary.startswith('LIBRARY_'):continue
                label=copy.deepcopy(obj);label['summary.json']['contract_failure']={'boundary':boundary,'code':code}
                m.validate_evidence(label)
                label['stage_exits.json']['stages'][0].update(observation(False),status='FAILED',diagnostics=m.empty_context('AVAILABLE'))
                with self.assertRaises(ValueError):m.validate_evidence(label)
        _,obj,pins=MockRun(wrong_budget=True).run(self.repo,self.root/'phase_budget_prefix')
        obj['stage_exits.json']['stages'][-1].update(observation(False),status='FAILED',diagnostics=m.empty_context('AVAILABLE'))
        obj['summary.json']['fifo']={'cases':0,'comparisons':0}
        with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
            with self.assertRaises(ValueError):m.validate_evidence(obj)

    def test_PC02_opaque_internal_and_post_return_groups(self):
        def timeout_row(row):
            row.update(exit_code=-9,final_reap_signal=9,waitid_code=2,waitid_status=9,receipt_timed_out=True,failure_code='SUPERVISOR_TIMEOUT_CLASSIFICATION')
        for boundary in ('OPAQUE_CONTEXT','OPAQUE_LOG_READ','OPAQUE_OBSERVATION','OPAQUE_BUDGET'):
            _,obj,pins=MockRun(parent_fail=boundary).run(self.repo,self.root/('internal_'+boundary))
            with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
                bad=copy.deepcopy(obj);bad['stage_exits.json']['stages'][-1].update(observation(True),status='EXIT0_CLEANED',diagnostics=m.empty_context())
                with self.assertRaises(ValueError):m.validate_evidence(bad)
                timeout=copy.deepcopy(obj);timeout_row(timeout['stage_exits.json']['stages'][-1])
                if boundary=='OPAQUE_BUDGET':
                    with self.assertRaises(ValueError):m.validate_evidence(timeout)
                else:m.validate_evidence(timeout)
        for boundary in ('HOST_OPAQUE_TREE','HOST_OPAQUE_AFTER_FIXTURES','HOST_OPAQUE_AFTER_TOOLS','HOST_OPAQUE_AFTER_RUNTIME','HOST_OPAQUE_AFTER_BACKEND','HOST_OPAQUE_RESULT'):
            _,obj,pins=MockRun(parent_fail=boundary).run(self.repo,self.root/('returned_'+boundary))
            with patched(pin_map=lambda:pins,public_sources=lambda p:[{'path':n,**x} for n,x in sorted(p.items())]):
                m.validate_evidence(obj)
                clean=copy.deepcopy(obj);clean['stage_exits.json']['stages'][-1].update(observation(True),status='EXIT0_CLEANED',diagnostics=m.empty_context())
                m.validate_evidence(clean)
                bad=copy.deepcopy(obj);timeout_row(bad['stage_exits.json']['stages'][-1])
                with self.assertRaises(ValueError):m.validate_evidence(bad)

if __name__=='__main__':unittest.main()
