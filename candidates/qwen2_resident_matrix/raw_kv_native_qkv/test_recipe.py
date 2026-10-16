"""Cold source/control and bounded Fraction fixtures; no native acceptance.

The ndarray/CDLL doubles below are CONTROL_ONLY protocol fixtures. They neither
calculate QKV outputs nor establish the required full-native M16/M128 gates.
"""
import ast
import builtins
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[3]
REFERENCE='candidates/qwen2_resident_matrix/dense_block_reduce/reference/'


def exact(word):
    exponent=(word>>23)&255;mantissa=word&0x7fffff
    if exponent==255:raise ValueError('finite Fraction fixture required')
    shift=-149 if exponent==0 else exponent-150
    if exponent:mantissa+=1<<23
    if word>>31:mantissa=-mantissa
    return Fraction(mantissa<<max(shift,0),1<<max(-shift,0))


def rounded(number):
    """Exact integer quotient/remainder, binary32 nearest-even rounding."""
    sign=0x80000000 if number<0 else 0
    if not number:return sign
    numerator,denominator=abs(number).as_integer_ratio()
    exponent=numerator.bit_length()-denominator.bit_length()
    if abs(number)<Fraction(1<<max(exponent,0),1<<max(-exponent,0)):exponent-=1
    shift=149 if exponent < -126 else 23-exponent
    numerator<<=max(shift,0);denominator<<=max(-shift,0)
    quotient,remainder=divmod(numerator,denominator)
    quotient+=2*remainder>denominator or (2*remainder==denominator and quotient&1)
    if exponent < -126:return sign|quotient
    if quotient>=1<<24:quotient>>=1;exponent+=1
    if exponent>127:return sign|0x7f800000
    return sign|((exponent+127)<<23)|(quotient&0x7fffff)


def bf16(word):
    if word&0x7f800000==0x7f800000:raise ValueError('finite BF16 fixture required')
    high,low=word>>16,word&0xffff
    high+=low>0x8000 or (low==0x8000 and high&1)
    return (high<<16)&0xffffffff


def pair_dot(activation,weights,blocks,*,pair_first=True,round_blocks=False):
    if (len(blocks)!=2 or any(type(n) is not int or n<=0 or n%2 for n in blocks)
            or sum(blocks)!=len(activation) or len(weights)!=len(activation)):
        raise ValueError('two positive even complete blocks required')
    begin=0;total=0
    for size in blocks:
        partial=0
        for issue in range(size):
            index=begin+(issue^1 if pair_first else issue)
            partial=rounded(exact(bf16(activation[index]))*exact(bf16(weights[index]))+exact(partial))
        if round_blocks:partial=bf16(partial)
        total=rounded(exact(partial)+exact(total));begin+=size
    return total


class FractionRecipeTests(unittest.TestCase):
    def test_k6_pair_order_and_block_boundary_distinguish_increasing_k(self):
        activation=[0x3f800000]*6
        weights=[0x3f800000,0,0xbf800000,0x33800000,0,0]
        self.assertEqual(pair_dot(activation,weights,[4,2]),0)
        self.assertEqual(pair_dot(activation,weights,[4,2],pair_first=False),0x33800000)
        self.assertEqual(pair_dot(activation,weights,[2,4]),0x33800000)
        for blocks in ([3,3],[True,5],[0,6],[2,2],[2,2,2]):
            with self.subTest(blocks=blocks),self.assertRaises(ValueError):pair_dot(activation,weights,blocks)

    def test_bias_once_and_single_final_bf16_boundary(self):
        one=0x3f800000;quarter_ulp=rounded(Fraction(1,512));half_ulp=rounded(Fraction(1,256))
        dot=pair_dot([one]*4,[one,half_ulp,0,0],[2,2])
        result=bf16(rounded(exact(dot)+exact(quarter_ulp)))
        early=bf16(rounded(exact(bf16(dot))+exact(quarter_ulp)))
        self.assertEqual((result,early),(0x3f810000,one))
        dot=pair_dot([one]*4,[one,0,one,0],[2,2])
        self.assertEqual(bf16(rounded(exact(dot)+exact(one))),0x40400000)
        self.assertNotEqual(bf16(rounded(exact(dot)+2*exact(one))),0x40400000)
        weights=[one,half_ulp,0,0,quarter_ulp,0]
        self.assertEqual(bf16(pair_dot([one]*6,weights,[4,2])),0x3f810000)
        self.assertEqual(bf16(pair_dot([one]*6,weights,[4,2],round_blocks=True)),one)

    def test_bf16_ties_subnormal_and_exact_fused_cancellation(self):
        self.assertEqual(bf16(0x3f808000),0x3f800000)
        self.assertEqual(bf16(0x3f818000),0x3f820000)
        self.assertEqual(bf16(0x00008000),0)
        self.assertEqual(bf16(0x00018000),0x00020000)
        self.assertEqual(pair_dot([0x00010000,0,0,0],[0x3f800000,0,0,0],[2,2]),0x00010000)
        # These exact binary32 operands expose fused versus two-round FP32.
        a=0x3f800001;b=0x3f7ffffe;c=0xbf800000
        fused=rounded(exact(a)*exact(b)+exact(c))
        unfused=rounded(exact(rounded(exact(a)*exact(b)))+exact(c))
        self.assertEqual(fused,0xa8800000);self.assertEqual(unfused,0)


class SourceRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from . import prepare
        cls.p=prepare;cls.original=prepare.read(prepare.ORIGINAL)
        cls.temp=tempfile.TemporaryDirectory(prefix='qkv-source-only-');cls.addClassCleanup(cls.temp.cleanup)
        target=Path(cls.temp.name)/prepare.ORIGINAL;target.parent.mkdir(parents=True);target.write_bytes(cls.original)
        subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=cls.temp.name,
            input=prepare.read(prepare.PREFIX+'variant.patch'),check=True,capture_output=True,timeout=10)
        cls.generated=target.read_bytes()

    def test_original_identity_and_disabled_ast_projection_preserve_all_other_functions(self):
        p=self.p;p.check_scope(self.original,self.generated)
        self.assertEqual(p.sha(self.original),p.ORIGINAL_SHA256)
        old={n.name:n for n in ast.parse(self.original).body if isinstance(n,ast.FunctionDef)}
        new={n.name:n for n in ast.parse(self.generated).body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(old.keys(),new.keys())
        for name in old.keys()-{'independent_forward','run_gate'}:
            self.assertEqual(ast.dump(old[name]),ast.dump(new[name]),name)
        for name in ('independent_forward','run_gate'):
            self.assertEqual([a.arg for a in new[name].args.kwonlyargs],['qkv_recipe'])
            self.assertEqual(ast.literal_eval(new[name].args.kw_defaults[0]),None)
        self.assertEqual(p.read(p.ORIGINAL),self.original)

    def test_explicit_branch_uses_only_own_linear_operands_and_binds_m16_identity(self):
        tree=ast.parse(self.generated)
        independent=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='independent_forward')
        linear=next(n for n in independent.body if isinstance(n,ast.FunctionDef) and n.name=='linear')
        branch=linear.body[0]
        self.assertEqual(ast.unparse(branch.test),
            "mode == 'bf16' and qkv_recipe is not None and (name in ('self_attn.q_proj', 'self_attn.k_proj', 'self_attn.v_proj'))")
        call=next(n for n in ast.walk(branch) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and n.func.attr=='linear')
        self.assertEqual(ast.unparse(call),"qkv_recipe.linear(value, weights[name + '.weight'], weights[name + '.bias'], name)")
        names={n.id for n in ast.walk(branch) if isinstance(n,ast.Name)}
        self.assertFalse(names&{'native','native_cache','torch','module','layer','xt'})
        gate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_gate')
        text=ast.unparse(gate)
        self.assertLess(text.index('qkv_identity = validate'),text.index('import torch'))
        self.assertLess(text.index("identity['independent_qkv_recipe'] = qkv_identity"),text.index('validate_small_gate('))
        self.assertIn('qkv_recipe=qkv_recipe',text)
        self.assertLess(text.rindex('qkv_recipe.revalidate()'),text.rindex("'RESULT.json'"))

    def test_scope_rejects_non_qkv_verdict_or_arithmetic_mutation(self):
        for function in ('stage_verdict','native_forward','independent_forward'):
            tree=ast.parse(self.generated)
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
            node.body.append(ast.parse('unapproved_callback()').body[0])
            with self.subTest(function=function),self.assertRaises(ValueError):
                self.p.check_scope(self.original,ast.unparse(tree))

    def test_preparer_enforces_generated_pin_even_for_enabled_only_change(self):
        p=self.p
        frozen=dict(source_sha256={p.ORIGINAL:p.sha(self.original)},pins_sha256='a'*64,
            generated_module_sha256=p.sha(self.generated))
        with tempfile.TemporaryDirectory() as temp,patch.object(p,'snapshot',return_value=frozen):
            receipt=p.prepare(Path(temp)/'good')
            self.assertEqual(receipt['status'],'PASS_SOURCE_PREPARATION_ONLY')
            self.assertIs(receipt['numerical_execution'],False)
            with self.assertRaises(ValueError):p.prepare(Path(temp)/'good')
        # The disabled projection alone cannot justify added enabled semantics.
        tree=ast.parse(self.generated)
        independent=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='independent_forward')
        linear=next(n for n in independent.body if isinstance(n,ast.FunctionDef) and n.name=='linear')
        linear.body[0].body.insert(0,ast.parse('unapproved_callback()').body[0])
        changed=ast.unparse(tree).encode();p.check_scope(self.original,changed)
        import difflib
        mutation=''.join(difflib.unified_diff(self.original.decode().splitlines(keepends=True),
            (changed.decode()+'\n').splitlines(keepends=True),fromfile='a/'+p.ORIGINAL,tofile='b/'+p.ORIGINAL)).encode()
        read=p.read
        with tempfile.TemporaryDirectory() as temp,patch.object(p,'snapshot',return_value=frozen), \
                patch.object(p,'read',side_effect=lambda name:mutation if name==p.PREFIX+'variant.patch' else read(name)), \
                self.assertRaises(ValueError):p.prepare(Path(temp)/'bad')
        self.assertEqual(p.read(p.ORIGINAL),self.original)

    def test_real_pinned_source_closures_and_preparation_agree(self):
        from . import kernel
        frozen=self.p.snapshot();native=kernel.source_snapshot()
        self.assertEqual(native['source_sha256'],dict(frozen['source_sha256'],
            **{kernel.PINS_PATH:frozen['pins_sha256']}))
        self.assertEqual(len(frozen['source_sha256']),10)
        self.assertEqual(native['cpp_sha256'],self.p.sha(kernel.source_bytes()))
        self.assertEqual(native['generated_module_sha256'],self.p.sha(self.generated))
        with tempfile.TemporaryDirectory() as temp:
            receipt=self.p.prepare(Path(temp)/'fresh')
            self.assertEqual(receipt['source_sha256'],frozen['source_sha256'])
            self.assertEqual(receipt['pins_sha256'],native['pins_sha256'])
            self.assertIs(receipt['numerical_execution'],False)
        self.assertEqual(self.p.read(self.p.ORIGINAL),self.original)


