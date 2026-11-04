"""Read-only prior O1 metadata regression; synthetic candidate labels/map only.
Never reads or runs ELF/SV, never changes production map or original receipts.
"""
import argparse,hashlib,importlib.util,json,pathlib,sys
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('candidate_metadata_regression',D/'candidate_dependency_proof.py');proof=importlib.util.module_from_spec(s);s.loader.exec_module(proof)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--payload',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();root=a.payload.resolve(strict=True)
 names=('source_manifest.json','build_receipt.json','tool_manifest.json','frozen_artifact.json');original={};inputs={}
 for name in names:
  p=root/name
  if p.is_symlink()or not p.is_file()or p.stat().st_size>16<<20:raise ValueError('bounded actual metadata only')
  raw=p.read_bytes();inputs[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()};original[name]=json.loads(raw)
 m=json.loads(json.dumps(original['source_manifest.json']));receipt=json.loads(json.dumps(original['build_receipt.json']));frozen=original['frozen_artifact.json'];tool=original['tool_manifest.json'];dep=m['p0_retained_evidence']['driver_dependency']
 suffix='/candidates/ci_frontend_pipeline_r2_20261029/build_producer.py';roots=[p[:-len(suffix)]for p in m['generation_input_pins']if p.endswith(suffix)]
 if len(roots)!=1:raise ValueError('one actual old builder root')
 repo=roots[0]
 # Only synthetic code-role labels are new. Underlying GCC/Make/.d/phase
 # receipts and all tool/output/header hashes remain actual old O1 objects.
 implementations={p:hashlib.sha256(('SYNTHETIC_CANDIDATE_ROLE:'+p).encode()).hexdigest()for p in proof.CANDIDATE_REQUIRED_IMPLEMENTATIONS}
 implementations[proof.COLLECTOR_PATH]=proof.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA
 for rel,h in implementations.items():m['generation_input_pins'][str(pathlib.PurePosixPath(repo)/rel)]=h
 receipt['schema']='MODEL_CANDIDATE_BUILD_RECEIPT_V1';receipt['status']='UNREVIEWED_MODEL_BUILD'
 common=dict(frozen['common']);common['build_receipt']=dict(common['build_receipt'],path=str(root/'build_receipt.json'))
 with mock.patch.object(proof,'CANDIDATE_IMPLEMENTATION_PINS',implementations):
  policy=proof.verify_compilation_policy(dep,m,receipt,tool,repo)
  selected=proof.verify(dep,m,{'source_pins':{'sparse_memory':proof.SPARSE_HEADER}},common,receipt,repo)
  changed=json.loads(json.dumps(dep));changed['compilation_phases'][0]['argv']+=['CXXFLAGS=-Ofast']
  rejected=False
  try:proof.verify_compilation_policy(changed,m,receipt,tool,repo)
  except ValueError:rejected=True
  if not rejected:raise ValueError('extra compiler override not rejected')
 header=[r for p,r in dep['dependencies'].items()if pathlib.PurePosixPath(p).name=='VHostBlockTopV4.h']
 if len(header)!=1:raise ValueError('one actual header dependency')
 out={'scope':'READ_ONLY_ACTUAL_OLD_O1_GCC_MAKE_DEPENDENCY_AND_FIVE_PHASE_METADATA_WITH_SYNTHETIC_CANDIDATE_SCHEMA_IMPLEMENTATION_MAP','actual_input_pins':inputs,'actual_source_commit':original['source_manifest.json']['source_commit'],'actual_five_phase_policy_verified':policy,'actual_sparse_header':{'bytes':dep['resolved_sparse_header']['bytes'],'sha256':dep['resolved_sparse_header']['sha256']},'actual_host_header_dependency_pin':{'bytes':header[0]['bytes'],'sha256':header[0]['sha256']},'extra_flag_negative_rejected':rejected,'host_header_text_not_present_in_old_artifact':True,'new_candidate_compilation_pass':False,'numerical_pass':False,'elf_or_sv_read_or_executed':False,'production_implementation_map_modified':False}
 if a.output.exists():raise ValueError('fresh regression result required')
 a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'scope':out['scope'],'actual_metadata_positive':True,'negative_rejected':True,'new_candidate_pass':False}))
if __name__=='__main__':main()
