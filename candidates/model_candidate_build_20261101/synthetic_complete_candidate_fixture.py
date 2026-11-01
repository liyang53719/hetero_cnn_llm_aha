"""ALL_SYNTHETIC_CANDIDATE_EVIDENCE fixture constructor, never production input.
Old closed O1 metadata supplies Make/.d/five-phase grammar templates only.
New 122 header text, 20 receipts/identity/map, ELF/SV are explicitly synthetic.
Never reads or executes the old ELF/SV; never modifies original evidence.
"""
import ast,hashlib,importlib.util,json,pathlib,re,shutil
D=pathlib.Path(__file__).resolve().parent
P=pathlib.Path
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def write(p,value):p=P(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n')
def textpin(path,text):return dict(path=str(path),bytes=len(text.encode()),sha256=hashlib.sha256(text.encode()).hexdigest(),text=text)
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def reseal(root,source=None,receipt=None,manifest=None):
 """Rehash synthetic fixture after N test adds its own role/review evidence."""
 root=P(root);source=source if source is not None else json.loads((root/'source_manifest.json').read_text());receipt=receipt if receipt is not None else json.loads((root/'build_receipt.json').read_text());manifest=manifest if manifest is not None else json.loads((root/'frozen_artifact.json').read_text())
 obs=source['model_candidate_observation'];oh=hashlib.sha256(canon(obs)).hexdigest();write(root/'source_manifest.json',source)
 receipt['model_candidate_observation_sha256']=oh
 for key,name in [('binary','dut.bin'),('sv','hardware.sv'),('driver','driver.cpp'),('source_manifest','source_manifest.json'),('tool_manifest','tool_manifest.json')]:receipt[key+'_sha256']=sha(root/name)
 write(root/'build_receipt.json',receipt);manifest['model_candidate_observation_sha256']=oh
 for key,row in manifest['common'].items():p=root/row['path'];row.update(bytes=p.stat().st_size,sha256=sha(p))
 p=root/'tool_manifest.json';manifest['tool_manifest'].update(bytes=p.stat().st_size,sha256=sha(p));write(root/'frozen_artifact.json',manifest)
 return {'manifest_sha256':sha(root/'frozen_artifact.json'),'expanded_bytes':sum(p.stat().st_size for p in root.iterdir())}

def make_fixture(destination,old_metadata_payload):
 destination=P(destination).resolve();old=P(old_metadata_payload).resolve(strict=True)
 if destination.exists():raise ValueError('fresh synthetic destination required')
 destination.mkdir(parents=True)
 tested=load_module('_fixture_package_tests',D/'test_pack_model_candidate.py');case=tested.PackTests('test_pack_exact_seven_unreviewed');case.setUp()
 try:
  produced=case.runpack();root=destination/'payload';shutil.copytree(P(produced['manifest']['path']).parent,root)
  # Read metadata and original driver source ONLY, never old dut.bin/hardware.sv.
  source=json.loads((old/'source_manifest.json').read_text());prior_receipt=json.loads((old/'build_receipt.json').read_text());tool=json.loads((old/'tool_manifest.json').read_text());prior_frozen=json.loads((old/'frozen_artifact.json').read_text())
  metadata_pins={n:sha(old/n)for n in ('source_manifest.json','build_receipt.json','tool_manifest.json','frozen_artifact.json','driver.cpp')}
  (root/'driver.cpp').write_bytes((old/'driver.cpp').read_bytes());write(root/'tool_manifest.json',tool)
  synthetic_source=json.loads((root/'source_manifest.json').read_text());receipt=json.loads((root/'build_receipt.json').read_text());manifest=json.loads((root/'frozen_artifact.json').read_text())
  source['source_commit']='a'*40;receipt['source_commit']='a'*40;receipt['launch_commit']='b'*40;manifest['artifact_identity'].update(source_commit='a'*40,launch_commit='b'*40)
  source['sv_sha256']=sha(root/'hardware.sv');source['driver_sha256']=sha(root/'driver.cpp')
  source['model_candidate_observation']=synthetic_source['model_candidate_observation'];source['model_candidate_observation']['source_closure']['source_commit']='a'*40
  source['model_source_evidence']={'schema':'SYNTHETIC_ROLE_EVIDENCE_PLACEHOLDER_FOR_CONSUMER_TEST_ONLY'}
  dep=source['p0_retained_evidence']['driver_dependency'];binary_pin=dict(dep['binary'],bytes=(root/'dut.bin').stat().st_size,sha256=sha(root/'dut.bin'));dep['binary']=binary_pin;dep['compilation_phases'][-1]['output']=dict(binary_pin)
  ports=json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text())['ports'];lines=[]
  for name,(direction,width)in ports.items():
   kind='8'if width<=8 else '16'if width<=16 else ''if width<=32 else '64'if width<=64 else 'W';suffix=','+str((width+31)//32)if width>64 else ''
   lines.append('VL_'+('IN'if direction=='input'else'OUT')+kind+'(&'+name+','+str(width-1)+',0'+suffix+');')
  header_text='// ALL SYNTHETIC reconstructed122 header, NOT original builder text.\n'+'\n'.join(lines)+'\n'
  hp=[p for p in dep['dependencies']if P(p).name=='VHostBlockTopV4.h']
  if len(hp)!=1:raise ValueError('one old header dependency template')
  header=textpin(hp[0],header_text);dep['dependencies'][hp[0]]={k:header[k]for k in ('path','bytes','sha256')};source['derived_generated_pins'][hp[0]]=header['sha256']
  evidence=synthetic_source['model_candidate_build_evidence'];evidence['driver_dependency']=dep;evidence['actual_host_header']=header
  receipt['phases']=[]
  for phase in dep['compilation_phases']:
   name=phase['phase'];r=phase['supervisor'];evidence['actual_stage_receipts'][name]=textpin('/synthetic/run/'+name+'/RESULT.json',json.dumps(r,indent=2)+'\n')
   receipt['phases'].append(dict(phase=name,argv=phase['argv'],output_sha256=phase['output']['sha256'],native_exit=0,supervisor_receipt_sha256=hashlib.sha256(canon(r)).hexdigest()))
  for s in receipt['stages']:s['receipt_sha256']=evidence['actual_stage_receipts'][s['name']]['sha256']
  source['model_candidate_observation']['stage_receipts']=[dict(name=s['name'],bytes=evidence['actual_stage_receipts'][s['name']]['bytes'],sha256=evidence['actual_stage_receipts'][s['name']]['sha256'])for s in receipt['stages']]
  source['model_candidate_build_evidence']=evidence
  repo=destination/'synthetic_checkout';c=repo/'candidates/model_candidate_build_20261101';c.mkdir(parents=True)
  for name in ('pack_model_candidate.py','MODEL_CANDIDATE_PRECONDITIONS.json'):(c/name).write_bytes((D/name).read_bytes())
  public=repo/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json';public.parent.mkdir();public.write_text(json.dumps(ports,indent=2)+'\n')
  # Reuse exact published public ABI contract serialization, not a new pin.
  known=D.parent/'source/candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'
  if known.is_file():public.write_bytes(known.read_bytes())
  else:
   # Repository wrapper supplies this fixed contract alongside the fixture.
   fixed=D/'OBSERVER_HOST_PORTS_122.json'
   if not fixed.is_file():raise ValueError('test-only exact original122 contract file required')
   public.write_bytes(fixed.read_bytes())
  original_proof=load_module('_fixture_original_candidate_proof',D/'candidate_dependency_proof.py')
  impl={p:hashlib.sha256(('SYNTHETIC_CANDIDATE_ROLE:'+p).encode()).hexdigest()for p in original_proof.CANDIDATE_REQUIRED_IMPLEMENTATIONS};impl[original_proof.COLLECTOR_PATH]=original_proof.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA;impl['candidates/model_candidate_build_20261101/pack_model_candidate.py']=sha(c/'pack_model_candidate.py')
  proof_text=(D/'candidate_dependency_proof.py').read_text();proof_text=re.sub(r'^CANDIDATE_IMPLEMENTATION_PINS = .*$', 'CANDIDATE_IMPLEMENTATION_PINS = '+repr(impl),proof_text,flags=re.M);(c/'candidate_dependency_proof.py').write_text(proof_text)
  suffix='/candidates/ci_frontend_pipeline_r2_20261029/build_producer.py';builder_roots=[p[:-len(suffix)]for p in source['generation_input_pins']if p.endswith(suffix)]
  if len(builder_roots)!=1:raise ValueError('one actual old builder root template')
  builder=builder_roots[0]
  for rel,h in impl.items():source['generation_input_pins'][str(P(builder)/rel)]=h
  catalog={'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','original_source_commit':'a'*40,'files':[dict(path=str(p.relative_to(repo)),bytes=p.stat().st_size,sha256=sha(p))for p in (c/'pack_model_candidate.py',c/'candidate_dependency_proof.py',c/'MODEL_CANDIDATE_PRECONDITIONS.json',public)]}
  cat=repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json';write(cat,catalog);source['model_candidate_observation']['source_closure']['source_pins_sha256']=sha(cat)
  result=reseal(root,source,receipt,manifest)
  info=dict(scope='ALL_SYNTHETIC_CANDIDATE_EVIDENCE_USING_OLD_METADATA_GRAMMAR_TEMPLATES_ONLY',payload_root=str(root),source_root=str(repo),candidate_dir=str(c),source_catalog_pin=dict(path=str(cat),bytes=cat.stat().st_size,sha256=sha(cat)),identity=manifest['artifact_identity'],implementation_pins=impl,old_metadata_template_pins=metadata_pins,old_elf_or_sv_read=False,new_candidate_build_pass=False,**result)
  write(destination/'FIXTURE_SCOPE.json',info);return info
 finally:case.doCleanups()
