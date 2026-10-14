"""Cold stdlib-only guards; no weights, numerical runtime, compiler, network or RTL."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode=True
PACKAGE=Path(__file__).resolve().parents[1]
ROOT=PACKAGE.parents[1]
spec=importlib.util.spec_from_file_location('attention_recipe',PACKAGE/'recipe.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

COLD_PROGRAM = r'''
import builtins, importlib.abc, json, os, pathlib, runpy, sys
recipe = pathlib.Path(sys.argv[1]).resolve()
root = recipe.parents[2]
sources = {root / name for name in json.loads(sys.argv[2])}
stdlib = pathlib.Path(os.__file__).resolve().parent
payload_roots = tuple(root / name for name in ('work', 'raw', 'oracle', 'oracles'))
header = root / 'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
payload_suffixes = {'.bin', '.safetensors', '.bf16', '.bf16le', '.f16', '.f16le',
                    '.f32', '.f32le', '.npy', '.npz', '.pt', '.pth', '.pkl', '.pickle'}
forbidden = {'torch', 'numpy', 'transformers', 'ctypes', 'urllib'}
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in forbidden:
        raise RuntimeError('forbidden cold dependency: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in forbidden:
            raise RuntimeError('forbidden cold dependency: ' + fullname)
sys.meta_path.insert(0, Block())
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn', 'os.posix_spawn')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.startfile', 'os.mkdir', 'os.remove',
            'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.chown',
            'os.truncate', 'os.utime'):
        raise RuntimeError('forbidden cold event: ' + event)
    if event == 'open':
        name, mode, flags = args
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
            raise RuntimeError('forbidden cold write: ' + str(name))
        if not isinstance(name, (str, bytes)):
            raise RuntimeError('forbidden cold file descriptor: ' + str(name))
        path = pathlib.Path(os.path.abspath(os.fsdecode(name)))
        resolved = path.resolve()
        if any(path.is_relative_to(base) or resolved.is_relative_to(base) for base in payload_roots):
            raise RuntimeError('forbidden cold payload root: ' + str(path))
        if (path.suffix.lower() in payload_suffixes or resolved.suffix.lower() in payload_suffixes) and not (
                path == resolved == header):
            raise RuntimeError('forbidden cold payload suffix: ' + str(path))
        source = path == resolved and path in sources
        stdlib_import = resolved.is_relative_to(stdlib) and resolved.suffix in ('.py', '.pyc')
        if not (source or stdlib_import):
            raise RuntimeError('forbidden cold file access: ' + str(path))
sys.addaudithook(audit)
if len(sys.argv) > 3:
    exec(sys.argv[3])
else:
    sys.argv = [str(recipe)]
    runpy.run_path(sys.argv[0], run_name='__main__')
'''

class ColdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.pins=R.load_pins(ROOT)
    def reject(self,fun,*a,**k):
        with self.assertRaises((R.Rejected,FileExistsError)):fun(*a,**k)

    def cold_run(self,root,optimize=(),probe=None):
        sources=[*self.pins['sources'],R.PACKAGE+'/recipe.py',R.PACKAGE+'/pins.json']
        cmd=[sys.executable,'-B','-S',*optimize,'-c',COLD_PROGRAM,
             str(root/R.PACKAGE/'recipe.py'),json.dumps(sources)]
        if probe is not None:cmd.append(probe)
        return subprocess.run(cmd,cwd=root,capture_output=True,text=True)

    def assert_cold(self,root):
        for optimize in ([],['-O']):
            done=self.cold_run(root,optimize)
            self.assertEqual(done.returncode,0,done.stderr)
            value=json.loads(done.stdout);self.assertEqual(value['status'],'NOT_EXECUTED')
            for key in ('torch_imported','numpy_imported','network_used','raw_payload_read','model_executed','rtl_executed','outputs_written'):
                self.assertIs(value[key],False)

    def copy_checkout(self,directory):
        root=Path(directory)/'home/runner/work/repo/repo'
        (root/'.git').mkdir(parents=True)
        for name in (*self.pins['sources'],R.PACKAGE+'/recipe.py',R.PACKAGE+'/pins.json'):
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
        return root

    def test_cold_without_runtime_payload_network_writes(self):self.assert_cold(ROOT)

    def test_cold_github_work_ancestor(self):
        with tempfile.TemporaryDirectory() as name:self.assert_cold(self.copy_checkout(name))

    def test_cold_rejects_unsafe_reads_writes_and_imports(self):
        with tempfile.TemporaryDirectory() as name:
            root=self.copy_checkout(name)
            for rel in ('work/payload.json','oracle/payload.json','raw/payload.json','forged.header.bin'):
                p=root/rel;p.parent.mkdir(exist_ok=True,parents=True);p.write_text('{}')
            (root/'alias.json').symlink_to(root/'work/payload.json')
            probes=["open('work/payload.json').read()","open('oracle/payload.json').read()",
                    "open('raw/payload.json').read()","open('forged.header.bin').read()",
                    "open('alias.json').read()","open('/etc/passwd').read()",
                    "open('new.txt','w')","__import__('torch')","__import__('numpy')",
                    "__import__('ctypes')","__import__('urllib')",
                    "__import__('subprocess').run(['true'])","__import__('os').mkdir('new')"]
            for optimize in ([],['-O']):
                for probe in probes:
                    done=self.cold_run(root,optimize,probe)
                    self.assertNotEqual(done.returncode,0,probe)
                    self.assertIn('forbidden cold',done.stderr,probe)

    def test_source_inventory(self):
        self.assertEqual(R.source_check(ROOT,self.pins),{'pinned_source_files':21,'official_ast_nodes':27,
            'raw_tensors':8,'input_roles':9,'reference_nodes':18,'payload_bytes':7085056})
    def test_exact_type_contract(self):
        for key,value in [('rows',True),('past_tokens',0.0),('groups',12),('old_pass_inherited',1),('direct_gamma',False),('head_dim',64)]:
            p=copy.deepcopy(self.pins);p['contract'][key]=value
            self.reject(R.check_contract,p)
    def test_contract_nodes_exact(self):
        for op in ('missing','extra'):
            p=copy.deepcopy(self.pins)
            if op=='missing':del p['references']['mask']
            else:p['references']['fake']=p['references']['att']
            self.reject(R.check_contract,p)
    def test_ast_identity_and_no_projection(self):
        nodes=R.official_nodes(ROOT,self.pins)
        self.assertEqual([n.lineno for n in nodes[15:]],[184,280,281,283,285,291,300,301,302,304,310,311])
        self.assertNotIn('o_proj','\n'.join(ast.unparse(n) for n in nodes[15:]))
        for key in ('source_sha256','ast_sha256','line_start','line_end','node_type'):
            p=copy.deepcopy(self.pins);p['official_ast_nodes'][18][key]=0 if 'line_' in key else 'invalid'
            self.reject(R.official_nodes,ROOT,p)
    def test_mask_all_positions(self):
        raw=R.mask_bytes();wide=R.P.widen_bf16(raw)
        self.assertEqual(len(raw),512);self.assertEqual(len(wide),1024)
        self.assertTrue(R.verify_mask(raw,self.pins)['all_words_checked'])
        R.verify_mask(wide,self.pins,exported=True)
        for q,k in ((0,0),(0,1),(15,15),(15,0),(7,8),(7,7)):
            bad=bytearray(raw);bad[2*(q*16+k)]^=1
            self.reject(R.verify_mask,bytes(bad),self.pins)
        self.reject(R.verify_mask,raw[:-2],self.pins)
        self.reject(R.verify_mask,bytearray(raw),self.pins)
    def test_mask_drift(self):
        for key,value in [('future_word_u16',65535),('allowed_word_u16',1),('past',1),('dut_observed',True),('native_sha256','0'*64)]:
            p=copy.deepcopy(self.pins);p['mask_contract'][key]=value
            self.reject(R.check_contract,p)
    def test_dtype_geometry_contract(self):
        for name in R.NAMES:
            p=copy.deepcopy(self.pins);p['references'][name]['shape'][0]=True
            self.reject(R.check_contract,p)
            p=copy.deepcopy(self.pins);p['references'][name]['native_dtype']='torch.float64'
            self.reject(R.check_contract,p)
    def test_softmax_no_rewrite(self):
        p=copy.deepcopy(self.pins);p['softmax_observation']['expression_rewritten']=True
        self.reject(R.check_contract,p)
    def test_bootstrap_never_accepted(self):
        p=copy.deepcopy(self.pins);p['reference_freeze']['status']='BOOTSTRAP_UNACCEPTED'
        self.reject(R.require_frozen_references,p)
    def test_fixed_token_layout(self):
        import struct
        shape=[1,2,16,128]
        data=b''.join(struct.pack('<I',n) for n in range(2*16*128))
        out=R.token_bytes('k',data,shape)
        self.assertEqual(out[:512],data[:512]);self.assertEqual(out[512:1024],data[2048*4:2048*4+512])
        self.assertEqual(R.token_bytes('scores',data,shape),data)
        self.reject(R.head_to_token,data,[1,2,128,128])
    def test_path_aliases(self):
        for p in ('/tmp/x','../x','./x','a//b','a/../b','a\\b','',R.OUTPUT_PREFIX+'/a/../b',
                  'work/qwen2_live_qkv_inputs/published7b31_fix_v3/reference',R.OUTPUT_PREFIX+'/a/b/c'):
            self.reject(R.stage_path,ROOT,p)
    def test_existing_out_and_symlink(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);rel=R.OUTPUT_PREFIX+'/test/reference';p=root/rel;p.mkdir(parents=True)
            self.reject(R.fresh_output,root,rel)
            (root/R.OUTPUT_PREFIX/'link').symlink_to(root/R.OUTPUT_PREFIX/'test')
            self.reject(R.stage_path,root,R.OUTPUT_PREFIX+'/link/reference')
    def test_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);rel=R.OUTPUT_PREFIX+'/test/reference'
            self.reject(R.fresh_output,root,rel,[root/R.OUTPUT_PREFIX])
    def test_json_nonfinite_duplicate(self):
        for value in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
            self.reject(R.parse_json,value)
    def test_cli_optin(self):
        cases=[['--action','capture'],['--execute'],['--out',R.OUTPUT_PREFIX+'/test/reference'],
               ['--action','capture','--execute'],['--action','audit','--execute'],
               ['--action','capture','--execute','--out',R.OUTPUT_PREFIX+'/test/reference',
                '--subset','work/qwen2_live_qkv_inputs/published7b31_fix_v3/raw',
                '--inputs','work/qwen2_live_qkv_inputs/published7b31_fix_v3/inputs','--reference',R.OUTPUT_PREFIX+'/test/reference']]
        for args in cases:
            done=subprocess.run([sys.executable,'-B','-S',str(PACKAGE/'recipe.py'),*args],capture_output=True,text=True)
            self.assertEqual(done.returncode,2,(args,done.stdout,done.stderr))
            self.assertEqual(json.loads(done.stderr)['status'],'REJECTED')
    def test_boundaries_detect_drift(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)
            with mock.patch.object(R,'boundary_snapshot',return_value={'changed':True}):
                self.reject(R.finish_boundary,ROOT,self.pins,[],{'before':True},out)
                self.assertTrue((out/'BOUNDARY_AFTER.json').is_file())
    def test_prefix_readonly_identity(self):
        pp=R.prefix_pins(ROOT,self.pins)
        self.assertEqual(self.pins['prefix_references'],R.normalized_prefix_references(pp))
        self.assertEqual(self.pins['official_ast_nodes'][:15],pp['official_ast_nodes'])
        self.assertEqual(self.pins['roles'],pp['roles'])

    def test_runtime_metadata_does_not_require_consumer_environment(self):
        p=copy.deepcopy(self.pins)
        build='TORCH_VERSION=2.10.0 COMMIT_SHA='+p['runtime_requirements']['torch_commit']+' USE_CUDA=0 CPU capability usage: AVX512'
        p['runtime_requirements']['torch_build_sha256']=R.sha(build.encode())
        libs={name:{'path':'/test/'+name,'bytes':1,'sha256':'a'*64} for name in p['runtime_native_files']}
        runtime={**p['runtime_requirements'],'python':sys.version,'torch_build':build,
                 'affinity':sorted(os.sched_getaffinity(0)),'environment':p['capture_environment'],
                 'new_process':True,'historical_runtime_equivalence_claimed':False,
                 'identity_scope':R.RUNTIME_IDENTITY_SCOPE,'native_files':libs}
        with mock.patch.dict(os.environ,{'PYTHONPATH':'/different/consumer','OMP_NUM_THREADS':'1'}), \
             mock.patch.object(R,'python_identity',return_value=libs['python']), \
             mock.patch.object(R,'runtime_files',return_value=libs) as files:
            R.check_runtime(runtime,p)
            files.assert_called_once_with(ROOT,p)
            bad=copy.deepcopy(runtime);bad['environment']['OMP_NUM_THREADS']='1'
            self.reject(R.check_runtime,bad,self.pins)
            changed=copy.deepcopy(libs);changed['torch_C']['sha256']='b'*64
            files.return_value=changed
            self.reject(R.check_runtime,runtime,p)

    def test_m16_geometry_and_raw_capture_source(self):
        expected={'att':[1,16,1536],'mask':[1,1,16,16],
                  **{n:[1,12,16,128] for n in ('repeat_k','repeat_v','pv')},
                  **{n:[1,12,16,16] for n in ('scores','logits','softmax_fp32','prob')}}
        for name,shape in expected.items():self.assertEqual(self.pins['references'][name]['shape'],shape)
        source=(PACKAGE/'capture.py').read_text()
        self.assertIn("tensor('embed_tokens.rows_0_255')[:R.ROWS]",source)
        self.assertIn('q_len=R.ROWS,kv_seq_len=R.ROWS',source)
        self.assertNotIn('m128',source.lower())
        self.assertNotIn('read_reference_payloads',source)
        self.assertNotIn('REFERENCE.json',source)
        self.assertIn('namespace[\'Qwen2RotaryEmbedding\'](128,max_position_embeddings=256',source)
        self.assertEqual(self.pins['reference_crosschecks'],
                         {n:self.pins['prefix_references'][n]['sha256'] for n in ('x','cos','sin')})

if __name__=='__main__':unittest.main()

