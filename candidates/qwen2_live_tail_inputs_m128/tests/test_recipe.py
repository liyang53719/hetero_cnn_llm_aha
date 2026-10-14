"""Bounded stdlib tests; synthetic words only, never production payloads."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('tail_recipe',PACKAGE/'recipe.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
SCRATCH = ROOT/'work/qwen2_live_tail_inputs_m128/cold'
COLD = r'''
import builtins, importlib.abc, json, os, pathlib, runpy, sys
recipe=pathlib.Path(sys.argv[1]).resolve();root=recipe.parents[2]
allowed={root/p for p in json.loads(sys.argv[2])}
stdlib=pathlib.Path(os.__file__).resolve().parent
header=root/'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
blocked={'numpy','torch','transformers','ctypes','urllib','socket'}
original=builtins.__import__
def guarded(name,*a,**k):
 if name.split('.')[0] in blocked:raise RuntimeError('forbidden import '+name)
 return original(name,*a,**k)
builtins.__import__=guarded
def audit(event,args):
 if event.startswith(('socket.','subprocess.','os.exec','os.spawn','os.posix_spawn')) or event in ('os.mkdir','os.remove','os.rmdir','os.rename','os.link','os.symlink','os.chmod','os.chown','os.truncate','os.utime','os.system','os.fork'):
  raise RuntimeError('forbidden side effect '+event)
 if event=='open':
  name,mode,flags=args
  if ((isinstance(mode,str) and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):raise RuntimeError('forbidden write')
  if not isinstance(name,(str,bytes)):raise RuntimeError('forbidden descriptor')
  p=pathlib.Path(os.path.abspath(os.fsdecode(name)));resolved=p.resolve()
  if any(p.is_relative_to(root/q) or resolved.is_relative_to(root/q) for q in ('work','raw','oracle','oracles')):raise RuntimeError('forbidden data')
  if (p.suffix.lower() in ('.bin','.f32le','.bf16','.npy','.npz','.safetensors') or resolved.suffix.lower() in ('.bin','.f32le','.bf16','.npy','.npz','.safetensors')) and not p==resolved==header:raise RuntimeError('forbidden payload')
  if not (p==resolved and p in allowed or resolved.is_relative_to(stdlib) and resolved.suffix in ('.py','.pyc')):raise RuntimeError('forbidden file '+str(p))
sys.addaudithook(audit)
if len(sys.argv)>3:exec(sys.argv[3])
else:
 sys.argv=[str(recipe)];runpy.run_path(str(recipe),run_name='__main__')
'''


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = R.load_pins(ROOT)
        SCRATCH.mkdir(parents=True,exist_ok=True)
        cls.widen,cls.transpose = staticmethod(R.conversion_functions(ROOT,cls.pins)[0]),staticmethod(R.conversion_functions(ROOT,cls.pins)[1])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def clone(self):
        for relative in list(self.pins['sources'])+[R.PACKAGE+'/recipe.py',R.PACKAGE+'/pins.json']:
            target = self.root/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/relative).read_bytes())
        return self.root

    def reject(self, function, *args, **kwargs):
        with self.assertRaises((ValueError,OSError,KeyError,TypeError)):
            function(*args,**kwargs)

    def cold(self, root, probe=None):
        names = list(self.pins['sources'])+[R.PACKAGE+'/recipe.py',R.PACKAGE+'/pins.json']
        cmd = [sys.executable,'-B','-S',*(['-O'] if sys.flags.optimize else []),'-c',COLD,
               str(root/R.PACKAGE/'recipe.py'),json.dumps(names)]
        if probe is not None:
            cmd.append(probe)
        return subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=15)

    def test_default_audited_no_data_or_side_effects(self):
        result = self.cold(ROOT)
        self.assertEqual(result.returncode,0,result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc['status'],'NOT_EXECUTED')
        for key in ('raw_payload_read','outputs_written','torch_imported','numpy_imported','network_used','model_executed','rtl_executed'):
            self.assertIs(doc[key],False)

    def test_source_only_checkout_without_work(self):
        self.clone()
        self.assertFalse((self.root/'work').exists())
        result = self.cold(self.root)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'work').exists())

    def test_cold_guard_rejects_reads_writes_imports_and_exec(self):
        self.clone()
        for probe in ("open('work/data.json').read()","open('oracle/data.json').read()",
                      "open('weight.bin','rb').read()","open('new.txt','w')","os.mkdir('new')",
                      "import numpy","import torch","import ctypes","import urllib",
                      "import subprocess; subprocess.run(['true'])","os.system('true')"):
            with self.subTest(probe=probe):
                self.assertNotEqual(self.cold(self.root,probe).returncode,0)

    def test_pin_file_byte_mutation(self):
        self.clone();path=self.root/R.PACKAGE/'pins.json';data=bytearray(path.read_bytes());data[20]^=1;path.write_bytes(data)
        self.reject(R.load_pins,self.root)

    def test_each_dependency_byte_mutation(self):
        self.clone()
        for relative in self.pins['sources']:
            with self.subTest(source=relative):
                path=self.root/relative;original=path.read_bytes();data=bytearray(original);data[len(data)//2]^=1;path.write_bytes(data)
                self.reject(R.source_check,self.root,self.pins)
                path.write_bytes(original)

    def test_all_physical_metadata_rejected_if_mutated(self):
        cases=0
        for role,record in self.pins['roles'].items():
            for key,value in record.items():
                p=copy.deepcopy(self.pins)
                p['roles'][role][key] = (not value if type(value) is bool else value+1 if type(value) is int else
                    value+'bad' if type(value) is str else [*value[:-1],value[-1]+1])
                with self.subTest(role=role,key=key):self.reject(R.source_check,ROOT,p)
                cases+=1
        self.assertEqual(cases,95)

    def test_bool_dimension_and_integer_scope_rejected(self):
        for section,key in (('roles','bytes'),('roles','descriptor_dtype'),('boundaries','numerical_model_executed')):
            p=copy.deepcopy(self.pins)
            if section=='roles':p[section]['gamma1'][key]=True
            else:p[section][key]=0
            self.reject(R.check_contract,p)

    def test_raw_pin_header_range_and_segment_mutations(self):
        for key in ('name','local_name','dtype','shape','source_shape','source_data_offsets','start','end','bytes','sha256'):
            p=copy.deepcopy(self.pins);v=p['tensors'][0][key]
            p['tensors'][0][key]=v+1 if type(v) is int else v+'bad' if type(v) is str else [v[0]+1,*v[1:]]
            self.reject(R.source_check,ROOT,p)
        for key in ('start','end','bytes','sha256'):
            p=copy.deepcopy(self.pins);v=p['tensors'][2]['segments'][0][key]
            p['tensors'][2]['segments'][0][key]=v+1 if type(v) is int else '0'*64
            self.reject(R.source_check,ROOT,p)

    def test_ast_identity_mutations(self):
        for location in ('conversion_ast','layout_ast'):
            p=copy.deepcopy(self.pins)
            if location=='conversion_ast':p[location]['transpose_words']['ast_sha256']='0'*64
            else:p[location]['prefix_nodes'][0]['ast_sha256']='0'*64
            self.reject(R.source_check,ROOT,p)

    def test_python_version_drift_rejected_before_ast(self):
        with mock.patch.object(R.sys,'version_info',(3,11,99)):
            self.reject(R.source_check,ROOT,self.pins)

    def test_source_to_physical_layout(self):
        layout=R.public_layout(ROOT,self.pins)
        self.assertEqual(set(layout),set(R.ROLES))
        for role in R.ROLES:
            for key,value in layout[role].items():self.assertEqual(value,self.pins['roles'][role][key])
        self.assertEqual(layout['gamma1']['shape'],[1,1536])
        self.assertEqual(sum(r['bytes'] for r in self.pins['roles'].values()),87300096)

    def test_transpose_nonsquare_and_square_not_identity(self):
        for rows,columns in ((1,3),(3,1),(2,3),(3,2),(3,3)):
            raw=struct.pack('<'+'H'*(rows*columns),*range(rows*columns))
            data=self.transpose(raw,rows,columns)
            expected=struct.pack('<'+'H'*(rows*columns),*(r*columns+c for c in range(columns) for r in range(rows)))
            self.assertEqual(data,expected)
            spec={'bytes':len(raw),'widened':False,'source_shape':[rows,columns]}
            R.verify_correspondence(raw,data,spec)
            if rows>1 and columns>1:self.assertNotEqual(data,raw)

    def test_transpose_rejects_bad_dimensions_and_length(self):
        for rows,columns,raw in ((True,2,b'\0'*4),(2,True,b'\0'*4),(0,2,b''),(-1,2,b''),(1.0,2,b'\0'*4),(2,3,b'\0'*11),(2,3,b'\0'*13)):
            self.reject(self.transpose,raw,rows,columns)

    def test_widen_preserves_every_test_word_and_signed_zero(self):
        words=(0,0x8000,1,0x3f80,0xbf80,0x7f7f,0xffff)
        raw=struct.pack('<7H',*words);data=self.widen(raw)
        self.assertEqual(data,struct.pack('<7I',*(w<<16 for w in words)))
        R.verify_correspondence(raw,data,{'bytes':28,'widened':True})
        self.reject(self.widen,b'\0')

    def test_correspondence_rejects_each_output_byte_mutation(self):
        raw=struct.pack('<6H',0x3f80,0x4000,0x4040,0x4080,0x40a0,0x40c0)
        for data,spec in ((self.transpose(raw,2,3),{'bytes':12,'widened':False,'source_shape':[2,3]}),
                          (self.widen(raw),{'bytes':24,'widened':True})):
            for i in range(len(data)):
                mutation=bytearray(data);mutation[i]^=1
                self.reject(R.verify_correspondence,raw,bytes(mutation),spec)

    def test_raw_whole_and_segment_hash_mutations(self):
        raw=struct.pack('<6H',*range(6));t={'role':'synthetic','start':10,'bytes':12,'sha256':R.sha(raw),
            'segments':[{'start':10,'end':15,'bytes':6,'sha256':R.sha(raw[:6])},
                        {'start':16,'end':21,'bytes':6,'sha256':R.sha(raw[6:])}]}
        R.validate_raw_bytes(raw,t)
        for i in range(len(raw)):
            b=bytearray(raw);b[i]^=1;self.reject(R.validate_raw_bytes,bytes(b),t)
        for raw2 in (raw[:-1],raw+b'\0'):self.reject(R.validate_raw_bytes,raw2,t)
        bad=copy.deepcopy(t);bad['segments'][1]['sha256']='0'*64
        self.reject(R.validate_raw_bytes,raw,bad)

    def test_http_receipts_type_and_field_mutations(self):
        s=self.pins['tensors'][0]['segments'][0]
        r={'requested_url':self.pins['shard']['url'],'request_range':f"bytes={s['start']}-{s['end']}",
           'status':206,'content_range':f"bytes {s['start']}-{s['end']}/3087467144",'bytes':s['bytes'],
           'sha256':s['sha256'],'acquired_at':'2026-10-14T10:53:57+00:00'}
        R.verify_http(r,s,self.pins)
        for key,value in r.items():
            bad=dict(r);bad[key]=True if type(value) is int else 'bad'
            self.reject(R.verify_http,bad,s,self.pins)
        for bad in ({**r,'extra':0},{k:v for k,v in r.items() if k!='status'},
                    {**r,'status':200},{**r,'acquired_at':'2026-10-14T10:00:00'}):
            self.reject(R.verify_http,bad,s,self.pins)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":-Infinity}'):
            self.reject(R.parse,raw)

    def test_strict_paths(self):
        for value in ('','/tmp/new','work/../new','work//new','./work/new','work\\new',
            R.OUTPUT_PREFIX+'/one',R.OUTPUT_PREFIX+'/one/two/three',R.OUTPUT_PREFIX+'/one/.two',
            'work/other/one/two'):
            self.reject(R.stage_path,self.root,value)
        path=R.stage_path(self.root,R.OUTPUT_PREFIX+'/run01/inputs')
        self.assertEqual(path,self.root/R.OUTPUT_PREFIX/'run01/inputs')

    def test_symlink_file_and_ancestor_rejected(self):
        (self.root/'other').mkdir();(self.root/'work').symlink_to(self.root/'other',target_is_directory=True)
        self.reject(R.stage_path,self.root,R.OUTPUT_PREFIX+'/run/inputs')
        (self.root/'dangling').symlink_to(self.root/'missing')
        self.reject(R.safe_path,self.root,'dangling/data')

    def test_existing_output_and_overlap_rejected(self):
        relative=R.OUTPUT_PREFIX+'/run/inputs';p=self.root/relative;p.mkdir(parents=True)
        self.reject(R.fresh_output,self.root,relative)
        self.reject(R.fresh_output,self.root,R.OUTPUT_PREFIX+'/run/other',[p.parent])

    def test_exclusive_file_write(self):
        p=self.root/'file';R.write_new(p,b'a');self.reject(R.write_new,p,b'b')
        self.assertEqual(p.read_bytes(),b'a')

    def test_cli_permission_precedes_source_and_data_read(self):
        for argv in (['--action','materialize'],['--action','audit','--execute'],
                     ['--execute'],['--out',R.OUTPUT_PREFIX+'/run/inputs'],
                     ['--action','materialize','--execute','--out',R.OUTPUT_PREFIX+'/run/inputs','--inputs','x']):
            with mock.patch.object(R,'load_pins',side_effect=AssertionError('must reject first')):
                self.reject(R.main,argv)

    def test_bad_metadata_fails_before_output_creation(self):
        p=copy.deepcopy(self.pins);p['roles']['wo']['shape']=[1,1]
        target=R.OUTPUT_PREFIX+'/run/inputs'
        self.reject(R.materialize,self.root,p,target)
        self.assertFalse((self.root/'work').exists())

    def test_bad_raw_fails_before_converter_or_output(self):
        target=R.OUTPUT_PREFIX+'/run/inputs'
        with mock.patch.object(R,'source_check'),mock.patch.object(R,'snapshot',return_value={}),\
             mock.patch.object(R,'read_raw',side_effect=R.Rejected('synthetic bad raw')),\
             mock.patch.object(R,'conversion_functions',side_effect=AssertionError('conversion prohibited')):
            self.reject(R.materialize,self.root,self.pins,target)
        self.assertFalse((self.root/'work').exists())

    def test_no_nonstdlib_import_in_recipe(self):
        tree=ast.parse((PACKAGE/'recipe.py').read_text())
        names=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):names.extend(a.name.split('.')[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom):names.append(node.module.split('.')[0])
        self.assertTrue(set(names)<=sys.stdlib_module_names|{'__future__'})
        self.assertNotIn('assert',[type(n).__name__.lower() for n in ast.walk(tree)])


if __name__ == '__main__':
    unittest.main()
