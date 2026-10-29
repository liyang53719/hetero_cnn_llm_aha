"""Fail-closed source-location-directory identity; always save bounded diagnosis.
New baseline must be independently reviewed before this candidate is published.
"""
import argparse,hashlib,json,pathlib,re,os
from sv_comment_only_identity import digest
D=pathlib.Path(__file__).resolve().parent
# Filled only from independently reviewed original c7, never fresh CI output.
EXPECTED='6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5'
SCANNER_SHA='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
MODULE_BASELINE_SHA='0d80da62c042b5da4f2879525d4660df957579a169295a5844deb0d953f2067a'

def check(sv,output):
 if output.exists():raise ValueError('fresh receipt required')
 r={'schema':'SV_DIRECTORY_IDENTITY_RECEIPT_V2','scope':'IDENTITY_ONLY_NO_NUMERICS','status':'FAIL_OR_INCOMPLETE','phase':'scanner_pin','expected_normalized_sha256':EXPECTED,'actual_normalized_sha256':None,'raw_sha256':None,'bytes':None,'counts':{},'error_code':None}
 try:
  r['scanner_sha256']=hashlib.sha256((D/'sv_comment_only_identity.py').read_bytes()).hexdigest()
  if EXPECTED is None or SCANNER_SHA is None:raise ValueError('BASELINE_NOT_APPROVED')
  if r['scanner_sha256']!=SCANNER_SHA:raise ValueError('SCANNER_SOURCE_PIN_MISMATCH')
  r['phase']='input_pin';r['bytes']=sv.stat().st_size
  if sv.is_symlink() or not sv.is_file() or not 0<r['bytes']<=512*1024**2:raise ValueError('SV_INPUT_BOUND')
  with sv.open('rb') as f:r['raw_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
  r['phase']='sourceinfo_directory_digest'
  with sv.open('rb') as f:r['actual_normalized_sha256']=digest(f,r['counts'])
  r['phase']='compare'
  if r['actual_normalized_sha256']!=EXPECTED:raise ValueError('SV_DIRECTORY_NORMALIZED_BYTES_DIFFER_STOP_AUDIT')
  r['status']='PASS_SV_SOURCEINFO_DIRECTORY_IDENTITY_ONLY_NO_NUMERICS';r['phase']='complete'
 except Exception as e:
  allowed={'BASELINE_NOT_APPROVED','SCANNER_SOURCE_PIN_MISMATCH','SV_INPUT_BOUND','SV_DIRECTORY_NORMALIZED_BYTES_DIFFER_STOP_AUDIT','bounded line comment','unterminated lexical token/comment'}
  r['error_code']=str(e) if str(e) in allowed else 'SV_IDENTITY_UNCLASSIFIED_ERROR';r['exception_class']=type(e).__name__
 raw=json.dumps(r,indent=2)+'\n'
 if len(raw.encode())>8192:raise ValueError('bounded identity receipt')
 with output.open('x') as f:f.write(raw)
 # Persist the full-file failure FIRST; bounded module diagnosis is supplemental.
 if r['error_code']=='SV_DIRECTORY_NORMALIZED_BYTES_DIFFER_STOP_AUDIT':
  try:
   from module_fingerprints import fingerprints
   data=(D/'C7_MODULE_FINGERPRINTS.json').read_bytes()
   if hashlib.sha256(data).hexdigest()!=MODULE_BASELINE_SHA:raise ValueError('module baseline pin')
   expected={x['module']:x for x in json.loads(data)['modules']};actual={x['module']:x for x in fingerprints(sv)};changed=[]
   for name in sorted(set(expected)|set(actual)):
    a=actual.get(name);e=expected.get(name)
    if a is None or e is None or a['normalized_sha256']!=e['normalized_sha256']:
     changed.append({'module':name,'expected_sha256':None if e is None else e['normalized_sha256'],'actual_sha256':None if a is None else a['normalized_sha256'],'actual_sourceinfo_count':None if a is None else a['sourceinfo_count']})
   r['module_diagnostics']={'status':'COMPLETE_DIAGNOSTIC_ONLY','expected_count':len(expected),'actual_count':len(actual),'different_count':len(changed),'first_differences':changed[:16],'all_differences_sha256':hashlib.sha256(json.dumps(changed,sort_keys=True).encode()).hexdigest()}
  except Exception:r['module_diagnostics']={'status':'INCOMPLETE_DIAGNOSTIC_ONLY'}
  updated=json.dumps(r,indent=2)+'\n'
  if len(updated.encode())<=16384:
   temp=output.with_name(output.name+'.update')
   with temp.open('x') as f:f.write(updated)
   os.replace(temp,output)
 return r
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--sv',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args();r=check(v.sv,v.output);print(json.dumps(r));raise SystemExit(0 if r['phase']=='complete' else 1)
