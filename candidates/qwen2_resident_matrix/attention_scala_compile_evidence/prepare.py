"""Source/JAR verification and command preparation only; never launches Java."""
import hashlib,json,tempfile
from pathlib import Path
from candidates.qwen2_resident_matrix.raw_kv_parent import prepare_unit as unit
from candidates.qwen2_resident_matrix.attention_packed_stream import prepare as stream
from candidates.qwen2_resident_matrix.attention_raw_scratch import prepare as scratch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SCALA=stream.SCALA
HEADER='package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\nimport chisel3.experimental.{IntParam,Param}\n'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,why):
 if not ok:raise ValueError(why)
def evidence():return json.loads((HERE/'EVIDENCE.json').read_bytes())
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 for name,h in p['own'].items():need(sha(HERE/name)==h,'evidence source drift')
 for name,h in p['sources'].items():need(sha(ROOT/name)==h,'construction source drift')
 return p

def declaration(text,name):
 marker='class '+name;need(text.count(marker)==1,'unique original declaration')
 start=text.index(marker);i=text.index('{',start)+1;depth=1
 while depth:
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[start:i]

def compose(destination,*,original_root):
 check();e=evidence();out=Path(destination);need(not out.exists(),'fresh destination required')
 base=Path(original_root)
 wide=base/SCALA/'WideMatrix.scala';controller=base/'candidates/qwen2_resident_matrix/MatrixAccumulatorSeedController.scala'
 need(sha(wide)==e['wide_source_sha256'] and sha(controller)==e['controller_source_sha256'],'original ABI/controller identity')
 unit.prepare(out)
 with tempfile.TemporaryDirectory() as temporary:
  st=Path(temporary)/'stream';stream.compose(st);sc=Path(temporary)/'scratch';scratch.compose(sc)
  need((out/'BurstProtocol.scala').read_bytes()==(st/(SCALA+'BurstProtocol.scala')).read_bytes(),'shared protocol identity')
  for name in scratch.parent.TARGETS:(out/Path(name).name).write_bytes((sc/name).read_bytes())
  for name in ('MatrixPipeline.scala','PackedAttentionStreamClient.scala'):(out/name).write_bytes((st/(SCALA+name)).read_bytes())
  retained=(st/(SCALA+'RetainedMatrix.scala')).read_text()
  (out/'RetainedAbi.scala').write_text(HEADER+'\n'.join(declaration(retained,n) for n in ('RetainedMatrixEndpoint','RetainedMatrixClockGate'))+'\n')
 (out/'WideAbi.scala').write_text(HEADER+'\n'.join(declaration(wide.read_text(),n) for n in ('WideMatrixStep','WideMatrixResult'))+'\n')
 (out/controller.name).write_bytes(controller.read_bytes())
 actual={p.name:sha(p) for p in sorted(out.glob('*.scala'))}
 need(actual==e['source_sha256'],'exact eighteen-source identity')
 return actual

def dependencies(lock,cache):
 e=evidence();need(sha(lock)==e['dependencies']['lock_sha256'],'official lock identity')
 data=json.loads(Path(lock).read_bytes())
 selected={p:h for p,h in data['artifacts'].items() if p.endswith('.jar') and '_2.12' not in p and '/2.12.' not in p and not p.startswith('org/scala-sbt/')}
 need(data['repository']=='https://repo.maven.apache.org/maven2/' and selected==e['dependencies']['jars'] and len(selected)==87,'official dependency inventory')
 for name,h in selected.items():need(sha(Path(cache)/name)==h,'JAR identity')
 return ':'.join(str(Path(cache).resolve()/n) for n in sorted(selected))

def command(java,classpath,cache,source,classes):
 e=evidence();need(sha(java)==e['java_sha256'],'Java identity')
 need({p.name:sha(p) for p in Path(source).glob('*.scala')}==e['source_sha256'],'compiler source identity')
 return [str(Path(java).resolve()),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',classpath,'scala.tools.nsc.Main','-classpath',classpath,'-Xplugin:'+str(Path(cache).resolve()/e['plugin']),'-language:reflectiveCalls','-d',str(classes)]+[str(p) for p in sorted(Path(source).glob('*.scala'))]