class KernelRecipeTests(unittest.TestCase):
    def fixture(self,out):
        """Synthetic ELF header and metadata only; never loaded or executed."""
        from . import kernel as k
        source=k.source_bytes();(out/k.CPP).write_bytes(source)
        binary=bytearray(64);binary[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',binary,16,3,62)
        (out/k.LIBRARY).write_bytes(binary)
        frozen=dict(source_sha256={'CONTROL_ONLY/source.py':'a'*64},pins_sha256='b'*64,
            cpp_sha256=k.sha(source),generated_module_sha256='c'*64)
        compiler=dict(path='/CONTROL_ONLY/g++',sha256='d'*64)
        value=dict(schema=1,profile=k.PROFILE,status='COMPILED_QKV_RECIPE',returncode=0,
            numerical_execution=False,official_framework_acceptance=False,**frozen,compiler=compiler,
            argv=[compiler['path'],*k.FLAGS,str(out/k.CPP),'-o',str(out/k.LIBRARY)],
            library_sha256=k.sha(binary),elapsed_seconds=0.1,total_budget_seconds=k.TOTAL)
        (out/k.RECEIPT).write_bytes(k.encoded(value))
        return k,frozen,compiler,value

    def test_exact_pinned_dot16_reuse_flags_and_no_official_result_dependency(self):
        from . import kernel as k
        source=k.source_bytes();dot=(ROOT/k.DOT).read_bytes()
        self.assertEqual(k.sha(dot),k.FIXED[k.DOT]);self.assertEqual(source.count(dot),1)
        self.assertEqual(source.count(b'reference_qkv_pair_dot16('),2)
        profile=json.loads((ROOT/k.RECIPE).read_bytes())['parameters']
        self.assertEqual(profile['block_sizes'],[1024,512]);self.assertIn(b'const int blocks[2]={1024,512};',source)
        self.assertIn(b'const int k=begin+(issue^1);',source)
        self.assertIn(b'float partial[16]={};',source)
        self.assertIn(b'std::fma(activation[k],bf(row[lane]),partial[lane])',source)
        self.assertIn(b'sums[lane]=block==0?partial[lane]:add(partial[lane],sums[lane]);',source)
        self.assertIn(b'float value=add(sums[lane],bias[column+lane]);',source)
        self.assertIn(b'value=bf(value);',source)
        self.assertLess(source.index(b'value=bf(value);'),source.index(b'std::copy(result.begin(),result.end(),output)'))
        self.assertIn(b'std::fegetround()!=FE_TONEAREST',source);self.assertIn(b'_mm_getcsr()&0xe040u',source)
        self.assertEqual(k.FLAGS,('-shared','-fPIC','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math','-fno-builtin-fmaf'))
        for foreign in (b'torch',b'numpy',b'native_forward',b'RESULT.json',b'matmul',b'dlopen'):
            self.assertNotIn(foreign,source)
        original=k.source
        for name in (k.DOT,k.RECIPE,k.SPEC):
            with self.subTest(source=name),patch.object(k,'source',side_effect=lambda p:
                    original(p)+b'\n' if p==name else original(p)),self.assertRaises(ValueError):k.source_bytes()

    def test_synthetic_library_receipt_metadata_and_identity_postflight(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,value=self.fixture(out)
            with patch.object(k,'source_snapshot',return_value=frozen),patch.object(k,'compiler_identity',return_value=compiler):
                result=k.verify(out)
            self.assertEqual(result['library_path'],str(out/k.LIBRARY))
            self.assertEqual(result['receipt_sha256'],k.sha((out/k.RECEIPT).read_bytes()))
            self.assertEqual(result['source_sha256'],frozen['source_sha256'])
            for field,changed in (('source',dict(frozen,pins_sha256='e'*64)),('compiler',dict(compiler,sha256='e'*64))):
                with self.subTest(field=field),patch.object(k,'source_snapshot',
                        side_effect=[frozen,changed] if field=='source' else [frozen,frozen]), \
                        patch.object(k,'compiler_identity',side_effect=[compiler,changed] if field=='compiler' else [compiler,compiler]), \
                        self.assertRaises(ValueError):k.verify(out)

    def test_receipt_type_flag_hash_and_nonfinite_negatives(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,good=self.fixture(out)
            cases=[]
            for key,bad in (('schema',True),('returncode',False),('numerical_execution',0),
                    ('official_framework_acceptance',0),('elapsed_seconds',True),('elapsed_seconds',float('inf')),
                    ('elapsed_seconds',-1),('elapsed_seconds',31),('total_budget_seconds',30.0),
                    ('library_sha256','0'*64),('pins_sha256','0'*64),('cpp_sha256','0'*64),
                    ('generated_module_sha256','0'*64),('status','PASS')):
                value=deepcopy(good);value[key]=bad;cases.append(value)
            value=deepcopy(good);value['argv'].append('-ffast-math');cases.append(value)
            value=deepcopy(good);value['compiler']['sha256']='0'*64;cases.append(value)
            value=deepcopy(good);value['extra']='CONTROL_ONLY';cases.append(value)
            value=deepcopy(good);del value['source_sha256'];cases.append(value)
            for index,value in enumerate(cases):
                (out/k.RECEIPT).write_text(json.dumps(value))
                with self.subTest(case=index),patch.object(k,'source_snapshot',return_value=frozen), \
                        patch.object(k,'compiler_identity',return_value=compiler),self.assertRaises(ValueError):k.verify(out)

    def test_library_source_binary_symlink_and_bounded_json_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,value=self.fixture(out)
            for kind in ('cpp','elf','hash','symlink','receipt_size','duplicate','nonfinite','overflow'):
                self.fixture(out)
                if kind=='cpp':(out/k.CPP).write_bytes(k.source_bytes()+b'\n')
                elif kind=='elf':(out/k.LIBRARY).write_bytes(b'CONTROL_ONLY'*6)
                elif kind=='hash':
                    raw=bytearray((out/k.LIBRARY).read_bytes());raw[-1]=1;(out/k.LIBRARY).write_bytes(raw)
                elif kind=='symlink':
                    (out/'link').write_bytes((out/k.LIBRARY).read_bytes());(out/k.LIBRARY).unlink();(out/k.LIBRARY).symlink_to(out/'link')
                elif kind=='receipt_size':(out/k.RECEIPT).write_bytes(b' '*131073)
                elif kind=='duplicate':(out/k.RECEIPT).write_bytes(b'{"schema":1,"schema":1}')
                elif kind=='nonfinite':(out/k.RECEIPT).write_bytes(b'{"x":NaN}')
                else:(out/k.RECEIPT).write_bytes(b'{"x":1e999}')
                with self.subTest(kind=kind),patch.object(k,'source_snapshot',return_value=frozen), \
                        patch.object(k,'compiler_identity',return_value=compiler),self.assertRaises(ValueError):k.verify(out)
                if (out/k.LIBRARY).is_symlink():(out/k.LIBRARY).unlink()
        for execute in (False,0,1,None,'yes'):
            with patch.object(k,'source_snapshot') as snapshot,self.subTest(execute=execute),self.assertRaises(ValueError):
                k.build('/CONTROL_ONLY/no-build',execute=execute)
            snapshot.assert_not_called()
        with patch.object(k,'source_snapshot') as snapshot,self.assertRaises(TimeoutError):
            k.build('/CONTROL_ONLY/no-build',execute=True,deadline_ns=time.monotonic_ns()-1)
        snapshot.assert_not_called()

    def test_sleep_only_process_group_timeout_kills_and_reaps(self):
        from . import kernel as k
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);pids=out/'control_pids';processes=[];real_popen=subprocess.Popen
            code=("import os,signal,time;from pathlib import Path;"
                  "signal.signal(signal.SIGTERM,signal.SIG_IGN);child=os.fork();"
                  f"Path({str(pids)!r}).write_text(str(os.getpid())+' '+str(child)) if child else None;"
                  "time.sleep(60)")
            def spawn(*args,**kwargs):
                process=real_popen(*args,**kwargs);processes.append(process);return process
            started=time.monotonic()
            try:
                with patch.object(k,'GRACE',0.05),patch.object(k.subprocess,'Popen',side_effect=spawn):
                    with self.assertRaises((TimeoutError,subprocess.TimeoutExpired)):
                        k._compile([sys.executable,'-c',code],out,time.monotonic_ns()+1_300_000_000)
                self.assertLess(time.monotonic()-started,2.0)
                self.assertTrue(pids.is_file(),'sleep-only child did not initialize')
                self.assertIsNotNone(processes[0].returncode,'direct child was not reaped')
                for pid in map(int,pids.read_text().split()):
                    state=Path('/proc')/str(pid)/'stat'
                    if state.exists():self.assertEqual(state.read_text().split(') ')[1].split()[0],'Z')
            finally:
                for process in processes:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=0.5)


class _ControlArray:
    """Metadata-only ndarray stand-in; contains no floating-point payload."""
    def __init__(self,shape,label,dtype='float32',finite=True,bf=True):
        self.shape=shape;self.ndim=len(shape);self.label=label;self.dtype=dtype
        self.finite=finite;self.bf=bf;self.ctypes=types.SimpleNamespace(data_as=lambda pointer:self)
    @property
    def T(self):return _ControlArray(tuple(reversed(self.shape)),self.label+'.T',self.dtype,self.finite,self.bf)
    def view(self,dtype):return self
    def __and__(self,mask):return self
    def __eq__(self,other):return self
    def all(self):return self.bf


class AdapterRecipeTests(unittest.TestCase):
    def control(self):
        from . import adapter
        receipt=dict(library_path='/CONTROL_ONLY/recipe.so',library_sha256='a'*64,
            source_sha256={adapter.SOURCE:adapter.IMPORTED_SHA256},pins_sha256='c'*64)
        function=Mock(return_value=0);library=types.SimpleNamespace(qkv_pair=function)
        with patch.object(adapter.kernel,'verify',return_value=receipt) as verify, \
                patch.object(adapter.ctypes,'CDLL',return_value=library) as cdll:
            recipe=adapter.Recipe('/CONTROL_ONLY')
        self.assertEqual(verify.call_count,2);cdll.assert_called_once_with(receipt['library_path'])
        return adapter,recipe,receipt,function

    def numpy_stub(self):
        copies=[];module=types.ModuleType('numpy')
        module.ndarray=_ControlArray;module.dtype=lambda x:x
        module.float32='float32';module.uint32='uint32'
        module.isfinite=lambda item:types.SimpleNamespace(all=lambda:item.finite)
        def array(item,*,dtype,order,copy):
            self.assertEqual((dtype,order,copy),('float32','C',True))
            result=_ControlArray(item.shape,item.label+'.copy',dtype,item.finite,item.bf);copies.append((item,result));return result
        module.array=array;module.empty=lambda shape,*,dtype:_ControlArray(shape,'output',dtype)
        return module,copies

    def test_control_canonical_modes_revalidation_and_identity(self):
        adapter,recipe,receipt,function=self.control()
        with patch.object(adapter.kernel,'verify',return_value=receipt):
            for tokens in (16,128):
                self.assertEqual(adapter.validate(recipe,tokens=tokens,carried=False,threads=4),
                    dict(profile=adapter.PROFILE,library_sha256='a'*64,source_sha256=receipt['source_sha256'],pins_sha256='c'*64))
        for tokens,carried,threads in ((True,False,4),(16.0,False,4),(1,False,4),(128,0,4),
                (128,True,4),(16,False,4.0),(16,False,True),(16,False,8)):
            with self.subTest(control=(tokens,carried,threads)),patch.object(adapter.kernel,'verify') as verify:
                with self.assertRaises(ValueError):adapter.validate(recipe,tokens=tokens,carried=carried,threads=threads)
                verify.assert_not_called()
        with self.assertRaises(ValueError):adapter.validate(object(),tokens=16,carried=False,threads=4)
        changed=dict(receipt,source_sha256={adapter.SOURCE:'d'*64})
        with patch.object(adapter.kernel,'verify',return_value=changed),self.assertRaises(ValueError):recipe.identity()
        function.assert_not_called()

    def test_library_rejection_precedes_load_and_postload_drift_rejects(self):
        from . import adapter
        with patch.object(adapter.kernel,'verify',side_effect=ValueError('CONTROL_ONLY rejected receipt')), \
                patch.object(adapter.ctypes,'CDLL') as load,self.assertRaises(ValueError):
            adapter.Recipe('/CONTROL_ONLY')
        load.assert_not_called()
        receipt=dict(library_path='/CONTROL_ONLY/recipe.so',library_sha256='a'*64,
            source_sha256={adapter.SOURCE:adapter.IMPORTED_SHA256},pins_sha256='c'*64)
        with patch.object(adapter.kernel,'verify',side_effect=[receipt,dict(receipt,library_sha256='d'*64)]), \
                patch.object(adapter.ctypes,'CDLL',return_value=types.SimpleNamespace(qkv_pair=Mock())), \
                self.assertRaises(ValueError):adapter.Recipe('/CONTROL_ONLY')

    def test_control_linear_copies_independent_inputs_and_transposes_weight(self):
        adapter,recipe,receipt,function=self.control();numpy,copies=self.numpy_stub()
        inputs=(_ControlArray((1,16,1536),'own_n0'),_ControlArray((256,1536),'checkpoint_weight'),
                _ControlArray((256,),'checkpoint_bias'))
        with patch.dict(sys.modules,{'numpy':numpy}),patch.object(adapter.kernel,'verify',return_value=receipt):
            output=recipe.linear(*inputs,'self_attn.k_proj')
        self.assertEqual(output.shape,(1,16,256));self.assertEqual(len(copies),3)
        args=function.call_args.args
        self.assertEqual([item.label for item in args[2:]],
            ['own_n0.copy','checkpoint_weight.T.copy','checkpoint_bias.copy','output'])
        self.assertEqual(args[:2],(16,256));self.assertEqual(args[3].shape,(1536,256))
        self.assertIs(args[5],output)
        for original,copied in copies:self.assertIsNot(original,copied)

    def test_control_linear_malformed_inputs_codes_and_postflight_reject(self):
        adapter,recipe,receipt,function=self.control();numpy,_=self.numpy_stub()
        def inputs():return [_ControlArray((1,16,1536),'x'),_ControlArray((256,1536),'w'),_ControlArray((256,),'b')]
        for case in ('role','tokens','weight','bias','dtype','finite','bf16'):
            values=inputs();role='self_attn.k_proj'
            if case=='role':role='self_attn.o_proj'
            elif case=='tokens':values[0].shape=(1,1,1536)
            elif case=='weight':values[1].shape=(1536,256)
            elif case=='bias':values[2].shape=(1,256)
            elif case=='dtype':values[0].dtype='float64'
            elif case=='finite':values[1].finite=False
            else:values[2].bf=False
            function.reset_mock()
            with self.subTest(case=case),patch.dict(sys.modules,{'numpy':numpy}), \
                    patch.object(adapter.kernel,'verify',return_value=receipt),self.assertRaises(ValueError):
                recipe.linear(*values,role)
            function.assert_not_called()
        for code in (True,False,0.0,1,-1):
            function.return_value=code
            with self.subTest(code=code),patch.dict(sys.modules,{'numpy':numpy}), \
                    patch.object(adapter.kernel,'verify',return_value=receipt),self.assertRaises(ValueError):
                recipe.linear(*inputs(),'self_attn.k_proj')
        function.return_value=0
        with patch.dict(sys.modules,{'numpy':numpy}),patch.object(adapter.kernel,'verify',
                side_effect=[receipt,dict(receipt,source_sha256={adapter.SOURCE:'d'*64})]),self.assertRaises(ValueError):
            recipe.linear(*inputs(),'self_attn.k_proj')


def run_native_smoke(out):
    """Explicit opt-in synthetic ABI check. Never called by unittest discovery.

    A caller must authorize this build/run and impose an external 30s ceiling.
    It is not the full-native M16 or M128 model gate, which remain mandatory.
    """
    import ctypes
    from . import kernel as k
    started=time.monotonic_ns();deadline=started+30_000_000_000
    def need(ok):
        if not ok:raise ValueError('isolated QKV synthetic check')
        if time.monotonic_ns()>=deadline:raise TimeoutError('isolated QKV deadline')
    receipt=k.build(out,execute=True,deadline_ns=deadline)
    need(k.verify(out)==receipt)
    library=ctypes.CDLL(receipt['library_path']);function=library.qkv_pair
    pointer=ctypes.POINTER(ctypes.c_float)
    function.argtypes=[ctypes.c_int,ctypes.c_int,pointer,pointer,pointer,pointer];function.restype=ctypes.c_int
    rows,columns,depth=16,256,1536;one=0x3f800000
    activation=(ctypes.c_float*(rows*depth))();weights=(ctypes.c_float*(depth*columns))()
    bias=(ctypes.c_float*columns)();output=(ctypes.c_float*(rows*columns))()
    aw=ctypes.cast(activation,ctypes.POINTER(ctypes.c_uint32))
    ww=ctypes.cast(weights,ctypes.POINTER(ctypes.c_uint32))
    bw=ctypes.cast(bias,ctypes.POINTER(ctypes.c_uint32))
    ow=ctypes.cast(output,ctypes.POINTER(ctypes.c_uint32))
    for index in range(rows*depth):aw[index]=one
    cases=[({0:one,2:0xbf800000,3:0x33800000},0),
           ({1022:one,1024:0xbf800000,1025:0x33800000},0),
           ({0:one,1:0x3b800000},0x3b800000),
           ({0:one},0x3b800000),({0:0x3f810000},0x3b800000),
           ({0:0x00010000},0),({0:one,1024:one},one)]
    expected=[0]*columns
    for lane,(terms,offset) in enumerate(cases):
        row=[0]*depth
        for index,word in terms.items():row[index]=word;ww[index*columns+lane]=word
        bw[lane]=offset
        expected[lane]=bf16(rounded(exact(pair_dot([one]*depth,row,[1024,512]))+exact(offset)))
        if lane==0:need(pair_dot([one]*depth,row,[1024,512],pair_first=False)==0x33800000)
        if lane==1:need(pair_dot([one]*depth,row,[512,1024])==0)
        need(True)
    need(expected[:7]==[0,0x33800000,0x3f810000,one,0x3f820000,0x00010000,0x40400000])
    calls=0
    def call(m=rows,n=columns,a=activation,w=weights,b=bias,y=output):
        nonlocal calls
        need(True);code=function(m,n,a,w,b,y);calls+=1;need(True);return code
    need(call()==0)
    need(all(ow[row*columns+column]==word for row in range(rows) for column,word in enumerate(expected)))
    output_sha256=k.sha(ctypes.string_at(ctypes.addressof(output),ctypes.sizeof(output)))
    need(output_sha256==k.sha(b''.join(struct.pack('<I',word) for _ in range(rows) for word in expected)))
    sentinel=0x7fc00001
    def poison():
        for index in range(rows*columns):ow[index]=sentinel
    def unchanged():need(all(ow[index]==sentinel for index in range(rows*columns)))
    poison();need(call(m=1)==1);unchanged()
    poison();need(call(n=255)==1);unchanged()
    saved=ww[0];ww[0]=0x3f800001
    try:poison();need(call()==4);unchanged()
    finally:ww[0]=saved
    poison();need(call(y=activation)==2);unchanged();need(all(aw[index]==one for index in range(rows*depth)))
    fenv_checks=0
    process=ctypes.CDLL(None)
    if hasattr(process,'fegetround') and hasattr(process,'fesetround'):
        process.fegetround.argtypes=[];process.fegetround.restype=ctypes.c_int
        process.fesetround.argtypes=[ctypes.c_int];process.fesetround.restype=ctypes.c_int
        previous=process.fegetround();need(previous==0)
        try:
            need(process.fesetround(0x400)==0)  # x86-64 FE_DOWNWARD, restored below.
            poison();need(call()==3);unchanged();fenv_checks=1
        finally:need(process.fesetround(previous)==0)
    need(k.verify(out)==receipt)
    elapsed=(time.monotonic_ns()-started)/1e9;need(0<=elapsed<30)
    return dict(status='PASS_ISOLATED_QKV_SYNTHETIC_ONLY',rows=rows,columns=columns,depth=depth,
        output_words=rows*columns,adversarial_lanes=len(cases),native_calls=calls,fenv_checks=fenv_checks,
        output_sha256=output_sha256,elapsed_seconds=elapsed,compile_returncode=0,kernel_returncode=0,
        library_sha256=receipt['library_sha256'],cpp_sha256=receipt['cpp_sha256'],pins_sha256=receipt['pins_sha256'],
        source_manifest_sha256=k.sha(k.encoded(receipt['source_sha256'])),
        full_native_m16=False,full_native_m128=False,official_framework_acceptance=False,rtl_execution=False)


if __name__=='__main__':unittest.main()
