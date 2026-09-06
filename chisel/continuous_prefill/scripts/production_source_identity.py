#!/usr/bin/env python3
"""Record/verify explicit source identity; optional offline Scala compilation.

Offline tools contain public compiler dependencies only. No credentials or
account caches are copied. Source files are never patched during a build.
"""
import hashlib,json,subprocess,sys
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
        for d in ['chisel/continuous_prefill/scripts','chisel/continuous_prefill/tests','rtl/matrix','rtl/integration']:
            paths += [p for p in (root/d).rglob('*') if p.is_file() and p.suffix in {'.scala','.sv','.cpp','.py','.sh','.vlt'}]
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
        cmd=['java','-Xmx3G','-XX:ActiveProcessorCount=3','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
             '-Xplugin:'+str(tools/'jars/chisel-plugin_2.13.16-6.7.0.jar'),'-language:reflectiveCalls','-d',str(out/'classes'),'@'+str(out/'main_sources.txt')]
        with (out/'compile.log').open('w') as f:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        (out/'compile.exit').write_text(str(code)+'\n')
        if code:raise SystemExit(code)
    else:raise ValueError('mode')
if __name__=='__main__':main()
