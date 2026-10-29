"""Pinned source/root ANSI ABI preflight only; not preprocessing/elaboration/numerics."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
WRAPPER_SHA='a82bc50fac9b29df3f5f68527361f9dfac4792dfea3178b84eb488428d8d12c0'
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clean(s):return re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
def ansi_ports(text,module):
 m=re.search(r'\bmodule\s+'+re.escape(module)+r'\b',text);need(m is not None,'required declaration missing: '+module)
 body=text[m.end():].split('endmodule',1)[0];header=body.split(');',1)[0];start=re.search(r'\b(input|output)\b',header);need(start is not None,'ANSI header missing: '+module);header=header[start.start():];ports={};direction=width=None
 for item in header.split(','):
  item=item.strip();m=re.fullmatch(r'(input|output)\s+(logic|axi_req_t|axi_rsp_t)\s*(?:\[(\d+):(\d+)\])?\s*(\w+)',item)
  if m:
   direction,typ,name=m[1],m[2],m[5];width=abs(int(m[3])-int(m[4]))+1 if m[3] else {'logic':1,'axi_req_t':785,'axi_rsp_t':532}[typ]
  else:need(direction is not None and re.fullmatch(r'\w+',item) is not None,'unsupported ANSI field: '+item);name=item
  need(name not in ports,'duplicate ANSI name');ports[name]=[direction,width]
 return ports

def validate_provider_roots(providers,contract_path=None):
 contract_path=Path(contract_path or HERE/'EXTERNAL_ROOT_ABI.json');contract=json.loads(contract_path.read_text());sources={};declarations={};pins={}
 for path in providers:
  p=Path(path);need(p.is_file() and not p.is_symlink(),'regular provider missing: '+str(p));need(p.stat().st_size<=64*1024**2,'provider size');text=clean(p.read_text());sources[str(p)]=text;pins[str(p)]=sha(p)
  for name in re.findall(r'^\s*module\s+(\w+)\b',text,re.M):declarations.setdefault(name,[]).append(str(p))
 roots={}
 for module,row in contract['roots'].items():
  matches=declarations.get(module,[]);need(len(matches)==1,'required external root count !=1: '+module);path=matches[0];need(pins[path]==row['source_sha256'],'required root source pin drift: '+module);ports=ansi_ports(sources[path],module);need(ports==row['ports'],'required root ANSI ABI mismatch: '+module);roots[module]={'path':path,'sha256':pins[path],'ports':len(ports)}
 return {'scope':'PINNED_EXTERNAL_ROOT_SOURCE_AND_LEXICAL_ABI_ONLY','roots':roots,'provider_files':len(providers),'contract_sha256':sha(contract_path),'not_preprocessor_or_numerical_pass':True}
