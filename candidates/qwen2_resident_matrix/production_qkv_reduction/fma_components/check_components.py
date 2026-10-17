"""Fixed provider module/port inventory; not arithmetic or timing validation."""
import re,json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent

def need(ok,message):
 if not ok:raise ValueError(message)
def clean(text):return re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
def modules(text):
 text=clean(text);tokens=list(re.finditer(r'\b(module|endmodule)\b',text));names=[];inside=False
 for token in tokens:
  if token[1]=='module':
   need(not inside,'nested module declaration');match=re.match(r'module\s+(\w+)\s*\(',text[token.start():]);need(match is not None,'unsupported module declaration');names.append(match[1]);inside=True
  else:need(inside,'unmatched endmodule');inside=False
 need(not inside and bool(names),'unterminated/empty module file');return names
def ports(text,name):
 text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
 matches=list(re.finditer(r'\bmodule\s+'+name+r'\s*\((.*?)\)\s*;',text,re.S));need(len(matches)==1,'one root module '+name)
 result={};direction=None;width=None
 for part in matches[0][1].split(','):
  part=part.strip();m=re.fullmatch(r'(?:(input|output)\s+)?(?:(?:wire|logic)\s+)?(?:\[(\d+)\s*:\s*(\d+)\]\s*)?(\w+)',part)
  need(m is not None,'unknown port syntax '+part)
  if m[1]:direction=m[1];width=1
  if m[2]:need(int(m[3])==0,'nonzero low bit');width=int(m[2])+1
  need(direction is not None and width is not None and m[4] not in result,'duplicate/unknown direction')
  result[m[4]]=[direction,width]
 return result

def check(root,lane):
 expected=json.loads((P/'PORTS.json').read_text());need(root.is_dir() and not root.is_symlink(),'component directory type');files=sorted(root.iterdir());need(len(files)==4 and all(f.is_file() and not f.is_symlink() and f.suffix=='.sv' for f in files),'exact four regular files and no subdirectories');need({f.stem for f in files}==set(expected),'four exact component SV files')
 allmodules={};evidence={}
 for f in files:
  b=f.read_bytes();need(len(b)<=8*1024**2,'SV cap');s=b.decode();names=modules(s);need(0<len(names)<=32 and len(set(names))==len(names),'module inventory')
  need(not (set(names)&set(allmodules)),'duplicate module definitions across files')
  for n in names:allmodules[n]=f.name
  need(ports(s,f.stem)==expected[f.stem],'provider port shape '+f.stem)
  need(not re.search(r'\b(always_ff|initial)\b|\$readmem',clean(s)),'unexpected stateful initialization in combinational provider')
  evidence[f.name]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),modules=names,ports=expected[f.stem])
 need(len(allmodules)<=64,'total module cap')
 # Fixed matrix lane's named bindings must cover every generated root port exactly.
 lane_text=Path(lane).read_text();signal_widths={}
 for width,names in re.findall(r'\blogic\s*(\[\d+:\d+\])?\s+([^;]+);',lane_text):
  size=1 if not width else int(width[1:].split(':')[0])+1
  for signal in names.split(','):
   if re.fullmatch(r'\w+',signal.strip()):signal_widths[signal.strip()]=size
 for name,spec in expected.items():
  found=re.findall(r'\b'+name+r'\s+\w+\s*\((.*?)\);',lane_text,re.S);need(len(found)==1,'lane provider instance '+name)
  pairs=re.findall(r'\.(\w+)\s*\(\s*(\w+)\s*\)',found[0]);bound=[x[0] for x in pairs];need(len(bound)==len(set(bound)) and set(bound)==set(spec),'lane named ports '+name)
  for port,signal in pairs:need(signal_widths.get(signal)==spec[port][1],'lane signal width '+name+'.'+port)
 return dict(scope='FOUR_EXISTING_FMA_COMPONENT_SYSTEMVERILOG_ONLY',files=evidence,total_module_definitions=len(allmodules),matrix_lane_named_ports_checked=True,arithmetic_tested=False,fullblock=False)
