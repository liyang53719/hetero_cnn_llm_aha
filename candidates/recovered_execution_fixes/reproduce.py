#!/usr/bin/env python3
"""Generate metadata locally and test TEMP transport/predicate fixes, never DUT."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(work):
 work.mkdir(parents=True,exist_ok=False)
 scripts=REPO/'chisel/continuous_prefill/scripts'
 pack=module('pack_fixture',scripts/'pack_owner_block_fixture.py')
 convert=module('native_fixture',scripts/'pack_owner_bf16_weights.py')
 old=work.parent/'programs/profile0'
 pack.pack(dict(H=1536,F=8960,HEADS=12,KVHEADS=2,HD=128,MAX_TOKENS=1024),128,old)
 native=work/'native_candidate';convert.convert(old,native)
 require(sha(native/'manifest.json')=='c5fcd45a4cee53b084a0915753186b06540342bb0620a783f528fefb83b9b561','native manifest pin')
 finding=json.loads((HERE/'QWEN2_FINDING.json').read_text())
 a=(old/'host_descriptors.bin').read_bytes();b=(native/'host_descriptors.bin').read_bytes()
 require(hashlib.sha256(a).hexdigest()==finding['old_descriptor'],'old pin')
 require(hashlib.sha256(b).hexdigest()==finding['native_descriptor'],'native pin')
 require((old/'host_commands.bin').read_bytes()==(native/'host_commands.bin').read_bytes(),'commands changed')
 require(sum(x!=y for x,y in zip(a,b))==7,'not exactly seven changed bytes')
 shutil.copytree(HERE/'provider_candidate',work/'provider_candidate',ignore=shutil.ignore_patterns('__pycache__'))
 env=dict(os.environ,FIXTURE_WORK=str(work),PYTHONDONTWRITEBYTECODE='1')
 for test in ('test_candidate.py','test_independent_provider_candidate.py','test_counterexample.py'):
  subprocess.run([sys.executable,str(HERE/test)],env=env,check=True)
 # Exact source patch reconstruction: no compilation/elaboration is performed.
 original=REPO/'candidates/host_runtime_moe/source/TransposedDenseOwner.scala'
 require(sha(original)=='485af859775994bd1b130aeb6e30b4c331c5a4fc6985e3ea09c1c4170efc8eb3','Down original pin')
 text=original.read_text();needle='    val prefixAliases=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd)).map{case(base,end)=>'
 before,down=text.split('class TransposedDenseDownOwner(',1)
 require(down.count('\n'+needle)==1,'normal Down predicate count')
 replacement='    // No prefix read/write exists for single-K-chunk jobs; phase operands may\n    // occupy region3 then. Multi-chunk jobs retain the exact original alias fence.\n    val prefixAliases=(j.k>w.splitK) && Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd)).map{case(base,end)=>'
 candidate=work/'TransposedDenseOwner.scala';candidate.write_text(before+'class TransposedDenseDownOwner('+down.replace('\n'+needle,'\n'+replacement))
 require(sha(candidate)=='961f4e650b499fc1f15918d2e0f6aa51b4905431ba35ba681a609c98b42c5d14','Down candidate pin')
 print('PASS metadata/transport/predicate reconstruction ONLY; compile, Chisel numerics and RTL NOT RUN; five full blocks 0/5')
if __name__=='__main__':
 require(__debug__, 'Run without -O: evidence tests use assert')
 with tempfile.TemporaryDirectory(prefix='hetero-fix-repro-') as tmp:run(Path(tmp)/'audit')
