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
RUN_BYTES=36443
RUN_SHA='99ca1477f3ac7dbd7eed8d5c22c4aa1d37f5ef4fb4f736a39ef6a4aa24689e80'

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
    def __init__(self,fail=None,opaque=OPAQUE,timeout=False,wrong_budget=False,transparent=b''):
        self.fail,self.opaque,self.timeout=fail,opaque,timeout
        self.wrong_budget,self.transparent=wrong_budget,transparent
        self.calls=[];self.deadlines=[];self.argv={};self.tool_calls=0
    def run(self,repo,out):
        self.out=out
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
            with patched(pin_map=lambda:pins,public_sources=sources,load_sources=lambda repo:(pins,buffers,lambda n,label:modules[n]),library_identities=lambda:{},verify_package_elf=lambda *a:None):
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

if __name__=='__main__':unittest.main()
