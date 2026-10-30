"""Read-only audit of the exact future run's extracted metadata. Never repins."""
import argparse,hashlib,importlib.util,json,pathlib,re,sys
D=pathlib.Path(__file__).resolve().parent
SRC=D.parents[1]
OLD_CANONICAL=SRC.parent/'ci_frontend_materialization_r2_20261029/fixed-canonical-baseline.tsv'
def need(x,m):
 if not x:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def load_module():
 p=SRC/'descriptor_metadata.py';need(sha(p.read_bytes())=='f53bff15269a083db8b654f3e3ac9a855e9ea6185deee484abcbd37887fcf725','reviewed checker pin')
 spec=importlib.util.spec_from_file_location('reviewed_descriptor',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def rows(b):
 lines=b.decode().splitlines();need(lines[0]=='TEMP_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1','canonical schema')
 head={};modules=[]
 for line in lines[1:]:
  f=line.split('\t')
  if len(f)==3 and f[0]=='module':modules.append((f[1],f[2]))
  else:need(len(f)==2 and f[0] not in head,'unique canonical header');head[f[0]]=f[1]
 need(len(dict(modules))==len(modules),'unique modules');return head,modules
def audit(root,summary_path):
 m=load_module();root=pathlib.Path(root);need(root.is_dir() and not root.is_symlink(),'regular metadata root')
 need({p.name for p in root.iterdir()}=={'observed-canonical.tsv','observed-details.json','provenance.json'},'exact metadata files only')
 data={n:m.read(root/n,cap) for n,cap in {**m.FILES,'provenance.json':65536}.items()};need(sum(map(len,data.values()))<=512<<10,'aggregate metadata bound')
 summary=m.obj(m.read(pathlib.Path(summary_path),65536));prov=m.obj(data['provenance.json']);detail=m.obj(data['observed-details.json'])
 identity={'source_commit':'97555642bee1b7a40047db8677d28f1f89185bce','launch_commit':'ec198c27364fc537da06d6430bf27607d9865596','launch_manifest_blob_sha':'ce88cb7cefdb7e71d937fcabb342d5c02e031562','run_id':41114764250}
 need(all(summary.get(k)==v and prov.get(k)==v for k,v in identity.items()),'exact actual source/launch/blob/run identity')
 need(set(prov)=={'schema','qualification','descriptor',*identity},'provenance exact schema')
 need(prov['schema']=='OBSERVED_DESCRIPTOR_PROVENANCE_V1' and prov['qualification']=='OBSERVED_UNREVIEWED','unreviewed provenance')
 flags=('numerical_pass','canonical_pass','target_host_qualified','sv_generated','generated_abi_qualification','physical_resource_or_qor_qualification','block_numerical_pass')
 need(all(summary.get(k)is False for k in flags),'no imported acceptance claims')
 need(summary.get('status')=='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY','complete IR plus descriptor required')
 stages=('jdk','compile_tools','jars','verilator_bytes','runtime_identity','compile155','helper_compile','original_ir','descriptor')
 need(tuple(s.get('name')for s in summary.get('stages',[]))==stages,'all nine stages ordered')
 for s in summary['stages']:
  need(s.get('native_exit')==0 and s.get('complete')is True and s.get('error_count')==0,'stage complete native zero')
  a=s.get('admission',{});need(a.get('status')=='ADMITTED' and a.get('census_complete')is True and a.get('execute_called')is True,'actual admitted stage')
 r=m.project_receipt(summary['descriptor']);need(r==m.project_receipt(prov['descriptor']),'receipt matches provenance')
 contract=m.obj(m.read(SRC/'PORT_CONTRACT.json',65536));counts=m.validate(data['observed-canonical.tsv'],detail,contract)
 need(r['counts']==counts,'recomputed descriptor counts')
 need(r['files']=={n:m.pin(data[n])for n in m.FILES},'metadata actual byte/hash identity')
 need(all(r['bound_inputs'][n]==summary['artifacts'][n] for n in m.INPUTS),'bound actual original helper artifacts')
 base=json.loads((D/'BASELINE_AND_CANDIDATE_PINS.json').read_text());oldbytes=OLD_CANONICAL.read_bytes();need(sha(oldbytes)==base['old_manifest']['sha256'],'old accepted canonical pin')
 oldhead,oldrows=rows(oldbytes);newhead,newrows=rows(data['observed-canonical.tsv']);old=dict(oldrows);new=dict(newrows)
 added=[n for n,_ in newrows if n not in old];removed=[n for n,_ in oldrows if n not in new];changed=[{'module':n,'old_sha256':old[n],'new_sha256':h}for n,h in newrows if n in old and old[n]!=h]
 expected=set(base['expected_changed_module_names']);changednames={r['module']for r in changed}
 ann=base['candidate_r2'];annotation_exact=(summary['artifacts']['high-annotations.json']=={'bytes':ann['bytes'],'sha256':ann['raw_sha256']} and detail['ordered_annotations_sha256']==ann['ordered_annotation_sha256'] and (detail['annotation_count'],detail['retained_annotation_count'],detail['target_dir_annotation_count'])==(9022,9021,1))
 return {'scope':'ACTUAL_DESCRIPTOR_DIFFERENCE_REPORT_NOT_ACCEPTANCE',**identity,'metadata_pins':{n:m.pin(b)for n,b in data.items()},'source_artifact_binding_verified':True,'old_module_count':len(oldrows),'new_module_count':len(newrows),'module_order_unchanged':[n for n,_ in oldrows]==[n for n,_ in newrows],'added_modules':added,'removed_modules':removed,'changed_modules':changed,'unexpected_changed_modules':sorted(changednames-expected),'expected_modules_not_changed':sorted(expected-changednames),'unchanged_module_count':len(set(old)&set(new))-len(changed),'whole_circuit':{'old':oldhead['circuit'],'new':newhead['circuit']},'annotations':{'old_ordered_sha256':oldhead['annotations_order_preserved'],'actual_ordered_sha256':detail['ordered_annotations_sha256'],'candidate_full_raw_and_ordered_match':annotation_exact,'candidate_only_origin_not_prior_run_pass':True,'candidate':ann},'ports':counts,'acceptance_authorized':False,'canonical_pass':False,'numerical_pass':False,'limitations':['Actual typed descriptor hashes are from the pinned successful CI helper; this local audit does not possess or reparse full actual HIGH/LOW.','Matching source-derived annotation candidate becomes supported only by this actual run raw and ordered hashes; old partial run terminal status is never inherited.','Changed-module names alone do not prove no logic/control feedback; independent source diff audit still required.','SV normalized identity, generated header, native backend, full numerical regression and utilization not qualified.']}
def main():
 p=argparse.ArgumentParser();p.add_argument('--metadata',type=pathlib.Path,required=True);p.add_argument('--summary',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();result=audit(a.metadata,a.summary)
 with a.output.open('x')as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:result[k] for k in ('scope','changed_modules','unexpected_changed_modules','annotations','acceptance_authorized')}))
if __name__=='__main__':main()
