"""Pinned portable stdlib tests. Never calls recover, limits, or native runtime."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('SOURCE_TEST_FLAGS')
import argparse
import ast
import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',required=True)
args=ap.parse_args()
ROOT=Path(__file__).resolve().parent
REPO=Path(args.repo)
if not (REPO.is_absolute() and '..' not in REPO.parts and REPO.resolve()==REPO and
        not any(p.is_symlink() for p in (REPO,*REPO.parents))):
    raise SystemExit('SOURCE_TEST_REPO_PATH')
SOURCE=ROOT/'n0_dispatch_candidate.py'
ORIGINAL=REPO/'candidates/host93_first_n0_sources/reference/n0_reference.py'
ORIGINAL_PINS=ORIGINAL.with_name('PINS.json')
WORKER_BYTES=21659
WORKER_SHA256='40ce6657c103a1b78b06f9370ebe15b234207a6ce98d7d8e74f5951b0dd51139'
IMPORTS=[]
_real_import=builtins.__import__
def guarded_import(name,*args,**kwargs):
    IMPORTS.append(name)
    if name.split('.')[0] in ('torch','numpy','transformers','requests','urllib','socket','subprocess','ctypes'):
        raise RuntimeError('FORBIDDEN_COLD_IMPORT')
    return _real_import(name,*args,**kwargs)

def read_worker(candidate):
    """Bounded fixed source identity; return the sole buffer eligible to compile."""
    if not (candidate.is_absolute() and '..' not in candidate.parts and
            candidate.resolve()==candidate and
            not any(p.is_symlink() for p in (candidate,*candidate.parents))):
        raise RuntimeError('SOURCE_TEST_WORKER_PATH')
    fd=os.open(candidate,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size!=WORKER_BYTES:
            raise RuntimeError('SOURCE_TEST_WORKER_SIZE')
        pieces=[];total=0
        while total<=WORKER_BYTES:
            chunk=os.read(fd,WORKER_BYTES+1-total)
            if not chunk:
                break
            pieces.append(chunk);total+=len(chunk)
        raw=b''.join(pieces)
        after=os.fstat(fd);current=candidate.stat()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(before)!=identity(after) or identity(after)!=identity(current):
            raise RuntimeError('SOURCE_TEST_WORKER_CHANGED')
        if len(raw)!=WORKER_BYTES:
            raise RuntimeError('SOURCE_TEST_WORKER_SIZE')
        if hashlib.sha256(raw).hexdigest()!=WORKER_SHA256:
            raise RuntimeError('SOURCE_TEST_WORKER_SHA')
        return raw
    finally:
        os.close(fd)

def load_worker(candidate):
    raw=read_worker(candidate)
    namespace={'__name__':'cold_candidate','__file__':str(candidate)}
    builtins.__import__=guarded_import
    try:
        exec(compile(raw,str(candidate),'exec'),namespace)
    finally:
        builtins.__import__=_real_import
    return raw,namespace

RAW,NAMESPACE=load_worker(SOURCE)
sys.argv=[sys.argv[0]]

class SourceTests(unittest.TestCase):
    def reject(self, fn, *args):
        with self.assertRaises(NAMESPACE['Rejected']):
            fn(*args)

    def report(self, stop='source', passed=False):
        r = NAMESPACE['new_report']()
        for gate, stage in zip(NAMESPACE['GATES'],NAMESPACE['STAGES']):
            NAMESPACE['enter_gate'](r,gate,stage)
            if gate == 'capability':
                r.update(capability_observed=True,observed_capability='AVX2')
            if gate == 'forward':
                r.update(full_shape_verified=True,hashes_checked=True)
            if gate == stop:
                if passed:
                    NAMESPACE['pass_gate'](r,gate)
                break
            NAMESPACE['pass_gate'](r,gate)
        return r

    def complete(self, native=True, f32=True):
        r = self.report('postflight',True)
        r.update(bf16_sha_exact=native,f32_sha_exact=f32,dual_sha_exact=native and f32)
        if native and f32:
            r.update(status='CANDIDATE_EXACT_MATCH',code=None,stage='COMPLETE')
        else:
            r.update(status='CANDIDATE_HASH_MISMATCH',code='HASH_MISMATCH')
        return r

    def test_original_frozen_identities(self):
        self.assertEqual(len(ORIGINAL.read_bytes()),13753)
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'d26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4')
        self.assertEqual(len(ORIGINAL_PINS.read_bytes()),6364)
        self.assertEqual(hashlib.sha256(ORIGINAL_PINS.read_bytes()).hexdigest(),'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8')
        self.assertEqual((ROOT/'ORIGINAL_PINS.json').read_bytes(),ORIGINAL_PINS.read_bytes())

    def test_exact_forward_and_inverse_substitutions(self):
        proof = json.loads((ROOT/'EXACT_SUBSTITUTIONS.json').read_bytes())
        candidate = ORIGINAL.read_text()
        for entry in proof['substitutions']:
            self.assertEqual(candidate.count(entry['old']),1)
            candidate = candidate.replace(entry['old'],entry['new'])
        self.assertEqual(candidate.encode(),RAW)
        for entry in reversed(proof['substitutions']):
            self.assertEqual(candidate.count(entry['new']),1)
            candidate = candidate.replace(entry['new'],entry['old'])
        self.assertEqual(candidate.encode(),ORIGINAL.read_bytes())

    def test_fixed_helpers_preserved(self):
        a={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(ORIGINAL.read_bytes()).body if isinstance(x,ast.FunctionDef)}
        b={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(RAW).body if isinstance(x,ast.FunctionDef)}
        for name in ('need','sha','path','read_checked','load_pins','official_node','source_buffers','output_identity','no_external_actions','limits','runtime_before','write_new'):
            self.assertEqual(a[name],b[name],name)

    def test_official_class_and_source_buffers(self):
        pins=NAMESPACE['load_pins'](ORIGINAL_PINS)
        buffers=NAMESPACE['source_buffers'](REPO,pins)
        node=NAMESPACE['official_node'](buffers[pins['official_class']['path']],pins['official_class'])
        self.assertEqual(hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),'af69b413179ffd44d8dbfa6a0573075c2ed72b6d3a137cf9b290aca3081a59ef')
        self.assertEqual(pins['runtime_requirements']['capability'],'AVX512')
        self.assertEqual(len([key for key in pins['runtime_native_files'] if key != 'python']),5)
        self.assertEqual(sum(x['bytes'] for x in pins['raw2'].values()),789504)
        self.assertEqual(pins['limits']['wall_seconds'],120)
        self.assertEqual(pins['limits']['cpu_seconds'],90)
        self.assertEqual(pins['limits']['address_space_bytes'],8589934592)
        self.assertEqual(pins['limits']['private_output_bytes'],4194304)

    def test_cold_import_and_default(self):
        self.assertTrue(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
        self.assertFalse(any(x in sys.modules for x in ('torch','numpy','transformers')))
        original=NAMESPACE['recover']
        def prohibited(*args):
            raise RuntimeError('EXECUTION_FORBIDDEN')
        NAMESPACE['recover']=prohibited
        try:
            text=io.StringIO()
            with contextlib.redirect_stdout(text):
                self.assertEqual(NAMESPACE['main']([]),0)
            self.assertEqual(text.getvalue(),'N0_DISPATCH_CANDIDATE_NOT_EXECUTED\n')
        finally:
            NAMESPACE['recover']=original

    def test_capability_enum_no_stringification(self):
        class Poison:
            def __str__(self):
                raise RuntimeError('MUST_NOT_STRINGIFY')
        for value in ('DEFAULT','AVX2','AVX512'):
            self.assertEqual(NAMESPACE['finite_capability'](value),value)
        for value in ('avx2','AVX512 /private/secret','',None,{},[],1,Poison()):
            self.assertEqual(NAMESPACE['finite_capability'](value),'OTHER')
        self.assertEqual(set(NAMESPACE['KNOWN_BUILDS']),{'AVX2','AVX512'})
        for value in ('DEFAULT','OTHER','avx2',None,1):
            self.reject(NAMESPACE['allowed_build'],value)
        profile=ast.parse((REPO/'candidates/qwen2_fullblock_ci_execution/runtime_profile.py').read_bytes())
        expected=next(ast.literal_eval(x.value) for x in profile.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='AVX2_BUILD_SHA256' for t in x.targets))
        self.assertEqual(NAMESPACE['allowed_build']('AVX2'),expected)
        self.assertEqual(NAMESPACE['allowed_build']('AVX512'),json.loads(ORIGINAL_PINS.read_bytes())['runtime_requirements']['torch_build_sha256'])

    def test_both_identity_hard_gates(self):
        native=b'n'*NAMESPACE['BF16_BYTES']
        widened=b'w'*NAMESPACE['F32_BYTES']
        original_sha=NAMESPACE['sha']
        try:
            for nm, fm in ((True,True),(True,False),(False,True),(False,False)):
                def synthetic_sha(value,nm=nm,fm=fm):
                    if value is native and nm:
                        return NAMESPACE['BF16_SHA256']
                    if value is widened and fm:
                        return NAMESPACE['F32_SHA256']
                    return '0'*64
                NAMESPACE['sha']=synthetic_sha
                output=NAMESPACE['output_identity'](native,widened)
                self.assertIs(output['native_exact'],nm)
                self.assertIs(output['fp32le_exact'],fm)
                self.assertIs(output['accepted'],nm and fm)
            NAMESPACE['sha']=lambda value: NAMESPACE['BF16_SHA256'] if len(value)<NAMESPACE['F32_BYTES'] else NAMESPACE['F32_SHA256']
            self.assertFalse(NAMESPACE['output_identity'](native[:-1],widened)['accepted'])
        finally:
            NAMESPACE['sha']=original_sha
        self.assertFalse(NAMESPACE['output_identity'](native,widened)['accepted'])

    def test_finite_projection_privacy(self):
        r=self.report('capability')
        r.update(observed_capability='OTHER',code='DISPATCH',output={'sha256':'private-output-hash'},secret='/private/secret')
        projection=NAMESPACE['public_projection'](r)
        self.assertEqual(set(projection),set(NAMESPACE['PUBLIC_KEYS']))
        encoded=json.dumps(projection)
        self.assertNotIn('private',encoded)
        self.assertNotIn('sha256',encoded)
        self.assertNotIn('output',encoded)
        self.assertEqual(NAMESPACE['validate_public_observation'](projection),projection)
        self.reject(NAMESPACE['validate_public_observation'],r)
        for cap in ('DEFAULT','AVX2','AVX512','OTHER'):
            r['observed_capability']=cap
            self.assertEqual(NAMESPACE['public_projection'](r)['observed_capability'],cap)

    def test_all_gate_failure_prefixes(self):
        for gate in NAMESPACE['GATES']:
            r=self.report(gate)
            self.assertEqual(NAMESPACE['validate_public_observation'](r),r)

    def test_completed_match_and_all_mismatch_combinations(self):
        for nm,fm in ((True,True),(True,False),(False,True),(False,False)):
            r=self.complete(nm,fm)
            self.assertEqual(NAMESPACE['validate_public_observation'](r),r)
            for field in ('reference_accepted','baseline_adopted','dut_executed','rtl_executed','fullblock_executed'):
                self.assertIs(r[field],False)

    def test_strict_schema_rejects_mutants(self):
        validate=NAMESPACE['validate_public_observation']
        for original in (self.report('capability'),self.complete(),self.complete(False,True)):
            for key in original:
                mutant=copy.deepcopy(original);del mutant[key]
                self.reject(validate,mutant)
            mutant=copy.deepcopy(original);mutant['new_output_sha256']='x'*64
            self.reject(validate,mutant)
            for key in ('reference_accepted','baseline_adopted','dut_executed','rtl_executed','fullblock_executed'):
                mutant=copy.deepcopy(original);mutant[key]=True
                self.reject(validate,mutant)
            for key,value in (('schema',True),('scope','other'),('status','PASS_FROZEN_N0_EXACT'),('code','/private'),('stage','/private'),('observed_capability','/private'),('expected_capability','AVX2'),('dual_sha_exact',1)):
                mutant=copy.deepcopy(original);mutant[key]=value
                self.reject(validate,mutant)
        for gate in NAMESPACE['GATES']:
            mutant=self.complete();mutant['gates_passed'][gate]=False
            self.reject(validate,mutant)
            mutant=self.complete();mutant['gates_reached'][gate]=False
            self.reject(validate,mutant)
        for key in ('full_shape_verified','hashes_checked','bf16_sha_exact','f32_sha_exact','dual_sha_exact','capability_observed'):
            mutant=self.complete();mutant[key]=False
            self.reject(validate,mutant)
        for key in ('gates_reached','gates_passed'):
            mutant=self.complete();mutant[key]['inventory']=True
            self.reject(validate,mutant)
            mutant=self.complete();mutant[key]['source']=1
            self.reject(validate,mutant)
        mutant=self.report('source');mutant['stage']='POSTFLIGHT'
        self.reject(validate,mutant)
        mutant=self.report('source');mutant['gates_reached']['forward']=True
        self.reject(validate,mutant)
        mutant=self.complete(False,False);mutant['dual_sha_exact']=True
        self.reject(validate,mutant)
        mutant=self.complete();mutant['observed_capability']='DEFAULT'
        self.reject(validate,mutant)

    def test_safe_stdout_markers(self):
        expected={'N0_DISPATCH_CANDIDATE_NOT_EXECUTED','CANDIDATE_EXACT_MATCH','CANDIDATE_HASH_MISMATCH:HASH_MISMATCH'}
        expected.update('NOT_COMPLETED:'+code for code in NAMESPACE['CODES'])
        self.assertEqual(NAMESPACE['SAFE_MARKERS'],frozenset(expected))
        self.assertNotIn('PASS_FROZEN_N0_EXACT',NAMESPACE['SAFE_MARKERS'])

    def test_read_checked_same_buffer_gate(self):
        raw=b'stdlib-fixture'
        pin={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        with tempfile.TemporaryDirectory(prefix='candidate-cold-') as folder:
            p=Path(folder)/'data';p.write_bytes(raw)
            self.assertEqual(NAMESPACE['read_checked'](p,pin),raw)
            link=Path(folder)/'link';link.symlink_to(p)
            self.reject(NAMESPACE['read_checked'],link,pin)
            p.write_bytes(raw+b'!')
            self.reject(NAMESPACE['read_checked'],p,pin)

    def test_no_automatic_profile_or_override_and_single_forward(self):
        tree=ast.parse(RAW)
        recover=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='recover')
        segment=ast.get_source_segment(RAW.decode(),recover)
        self.assertNotIn('QWEN2_CI_RUNTIME_PROFILE',segment)
        self.assertNotIn('runtime_profile',segment)
        self.assertNotIn('os.environ[',segment)
        self.assertNotIn('os.putenv',segment)
        for forbidden in ('ATEN_CPU_CAPABILITY','MKL_CBWR','ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA'):
            self.assertIn(forbidden,segment)
        ordered=('get_cpu_capability()',"allowed_build(report['observed_capability'])",'torch.set_num_threads(4)','torch.set_num_interop_threads(1)','torch.use_deterministic_algorithms(True)',"sha(torch.__config__.show().encode()) == candidate_build",'n0 = norm(x)',"need(report['output']['accepted'], 'HASH_MISMATCH')")
        self.assertEqual([segment.index(x) for x in ordered],sorted(segment.index(x) for x in ordered))
        self.assertEqual(segment.count('n0 = norm(x)'),1)
        self.assertNotIn("write_new(out,'n0.",segment)
        self.assertNotIn('reference_accepted=True',segment)
        self.assertNotIn('PASS_FROZEN_N0_EXACT',segment)
        self.assertIn("out.mkdir(mode=0o700)",segment)
        main=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='main')
        maintext=ast.get_source_segment(RAW.decode(),main)
        self.assertIn("return 0 if report['status'] == 'CANDIDATE_EXACT_MATCH' else 1",maintext)
        self.assertIn("choices=('ci31214',)",maintext)

    def test_loader_bad_size_same_length_sha_and_same_buffer(self):
        with tempfile.TemporaryDirectory(prefix='candidate-loader-') as folder:
            p=Path(folder)/'worker.py'
            p.write_bytes(RAW+b'!')
            with self.assertRaisesRegex(RuntimeError,'^SOURCE_TEST_WORKER_SIZE$'):
                load_worker(p)
            poison=b"raise RuntimeError('UNTRUSTED_EXECUTED')\n"
            p.write_bytes(poison+RAW[len(poison):])
            self.assertEqual(p.stat().st_size,WORKER_BYTES)
            with self.assertRaisesRegex(RuntimeError,'^SOURCE_TEST_WORKER_SHA$'):
                load_worker(p)
            p.write_bytes(RAW)
            same,loaded=load_worker(p)
            self.assertEqual(same,RAW)
            self.assertEqual(loaded['KNOWN_BUILDS'],NAMESPACE['KNOWN_BUILDS'])
            self.assertNotIn('torch',sys.modules)
            link=Path(folder)/'link';link.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError,'^SOURCE_TEST_WORKER_PATH$'):
                load_worker(link)

    def test_atomic_gate_and_capability_interruption(self):
        tree=ast.parse(RAW)
        recover=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='recover')
        body=next(n for n in recover.body if isinstance(n,ast.Try)).body
        start=next(i for i,n in enumerate(body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and
                   isinstance(n.value.func,ast.Name) and n.value.func.id=='enter_gate' and
                   len(n.value.args)>1 and isinstance(n.value.args[1],ast.Constant) and n.value.args[1].value=='capability')
        fragment=compile(ast.Module(body=body[start:start+4],type_ignores=[]),str(SOURCE),'exec')
        fake_torch=types.SimpleNamespace(backends=types.SimpleNamespace(cpu=types.SimpleNamespace(get_cpu_capability=lambda:'AVX2')))
        def setup_gate():
            r=self.report('source',True)
            return r,lambda:NAMESPACE['enter_gate'](r,'raw2','RAW2')
        def setup_capability():
            r=self.report('version',True)
            local=dict(NAMESPACE,report=r,torch=fake_torch)
            return r,lambda:exec(fragment,local)
        for setup in (setup_gate,setup_capability):
            r,action=setup();events=[]
            def observe(frame,event,arg):
                if frame.f_code.co_filename==str(SOURCE):
                    if event in ('line','return'):events.append((frame.f_code.co_name,frame.f_lineno,event))
                return observe
            prior=sys.gettrace()
            try:
                sys.settrace(observe);action()
            finally:
                sys.settrace(prior)
            self.assertGreater(len(events),0)
            for target in range(len(events)):
                r,action=setup();count=[0];sentinel=NAMESPACE['Rejected']('DEADLINE')
                def interrupt(frame,event,arg):
                    if frame.f_code.co_filename==str(SOURCE):
                        if event in ('line','return'):
                            current=count[0];count[0]+=1
                            if current==target:raise sentinel
                    return interrupt
                try:
                    sys.settrace(interrupt)
                    action()
                except NAMESPACE['Rejected'] as error:
                    self.assertIs(error,sentinel)
                    r.update(code=error.code,status='NOT_COMPLETED')
                else:
                    self.fail('INTERRUPTION_NOT_REACHED')
                finally:
                    sys.settrace(prior)
                projected=NAMESPACE['receipt_projection'](r)
                self.assertEqual(projected['code'],'DEADLINE')
                self.assertEqual(projected['status'],'NOT_COMPLETED')
                if not projected['capability_observed']:
                    self.assertEqual(projected['observed_capability'],'OTHER')
                else:
                    self.assertEqual(projected['observed_capability'],'AVX2')
                self.assertFalse(projected['reference_accepted'])

    def test_receipt_projection_preserves_primary_failure(self):
        original=NAMESPACE['public_projection']
        def secondary(report):
            raise NAMESPACE['Rejected']('OUTPUT')
        try:
            NAMESPACE['public_projection']=secondary
            for code in NAMESPACE['CODES']:
                r=self.report('source');r['code']=code
                with self.assertRaises(NAMESPACE['Rejected']) as caught:
                    NAMESPACE['receipt_projection'](r)
                self.assertEqual(caught.exception.code,code)
            with self.assertRaises(NAMESPACE['Rejected']) as caught:
                NAMESPACE['receipt_projection'](self.complete())
            self.assertEqual(caught.exception.code,'OUTPUT')
        finally:
            NAMESPACE['public_projection']=original

    def test_original_forward_postflight_text_unchanged(self):
        old=ORIGINAL.read_text();new=RAW.decode()
        def section(text,start,end):
            return text[text.index(start):text.index(end)+len(end)]
        start="        namespace = {'torch':torch,'nn':nn}"
        end="        report['output'] = output_identity(native,data)"
        self.assertEqual(section(old,start,end),section(new,start,end).replace("        report['full_shape_verified'] = True\n",'',1))
        start="        need(source_buffers(repo,pins) == buffers, 'CHANGED')"
        end="        need(time.monotonic() < args.shared_stop - 5, 'DEADLINE')"
        self.assertEqual(section(old,start,end),section(new,start,end))

if __name__=='__main__':
    unittest.main(verbosity=2)
