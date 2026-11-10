from pathlib import Path
import json,hashlib,subprocess,time
root=Path.cwd();out=root/'round_20261110T1133/scala';(out/'classes').mkdir(exist_ok=True)
a=json.loads((root/'round_20261110T1033/chisel_execution/HYBRID_DEPENDENCY_AUDIT.json').read_text())['verified'];b=json.loads((root/'round_20261110T1033/chisel_execution/HYBRID_JAR_RECOVERY.json').read_text());jars=[]
for x in a+b:
 p=Path(x['path']);p=p if p.is_absolute() else root/p
 if hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:raise ValueError('jar pin '+str(p))
 if p not in jars:jars.append(p)
old=root/'round_20261110T0133/recovery/sources/hetero_20261109T1934/tail_identity_1934/sources/selected_host';new=root/'round_20261110T1033/chisel_execution/unseeded_v2'
sources=[old/(x+'.scala') for x in ['NativeLibraryPin','NativeEdgeSnapshot','IdmaEdgeSnapshot','RetainedIcgNativeLeaf','IcgNativeBlackBox','CheckedRetainedIdmaNativeLeaf','CheckedIdmaFieldSplitBlackBox']]+list(new.glob('*.scala'))+[root/'round_20261110T0133/recovery/sources/hetero_cloud_recovery_20261107T2134/candidates/chisel_host_boundary_graph_20261105/scala/IdmaSplitLayout.scala']
sources += [p for p in out.glob('*.scala') if p.name != 'RunCurrentHost.scala']
cp=':'.join(map(str,jars));cmd=['java','-Xmx2g','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-d',str(out/'classes')]+list(map(str,sources))
(out/'CLASSPATH.txt').write_text(cp);(out/'PINS.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+jars},indent=2));(out/'COMMAND.json').write_text(json.dumps(cmd));t=time.monotonic()
with (out/'compile.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=180)
(out/'RESULT.json').write_text(json.dumps({'exit':r.returncode,'seconds':time.monotonic()-t,'scope':'Scala transport compile only; no Host or native execution'},indent=2));print(r.returncode)
