from pathlib import Path
import subprocess,json,hashlib,time
r=Path('round_20261110T1133/scala').resolve()
# Requires original pinned source closure compiled by round0733 pipeline.
original=Path('round_20261110T0733/qwen2_execution/v4_legacy_pipeline/classes').resolve()
if not original.is_dir(): raise SystemExit('missing original compiled Host source closure; rebuild original pipeline first')
cp=(r/'CLASSPATH.txt').read_text()+':'+str(r/'classes')+':'+str(original)
(r/'HOST_CLASSPATH.txt').write_text(cp)
s=r/'RunCurrentHost.scala';cmd=['java','-Xmx2g','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-d',str(r/'classes'),str(s)]
(r/'HOST_COMPILE_COMMAND.json').write_text(json.dumps(cmd));t=time.monotonic()
with (r/'host_compile.log').open('w') as f: code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=180).returncode
(r/'HOST_COMPILE_RESULT.json').write_text(json.dumps({'exit':code,'seconds':time.monotonic()-t,'source_sha256':hashlib.sha256(s.read_bytes()).hexdigest(),'scope':'Host runner compile only; no execution'},indent=2))
raise SystemExit(code)
