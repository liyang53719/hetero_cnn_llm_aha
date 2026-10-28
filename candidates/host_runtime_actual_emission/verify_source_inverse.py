"""Verify original source hash from two private literals; no source output or execution."""
from pathlib import Path
import hashlib,json,argparse

def verify(root,literals):
 if not isinstance(literals,list) or len(literals)!=2 or any(not isinstance(x,str) or not x or any(c in x for c in ['"','\n','\r','\x00','\\']) for x in literals):raise ValueError('two safe literal values required')
 r=next(x for x in json.loads((root/'SOURCE_PINS.json').read_text())['files'] if x['redactions']==2)
 b=(root/r['path']).read_bytes()
 for i,x in enumerate(literals):
  token=('"REQUIRES_PARENT_LITERAL_'+str(i)+'"').encode()
  if b.count(token)!=1:raise ValueError('token count')
  b=b.replace(token,('"'+x+'"').encode())
 if dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())!=r['original']:raise ValueError('original source mismatch')
 return True
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('private_json_file',type=Path);a=p.parse_args();verify(Path(__file__).resolve().parent,json.loads(a.private_json_file.read_text()));print('PASS_ORIGINAL_SOURCE_HASH_ONLY_NOT_EQUIVALENCE_OR_RECOMPILE')
