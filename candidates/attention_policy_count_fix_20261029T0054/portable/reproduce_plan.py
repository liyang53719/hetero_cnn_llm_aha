"""Validate production extraction + exact dependencies; PRINT commands, never execute them."""
import argparse,hashlib,json,os
from pathlib import Path
D=Path(__file__).resolve().parent
PRODUCTION='8cea5e8863e47ca14978871d23b7f80639e43ae3192c3e6c0ccf372b1c73a20f'
TEST='6b595ef567fc8c9bec0072426081fb616b0988a6cbdf1719de598773e29692b7'

def need(x,m):
 if not x:raise ValueError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def extraction(source):
 lines=[]
 for start in ['val isMatrix=','val isSoftmax=','val attentionPolicySlot=','val attentionContextSlot=','val countPolicy=','val indices=','val used=','attentionDistinct:=']:
  region=source if start in ['val isMatrix=','val isSoftmax=','val attentionPolicySlot=','val attentionContextSlot='] else source[source.index('val countPolicy='):source.index('val trusted=attentionCold')]
  found=[l.strip() for l in region.splitlines() if l.strip().startswith(start)];need(len(found)==1,'unique production expression '+start);lines+=found
 return lines
p=argparse.ArgumentParser();p.add_argument('--production',type=Path,required=True);p.add_argument('--toolchain-pins',type=Path);p.add_argument('--jar-root',type=Path);p.add_argument('--java',type=Path);p.add_argument('--output',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
need(sha(a.production)==PRODUCTION,'exact fixed production source');test=D/'AttentionPolicyCountExpressionTest.scala';need(sha(test)==TEST,'exact actually tested micro source')
lines=extraction(a.production.read_text());text=test.read_text();need(('\n  '.join(lines)) in text,'micro must contain contiguous verbatim production extraction')
result={'status':'PASS_SOURCE_EXTRACTION_ONLY','production_sha256':PRODUCTION,'test_sha256':TEST,'lines':lines,'no_execution':True}
if not a.check_only:
 need(all(x is not None for x in [a.toolchain_pins,a.jar_root,a.java,a.output]),'all runtime paths explicitly required')
 contract=json.loads((D/'DEPENDENCY_CONTRACT.json').read_text());need(sha(a.toolchain_pins)==contract['toolchain_pins_sha256'],'published exact toolchain manifest')
 jars=json.loads(a.toolchain_pins.read_text())['jars'];need(len(jars)==107,'106 classpath jars +1 plugin')
 paths=[];plugins=[]
 for r in jars:
  rel=Path(r['maven_path']);need(not rel.is_absolute() and '..' not in rel.parts,'relative Maven path')
  q=a.jar_root/rel;need(q.is_file() and q.stat().st_size==r['bytes'] and sha(q)==r['sha256'],'exact dependency '+str(rel))
  if r['role']=='classpath':paths.append(str(q.resolve()))
  else:plugins.append((r['role'],str(q.resolve())))
 need(len(paths)==106 and len(plugins)==1,'exact dependency roles')
 cp=os.pathsep.join(paths);classes=a.output.resolve()/'classes';need(not a.output.exists(),'fresh output required');java=str(a.java.resolve())
 result.update({'java_version_required':'21.0.12.1 (check java -version and environment receipt separately)','prepare_directories':[str(classes),str(a.output.resolve()/'micro')], 'compile_argv':[java,'-XX:ActiveProcessorCount=1','-Xmx2g','-Xss4m','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugins[0][1],'-language:reflectiveCalls','-d',str(classes),str(test)],'micro_cwd':str(a.output.resolve()/'micro'),'micro_argv':[java,'-XX:ActiveProcessorCount=1','-Xmx2g','-cp',str(classes)+os.pathsep+cp,'heteronpu.continuous.AttentionPolicyCountExpressionTest'],'limits_required':{'wall_seconds':300,'rss_bytes':3221225472,'minimum_available_memory_bytes':5368709120,'one_heavy_job_at_a_time':True},'note':'Run under existing reviewed supervisor; inspect fresh compiled classes before micro. No full controller/full block/RTL PASS.'})
print(json.dumps(result,indent=2))
