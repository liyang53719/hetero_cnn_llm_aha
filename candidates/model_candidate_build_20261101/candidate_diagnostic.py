"""Finite helper telemetry to existing Actions stdout, never raw logs or bodies."""
import json,pathlib,re
STAGES={'canonical_full','transform_new_toolchain','emit_host'}
REASONS={'NONE','INPUT_BOUNDS_OR_PIN','HIGH_ROUNDTRIP','ANNOTATION_ROUNDTRIP','ANNOTATION_CLASS_TARGET','CANONICAL_IDENTITY','FIXED_MODULE_HASH','FIXED_PROVIDER_BINDINGS','BANK_SUBTREE_HASH','FIFO_LOCAL_SHAPE','DENSE_ACC_LOCAL_SHAPE','LOW_LOWERING','LOW_SERIALIZATION','FINAL_CONNECTORS','TOP_PORT_ABI','SV_EMISSION','METADATA_BOUNDS','INTERNAL_UNCLASSIFIED'}
NUMBERS={'high_bytes','annotation_bytes','module_count','annotation_count','target_dir_count','low_port_count','reachable_instance_count','fixed_module_index','bank_subtree_module_index'}
HASHES={'high_sha256','annotations_sha256','canonical_sha256','failing_module_sha256'}
def project(d,stage):
 if type(d)is not dict or set(d)!={'schema','stage','status','reason_code','actual','numerical_pass','post_build_structure_accepted'}:raise ValueError('diagnostic exact fields')
 if d['schema']!='MODEL_CANDIDATE_DIAGNOSTIC_V1'or stage not in STAGES or d['stage']!=stage or d['status']not in {'OBSERVED_COMPLETE_UNREVIEWED','REJECTED_UNREVIEWED'}or d['reason_code']not in REASONS:raise ValueError('diagnostic finite enums')
 if (d['status']=='OBSERVED_COMPLETE_UNREVIEWED')!=(d['reason_code']=='NONE')or d['numerical_pass']is not False or d['post_build_structure_accepted']is not False:raise ValueError('diagnostic not acceptance')
 a=d['actual']
 if type(a)is not dict or not set(a)<=(NUMBERS|HASHES):raise ValueError('diagnostic safe fields')
 for k,v in a.items():
  if k in NUMBERS:
   if type(v)is not int or not 0<=v<=2**53:raise ValueError('bounded count')
  elif type(v)is not str or re.fullmatch('[0-9a-f]{64}',v)is None:raise ValueError('bounded SHA')
 return d

def read_projection(path,stage):
 try:
  p=pathlib.Path(path)
  if p.is_symlink()or not p.is_file()or not 0<p.stat().st_size<=8192:raise ValueError('bounded diagnostic file')
  result=project(json.loads(p.read_text()),stage)
 except Exception:
  result={'schema':'MODEL_CANDIDATE_DIAGNOSTIC_UNAVAILABLE_V1','stage':stage if stage in STAGES else 'UNKNOWN','numerical_pass':False,'post_build_structure_accepted':False}
 text=json.dumps(result,separators=(',',':'),sort_keys=True,allow_nan=False)
 if len(text.encode())>8192:raise ValueError('safe telemetry cap')
 return text
