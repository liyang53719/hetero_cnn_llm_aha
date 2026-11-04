"""Observe generated candidate bytes only. No expected identity or acceptance."""
import argparse,hashlib,importlib.util,json,pathlib
D=pathlib.Path(__file__).resolve().parent
SCANNER_SHA='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
INVENTORY_SHA='685b15b4f9bee8d23ac25ffc7d26aa718d55621e5fe1b9b2f3519669f24768d4'
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def module(path,want,name):
 if path.is_symlink()or not path.is_file()or sha(path)!=want:raise ValueError('observer implementation pin')
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def observe(sv,output):
 if output.exists():raise ValueError('fresh observation required')
 scanner=module(D.parent/'ci_frontend_materialization_r2_20261029/sv_comment_only_identity.py',SCANNER_SHA,'candidate_original_scanner')
 inv=module(D/'sv_inventory_single_pass.py',INVENTORY_SHA,'candidate_single_pass')
 try:
  r=inv.inventory(sv,scanner)
  r=dict(schema='MODEL_CANDIDATE_SV_OBSERVATION_V1',status='OBSERVED_UNREVIEWED',phase='complete',scope='ACTUAL_BYTES_ONLY_NOT_STRUCTURE_OR_NUMERICAL_ACCEPTANCE',raw_sha256=r['raw_sha256'],actual_normalized_sha256=r['normalized_sha256'],bytes=r['bytes'],counts=r['counts'],modules=r['modules'],scanner_sha256=SCANNER_SHA,inventory_sha256=INVENTORY_SHA,numerical_pass=False,sv_accepted=False)
 except Exception as e:
  allowed={'SV input bound','module diagnostic line bound','nested module diagnostic boundary','module name bound or duplicate','module inventory nonexhaustive gap','module bound','module terminal LF required for lexical continuity','module count bound','module inventory incomplete','SV input mutated during observation','bounded line comment','unterminated lexical token/comment'}
  code=str(e)if str(e)in allowed else 'UNCLASSIFIED_OBSERVATION_ERROR'
  r=dict(schema='MODEL_CANDIDATE_SV_OBSERVATION_V1',status='INCOMPLETE',phase='scanner',error_code=code,exception_class=type(e).__name__,numerical_pass=False,sv_accepted=False)
 raw=(json.dumps(r,indent=2)+'\n').encode()
 if len(raw)>2<<20:raise ValueError('bounded complete observation')
 with output.open('xb')as f:f.write(raw)
 return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sv',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();r=observe(a.sv,a.output);print('MODEL_CANDIDATE_SV_'+r['status']);raise SystemExit(0 if r['status']=='OBSERVED_UNREVIEWED'else 1)
