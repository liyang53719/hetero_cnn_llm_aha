"""Public CI API with bounded preflight/failure receipts; no tools on import."""
from pathlib import Path
import json
from conditional_admission import admit_build as _admit_build
from build_producer import prepare as _prepare,run as _run,artifact_manifest

def admit_build(b,obj,host,frontend_receipt,out):
 p=Path(out);existed=p.exists()
 try:
  result=_admit_build(b,obj,host,frontend_receipt,out)
  result['build_evidence_dir']=str(p.resolve())
  (p/'build_preflight.json').write_text(json.dumps(dict(status='PASS_CONDITIONAL_SOURCE_ABI_MAKE_ADMISSION_ONLY',actual_compile_executed=False),indent=2)+'\n')
  return result
 except Exception as e:
  if not existed and p.is_dir():
   (p/'build_preflight.json').write_text(json.dumps(dict(status='FAIL',code='CONDITIONAL_BUILD_ADMISSION_REJECTED',error_type=type(e).__name__,detail=str(e)[:1024],actual_compile_executed=False),indent=2)+'\n')
  raise

def run(b,stage):
 try:return _run(b,stage)
 except Exception as e:
  p=Path(b['build_evidence_dir'])
  (p/'build_failure.json').write_text(json.dumps(dict(status='FAIL_OR_INCOMPLETE',code='BOUNDED_ARCHIVE_OR_LINK_REJECTED',error_type=type(e).__name__,detail=str(e)[:1024],numerical_pass=False),indent=2)+'\n')
  raise

def prepare(b):
 try:return _prepare(b)
 except Exception as e:
  (Path(b['build_evidence_dir'])/'build_preflight.json').write_text(json.dumps(dict(status='FAIL',code='DERIVED_BUILD_PLAN_REJECTED',error_type=type(e).__name__,detail=str(e)[:1024],actual_compile_executed=False),indent=2)+'\n')
  raise
