"""Bounded observed metadata, not an accepted canonical, ABI or numerical result."""
import argparse,hashlib,json,pathlib,re
FILES={'observed-canonical.tsv':256<<10,'observed-details.json':128<<10}
INPUTS=('original-high.fir','high-annotations.json','low-top-ports.fir')
IDENT=r'[A-Za-z_$][A-Za-z0-9_$]{0,255}'
SHA=r'[0-9a-f]{64}'
QUAL='OBSERVED_UNREVIEWED'
def need(x):
 if not x:raise ValueError('observed metadata contract')
def integer(x,lo=0,hi=2**53):need(type(x) is int and lo<=x<=hi);return x
def digest(x):need(type(x) is str and re.fullmatch(SHA,x));return x
def no_duplicates(pairs):
 out={}
 for k,v in pairs:need(k not in out);out[k]=v
 return out
def read(path,cap):
 need(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=cap)
 b=path.read_bytes();need(0<len(b)<=cap);return b
def obj(b):
 x=json.loads(b,object_pairs_hook=no_duplicates);need(type(x) is dict);return x
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def file_pin(x,cap):
 need(type(x) is dict and set(x)=={'bytes','sha256'});return {'bytes':integer(x['bytes'],1,cap),'sha256':digest(x['sha256'])}
def validate(canonical,details,contract):
 need(set(details)=={'schema','qualification','main','canonical_algorithm','module_count','annotation_count','target_dir_annotation_count','retained_annotation_count','annotation_classes','circuit_sha256','ordered_annotations_sha256','low_port_source','ports'})
 need(details['schema']=='OBSERVED_HIGH_DESCRIPTOR_V1' and details['qualification']==QUAL and details['main']=='HostBlockTopV4')
 need(details['canonical_algorithm']=='CanonicalHighGate_public_semantic_methods')
 need(details['low_port_source']=='ORIGINAL_HELPER_HASH_BOUND_EXTRACTION_NOT_FULL_LOW_REPARSE')
 n=integer(details['module_count'],1,4096);ac=integer(details['annotation_count'],0,100000);tc=integer(details['target_dir_annotation_count'],0,ac)
 need(integer(details['retained_annotation_count'])==ac-tc)
 classes=details['annotation_classes'];need(type(classes) is dict and len(classes)<=128)
 need(all(type(k) is str and re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_.$]{0,255}',k) and integer(v,1,100000) for k,v in classes.items()))
 need(sum(classes.values())==ac)
 need(classes.get('firrtl2.options.TargetDirAnnotation',0)==tc)
 lines=canonical.decode('utf-8').splitlines();need(canonical.endswith(b'\n') and len(lines)==n+4)
 need(lines[:4]==['TEMP_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1','main\tHostBlockTopV4','circuit\t'+digest(details['circuit_sha256']),'annotations_order_preserved\t'+digest(details['ordered_annotations_sha256'])])
 modules=[]
 for line in lines[4:]:
  row=line.split('\t');need(len(row)==3 and row[0]=='module' and re.fullmatch(IDENT,row[1]));digest(row[2]);modules.append(row[1])
 need(len(set(modules))==n and 'HostBlockTopV4' in modules)
 need(contract['schema']=='REVIEWED_OLD85_PLUS_OUTPUT37_V1' and len(contract['old_ports'])==85 and len(contract['added_ports'])==37)
 need(not set(contract['old_ports']) & set(contract['added_ports']))
 expected={**contract['old_ports'],**contract['added_ports']};ports=details['ports']
 need(type(ports) is list and len(ports)==122 and contract['expected_ports']==122)
 names=[]
 for p in ports:
  need(type(p) is dict and set(p)=={'name','direction','type','width'} and type(p['name']) is str and re.fullmatch(IDENT,p['name']))
  names.append(p['name']);need(p['name'] in expected)
  w=integer(p['width'],1,65536);need([p['direction'],w]==expected[p['name']])
  # Old 85 pinned raw header has clock as Clock; other original ports are UInt.
  need(p['type']==('Clock' if p['name']=='clock' else 'UInt<'+str(w)+'>'))
 need(len(set(names))==122 and set(names)==set(expected))
 need(all(v[0]=='output' for v in contract['added_ports'].values()))
 need(sum(v[1] for v in contract['added_ports'].values())==contract['added_bits']==948)
 return {'module_count':n,'annotation_count':ac,'retained_annotation_count':ac-tc,'target_dir_annotation_count':tc,'port_count':122,'old_ports_unchanged':85,'added_output_ports':37,'added_output_bits':948,'circuit_sha256':details['circuit_sha256'],'ordered_annotations_sha256':details['ordered_annotations_sha256']}
def project_receipt(x):
 need(type(x) is dict and set(x)=={'qualification','files','bound_inputs','counts'})
 need(x['qualification']==QUAL and type(x['files']) is dict and set(x['files'])==set(FILES))
 files={n:file_pin(x['files'][n],cap) for n,cap in FILES.items()}
 need(type(x['bound_inputs']) is dict and set(x['bound_inputs'])==set(INPUTS))
 inputs={n:file_pin(x['bound_inputs'][n],384<<20) for n in INPUTS}
 c=x['counts'];need(type(c) is dict and set(c)=={'module_count','annotation_count','retained_annotation_count','target_dir_annotation_count','port_count','old_ports_unchanged','added_output_ports','added_output_bits','circuit_sha256','ordered_annotations_sha256'})
 for k in ('module_count','annotation_count','retained_annotation_count','target_dir_annotation_count','port_count','old_ports_unchanged','added_output_ports','added_output_bits'):integer(c[k])
 need(1<=c['module_count']<=4096 and c['annotation_count']<=100000 and c['retained_annotation_count']+c['target_dir_annotation_count']==c['annotation_count'])
 need((c['port_count'],c['old_ports_unchanged'],c['added_output_ports'],c['added_output_bits'])==(122,85,37,948))
 digest(c['circuit_sha256']);digest(c['ordered_annotations_sha256'])
 return {'qualification':QUAL,'files':files,'bound_inputs':inputs,'counts':dict(c)}
def inspect(root,artifacts,contract):
 root=pathlib.Path(root);need(root.is_dir() and not root.is_symlink())
 content={n:read(root/n,cap) for n,cap in FILES.items()}
 counts=validate(content['observed-canonical.tsv'],obj(content['observed-details.json']),contract)
 receipt={'qualification':QUAL,'files':{n:pin(b) for n,b in content.items()},'bound_inputs':{n:artifacts[n] for n in INPUTS},'counts':counts}
 return project_receipt(receipt)
def verify_inputs(root,inputs):
 need(root.is_dir() and not root.is_symlink() and set(inputs)==set(INPUTS))
 for n in INPUTS:
  p=root/n;expected=file_pin(inputs[n],384<<20)
  need(p.is_file() and not p.is_symlink() and p.stat().st_size==expected['bytes'])
  with p.open('rb') as f:need(hashlib.file_digest(f,'sha256').hexdigest()==expected['sha256'])
def export(work,summary,identity,contract,out):
 need(summary.get('status')=='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY')
 need(all(summary.get(k) is False for k in ('numerical_pass','canonical_pass','target_host_qualified','sv_generated','generated_abi_qualification','physical_resource_or_qor_qualification','block_numerical_pass')))
 need(all(summary[k]==identity[k] for k in ('source_commit','launch_commit','launch_manifest_blob_sha','run_id')))
 expected=project_receipt(summary.get('descriptor'));actual=inspect(work/'descriptor',summary['artifacts'],contract);need(actual==expected)
 for n in INPUTS:need(actual['bound_inputs'][n]==summary['artifacts'][n])
 verify_inputs(work/'original_ir'/'host-diagnostic',actual['bound_inputs'])
 need(not out.exists() and not any(p.is_symlink() for p in (out,*out.parents)))
 provenance={'schema':'OBSERVED_DESCRIPTOR_PROVENANCE_V1','qualification':QUAL,**{k:identity[k] for k in ('source_commit','launch_commit','launch_manifest_blob_sha','run_id')},'descriptor':actual}
 payload={n:read(work/'descriptor'/n,cap) for n,cap in FILES.items()};payload['provenance.json']=(json.dumps(provenance,indent=2)+'\n').encode()
 need(sum(map(len,payload.values()))<=512<<10 and len(payload['provenance.json'])<=65536)
 # Recheck bytes before publishing; no wildcard/rawlog/IR copy.
 need(all(pin(payload[n])==expected['files'][n] for n in FILES));out.mkdir()
 for n,b in payload.items():
  with (out/n).open('xb') as f:f.write(b)
def main():
 p=argparse.ArgumentParser()
 for n in ('work','summary','identity','contract','output'):p.add_argument('--'+n,type=pathlib.Path,required=True)
 a=p.parse_args();export(a.work,obj(read(a.summary,65536)),obj(read(a.identity,65536)),obj(read(a.contract,65536)),a.output)
if __name__=='__main__':main()
