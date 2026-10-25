"""Complete real manifest read/hash chain plus exact metadata boundary negatives.
Only stdlib and AST-extracted file/inventory functions execute. No DUT imports,
NumPy/YAML/native imports, library loads, service objects, jobs or tensor decode.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/'PRIVATE_CONFIG.json').read_text())
SOURCE=Path(CONFIG['project_code_gate_source'])
SUPPORT=ROOT/'code/support.py'
HEADER=Path(CONFIG['source_metadata_integrity_only']['path'])
REPORT={'config_sha256':hashlib.sha256((ROOT/'PRIVATE_CONFIG.json').read_bytes()).hexdigest(),'scope':'PURE_STDLIB_FILE_INVENTORY_NO_DUT_IMPORT_NO_NATIVE_NO_TENSOR_DECODE'}

def need(ok,msg):
    if not ok:raise ValueError(msg)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def extract(path,names,ns):
    tree=ast.parse(Path(path).read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    need({n.name for n in nodes}==set(names),'complete AST selection')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns

def isolation():
    ns=dict(need=need,Path=Path,hashlib=hashlib,json=json,os=os,sys=sys,types=types)
    extract(SUPPORT,['Isolation','qualify_source_metadata','check_manifest'],ns)
    closure=dict(Path=Path,re=re)
    extract(ROOT/'code/runtime_closure.py',['require','verify_graph'],closure)
    ns.update(digest=digest,verify_graph=closure['verify_graph'])
    return ns,ns['Isolation'](CONFIG)

def verifier():
    ns=dict(__name__='_production_existing_project_code_gate',Path=Path,hashlib=hashlib,json=json)
    return extract(SOURCE,['need','digest','verify_sources'],ns)['verify_sources']

class Hook:
    def __init__(self,guard):self.guard=guard;self.active=False;self.opens=[]
    def __call__(self,event,args):
        if self.active:
            if event=='open' and isinstance(args[0],(str,bytes)):self.opens.append(os.fsdecode(args[0]))
            self.guard.audit(event,args)
    def __enter__(self):sys.addaudithook(self);self.active=True;return self
    def __exit__(self,*unused):self.active=False

class ExactMetadataBoundary(unittest.TestCase):
    def test_01_header_is_only_exact_length_prefixed_json(self):
        ns,guard=isolation();source=json.loads(Path(CONFIG['source_manifest']).read_text())
        receipt=ns['qualify_source_metadata'](CONFIG,source)
        raw=HEADER.read_bytes();meta=json.loads(raw[8:]);http=json.loads(HEADER.with_name('model.safetensors.http_receipt.json').read_text())
        self.assertEqual(len(raw),8+int.from_bytes(raw[:8],'little'))
        self.assertEqual(http['body_sha256'],digest(HEADER));self.assertEqual(http['content_length'],len(raw))
        self.assertEqual(http['request_range'],'bytes=0-38535');self.assertEqual(http['content_range'],'bytes 0-38535/3087467144')
        REPORT['header']=dict(receipt,descriptor_count=len(meta)-1,actual_bytes=len(raw),http= http,
            restricted_source_paths=[p for p in source['source_files'] if Path(p).suffix in ('.bin','.f32le','.bf16le','.npz')])

    def test_02_original_denial_exact_path_file_only(self):
        ns=dict(need=need,Path=Path,os=os)
        extract(ROOT.parent/'r2/code/support.py',['Isolation'],ns)
        hook=Hook(ns['Isolation'](CONFIG))
        with hook, self.assertRaisesRegex(ValueError,'reference/weight payload'):
            verifier()(CONFIG['source_root'],CONFIG['source_manifest'],CONFIG['source_manifest_sha256'])
        self.assertEqual(hook.opens[-1],str(HEADER))
        REPORT['old_denial_reproduced_file_only']=dict(path=hook.opens[-1],opens=len(hook.opens),dut_imported=False)

    def test_03_complete_preflight_two_original_verify_passes_postflight(self):
        ns,guard=isolation();ns['check_manifest'](CONFIG)
        fn=verifier();guard.register_source_verifier(fn)
        with Hook(guard) as hook:
            for _ in range(2):
                root,files=fn(CONFIG['source_root'],CONFIG['source_manifest'],CONFIG['source_manifest_sha256'])
                self.assertEqual(len(files),316)
            self.assertEqual(len(guard.metadata_verification_reads),2)
            guard.terminal=True;guard.integrity=True
            ns['check_manifest'](CONFIG)
            guard.integrity=False
        REPORT['complete_read_only_chain']=dict(pinned_files=len(CONFIG['files']),source_files_per_pass=len(files),
            original_verify_passes=2,preflight_pass=True,postflight_pass=True,
            exact_metadata_reads=guard.metadata_verification_reads,source_gate_sha256=digest(SOURCE))

    def test_04_header_generic_reader_wrong_caller_and_clone_denied(self):
        ns,guard=isolation();fn=verifier();guard.register_source_verifier(fn)
        with Hook(guard),self.assertRaisesRegex(ValueError,'reference/weight payload'):
            HEADER.read_bytes()
        # Same AST/name/filename, different actual code object: not the registered verifier.
        clone=verifier()
        with Hook(guard),self.assertRaisesRegex(ValueError,'reference/weight payload'):
            clone(CONFIG['source_root'],CONFIG['source_manifest'],CONFIG['source_manifest_sha256'])
        self.assertEqual(guard.metadata_verification_reads,[])

    def test_05_write_foreign_binary_alias_reference_denied_without_opening(self):
        ns,guard=isolation();guard.register_source_verifier(verifier())
        for path,mode,flags in ((str(HEADER),'w',os.O_WRONLY|os.O_TRUNC),
            (str(HEADER),'r+',os.O_RDWR),(str(HEADER.with_name('forged.header.bin')),'r',os.O_RDONLY),
            (str(HEADER.parent/'..'/'qwen2_1p5b'/HEADER.name),'r',os.O_RDONLY),
            (CONFIG['raw_root']+'/att.f32le','r',os.O_RDONLY),
            (str(HEADER.with_name('weights.bin')),'r',os.O_RDONLY)):
            with self.assertRaises(ValueError):guard.audit('open',(path,mode,flags))
        for spec in CONFIG['inputs'].values():guard.audit('open',(spec['path'],'r',os.O_RDONLY))
        for path in {CONFIG['oracle_harness'],*(s['path'] for s in CONFIG['reference_sources'].values())}-{CONFIG['exact_helper'],CONFIG['buffer_source']}:
            with self.assertRaisesRegex(ValueError,'independent reference'):guard.audit('open',(path,'r',os.O_RDONLY))

    def test_06_unknown_metadata_role_pin_or_extra_payload_rejected(self):
        ns,guard=isolation();source=json.loads(Path(CONFIG['source_manifest']).read_text())
        for field,value in (('path',str(HEADER.with_name('other.bin'))),('bytes',38537),('role','weights'),('tensor_payload_bytes',1)):
            c=copy.deepcopy(CONFIG);c['source_metadata_integrity_only'][field]=value
            with self.assertRaises(ValueError):ns['qualify_source_metadata'](c,source)
        source['source_files']['extra.bin']=dict(bytes=1,sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'unexpected source-tree'):ns['qualify_source_metadata'](CONFIG,source)

    def test_07_production_source_and_driver_unchanged_registration_precedes_imports(self):
        old=ROOT.parent/'r2/code'
        for name in ('component.py','launch.py','reference_capture.py','runtime_observer.py','selective_binding.py','primitives.py'):
            self.assertEqual((ROOT/'code'/name).read_bytes(),(old/name).read_bytes())
        code=(ROOT/'code/binding.py').read_text()
        self.assertLess(code.index('guard.register_source_verifier('),code.index('gate_module.load_runtime('))
        self.assertNotIn('guard.integrity',code)
        # Original load_runtime validates the same complete manifest before and after imports.
        node=next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='load_runtime')
        calls=[n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='verify_sources']
        self.assertEqual(len(calls),2)

if __name__=='__main__':
    program=unittest.main(verbosity=2,exit=False)
    REPORT['passed']=program.result.wasSuccessful();REPORT['tests']=program.result.testsRun
    name='SOURCE_BOUNDARY_OPTIMIZED.json' if sys.flags.optimize else 'SOURCE_BOUNDARY_NORMAL.json'
    with (ROOT/name).open('x') as f:json.dump(REPORT,f,indent=2,sort_keys=True);f.write('\n')
    raise SystemExit(not REPORT['passed'])
