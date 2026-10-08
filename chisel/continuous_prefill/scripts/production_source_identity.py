#!/usr/bin/env python3
"""Record/verify explicit source identity; optional offline Scala compilation.

Offline tools contain public compiler dependencies only. No credentials or
account caches are copied. Source files are never patched during a build.
"""
import hashlib,json,os,subprocess,sys
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources(root,hf):
    files=sorted((root/'chisel/continuous_prefill/src/main/scala').rglob('*.scala'))
    files+=sorted((root/'chisel/p0_safety/src/main/scala').rglob('*.scala'))
    files+=[root/'integration/gemmini'/x for x in ('EmitHeteroBF16Fma.scala','EmitHeteroFP32Alu.scala')]
    files+=sorted((hf/'hardfloat/src/main/scala').glob('*.scala'))
    return files

def main():
    mode,root,out,hf=sys.argv[1:5];root,out,hf=map(lambda x:Path(x).resolve(),(root,out,hf))
    if mode=='record':
        paths=[p for p in sources(root,hf) if p.is_relative_to(root) and not p.is_relative_to(hf)]
        scope=os.environ.get('SOURCE_IDENTITY_SCOPE','full')
        if scope not in ('full','legacy_host_gate'):raise ValueError('unknown source identity scope')
        directories=['rtl/matrix','rtl/integration']
        if scope=='full':directories+=['chisel/continuous_prefill/src/test/scala','chisel/continuous_prefill/scripts','chisel/continuous_prefill/tests']
        for d in directories:
            paths += [p for p in (root/d).rglob('*') if p.is_file() and p.suffix in {'.scala','.sv','.cpp','.py','.sh','.vlt','.h','.inc'}]
        if scope=='legacy_host_gate':
            # Bind the actual legacy compiler/driver/fixture/verifier closure.
            # Unrelated Host-V authoring helpers can change without claiming
            # they participated in this long-running numeric regression.
            scripts=['run_real_two_layer_gate.sh','run_host_block_gate.sh','production_source_identity.py',
              'prepare_idma_export.py','prepare_hardfloat.sh','retained_sources.sh','prepare_verilator_runtime.sh',
              'build_host_hierarchy_bounded.py','pack_owner_block_fixture.py','pack_owner_multilayer_fixture.py',
              'pack_owner_bf16_weights.py','verify_host_block_gate.py','verify_real_two_layer.py',
              'audit_owner_block_abi.py','audit_matrix_topology.py','real2_ci.py']
            tests=['host_block_commands.cpp','host_burst_write_step.inc','retained_hierarchy.vlt',
              'matrix4096_hierarchy.vlt','native_weight_hierarchy.vlt','silu_overlap_hierarchy.vlt']
            paths += [root/'chisel/continuous_prefill/scripts'/n for n in scripts]
            paths += [root/'chisel/continuous_prefill/tests'/n for n in tests]
            paths += [root/'src/heteronpu'/n for n in ['abi_validation.py','command.py','descriptor_chain.py',
              'gemmini_descriptor_v2.py','l9_transport_contract.py']]
        (out/'source_scope.json').write_text(json.dumps({'scope':scope,'unrelated_helpers_bound':scope=='full'},indent=2)+'\n')
        (out/'sources.sha256.json').write_text(json.dumps({str(p.relative_to(root)):digest(p) for p in sorted(set(paths))},indent=2)+'\n')
        (out/'hardfloat.sha256.json').write_text(json.dumps({str(p.relative_to(hf)):digest(p) for p in (hf/'hardfloat/src/main/scala').glob('*.scala')},indent=2)+'\n')
    elif mode=='verify':
        for base,name in [(root,'sources.sha256.json'),(hf,'hardfloat.sha256.json')]:
            for path,sha in json.loads((out/name).read_text()).items():
                if digest(base/path)!=sha:raise ValueError('SOURCE_CHANGED: '+path)
        print('SOURCE_IMMUTABILITY_PASS')
    elif mode=='compile':
        tools=Path(sys.argv[5]).resolve()
        jars=[p for p in sorted((tools/'jars').glob('*.jar')) if '_2.12' not in p.name and not p.name.startswith(('scala-library-2.12','scala-reflect-2.12','scala-compiler-2.12'))]
        required=['scala-compiler-2.13.16.jar','scala-library-2.13.16.jar','chisel_2.13-6.7.0.jar','chisel-plugin_2.13.16-6.7.0.jar']
        if any(not (tools/'jars'/n).is_file() for n in required):raise ValueError('incomplete pinned offline compiler')
        cp=':'.join(str(p) for p in jars);(out/'classpath.txt').write_text(cp)
        (out/'compiler_jars.sha256.json').write_text(json.dumps({p.name:digest(p) for p in jars},indent=2)+'\n')
        files=sources(root,hf);(out/'main_sources.txt').write_text(''.join(str(p)+'\n' for p in files))
        (out/'classes').mkdir()
        cmd=['java','-Xmx'+os.environ.get('SCALA_HEAP','3G'),'-XX:ActiveProcessorCount='+os.environ.get('SCALA_CPUS','3'),'-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
             '-Xplugin:'+str(tools/'jars/chisel-plugin_2.13.16-6.7.0.jar'),'-language:reflectiveCalls','-d',str(out/'classes'),'@'+str(out/'main_sources.txt')]
        with (out/'compile.log').open('w') as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        (out/'compile.exit').write_text(str(code)+'\n')
        if code:raise SystemExit(code)
    else:raise ValueError('mode')
if __name__=='__main__':main()
