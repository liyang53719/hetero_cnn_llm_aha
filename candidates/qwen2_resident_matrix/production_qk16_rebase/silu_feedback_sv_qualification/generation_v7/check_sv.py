"""Lexical generated SV inventory only; linkage is a separate gate."""
import re,hashlib
from pathlib import Path
def need(ok,msg):
 if not ok:raise ValueError(msg)
def cleaned(text):return re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*','',text,flags=re.S)
def check(path):
 p=Path(path);need(p.is_file() and not p.is_symlink(),'regular SV required');b=p.read_bytes();need(0<len(b)<=128*1024**2,'SV size cap');s=cleaned(b.decode());inside=False;names=[]
 for m in re.finditer(r'\b(module|endmodule)\b',s):
  if m[1]=='module':
   need(not inside,'nested module');h=re.match(r'module\s+(\w+)\s*\(',s[m.start():]);need(h is not None,'unknown declaration');names.append(h[1]);inside=True
  else:need(inside,'unmatched endmodule');inside=False
 need(not inside and 0<len(names)<=768,'module limit/unclosed')
 need(len(set(names))==len(names),'duplicate module')
 need(names.count('ProductionQk16KernelBench')==1,'unique fixed top')
 need(not set(names)&{'HostBlockTop','HostBlockCommands','idma_backend_rw_axi_flat_wrap','qwen2_matrix_command_endpoint','tc_clk_gating'},'unexpected substituted external/Host definition')
 return dict(scope='GENERATED_REAL_KERNEL_TEST_SHELL_SV_INVENTORY_ONLY',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),modules=names,definition_count=len(names),top='ProductionQk16KernelBench',linked=False,numerical=False)

def parens(s,start):
 need(start<len(s) and s[start]=='(','expected parenthesis');depth=1
 for i in range(start+1,len(s)):
  if s[i]=='(':depth+=1
  elif s[i]==')':
   depth-=1
   if depth==0:return s[start+1:i],i+1
 raise ValueError('unclosed parenthesis')
def bindings(s,allow_empty=False):
 result={};pos=0
 while pos<len(s):
  m=re.match(r'\s*\.(\w+)\s*\(',s[pos:]);need(m is not None,'unknown/positional binding');name=m[1];need(name not in result,'duplicate named binding')
  body,end=parens(s,pos+m.end()-1);need(body.strip() or allow_empty,'empty external binding');result[name]=body.strip();pos=end
  tail=re.match(r'\s*(,|$)',s[pos:]);need(tail is not None,'binding separator');pos+=tail.end()
 return result
def direct_instance_context(prefix):
 # Conservative direct module-body syntax only; never evaluate generate guards.
 block=0;generate=0;conditional=0;last_boundary=0
 token=re.compile(r'`(?:ifdef|ifndef|elsif|else|endif)\b[^\n]*|\b(?:begin|end|generate|endgenerate|endcase)\b|;')
 for m in token.finditer(prefix):
  word=m[0]
  if word.startswith(('`ifdef','`ifndef')):conditional+=1
  elif word.startswith('`endif'):
   need(conditional>0,'preprocessor nesting');conditional-=1;last_boundary=m.end()
  elif word.startswith(('`else','`elsif')):need(conditional>0,'preprocessor branch nesting')
  elif word=='begin':block+=1
  elif word=='end':need(block>0,'block nesting');block-=1;last_boundary=m.end()
  elif word=='generate':generate+=1
  elif word=='endgenerate':need(generate>0,'generate nesting');generate-=1;last_boundary=m.end()
  elif word in [';','endcase']:last_boundary=m.end()
 need(block==0 and generate==0 and conditional==0,'conditional/non-direct instance')
 need(not prefix[last_boundary:].strip(),'unknown implicit conditional/instance prefix')

def external_inventory(text,spec):
 import collections
 s=cleaned(text);starts=list(re.finditer(r'\bmodule\s+(\w+)\s*\(',s));bodies={}
 for m in starts:
  _,end=parens(s,m.end()-1);tail=re.match(r'\s*;',s[end:]);need(tail is not None,'module header terminator');begin=end+tail.end();finish=re.search(r'\bendmodule\b',s[begin:]);need(finish is not None,'module end');bodies[m[1]]=s[begin:begin+finish.start()]
 known=set(bodies)|set(spec);pat=re.compile(r'\b('+'|'.join(re.escape(x) for x in sorted(known,key=len,reverse=True))+r')\b');edges={};evidence=[]
 for parent,body in bodies.items():
  items=[];instnames=set()
  for m in pat.finditer(body):
   direct_instance_context(body[:m.start()])
   typ=m[1];pos=m.end();ws=re.match(r'\s*',body[pos:]);pos+=ws.end();params={}
   if pos<len(body) and body[pos]=='#':
    pos+=1;ws=re.match(r'\s*',body[pos:]);pos+=ws.end();raw,pos=parens(body,pos);params=bindings(raw)
   inst=re.match(r'\s*(\w+)\s*\(',body[pos:]);need(inst is not None,'unknown instance form '+typ);name=inst[1];need(name not in instnames,'duplicate instance name');instnames.add(name)
   raw,end=parens(body,pos+inst.end()-1);need(re.match(r'\s*;',body[end:]) is not None,'unknown instance terminator');items.append((name,typ))
   if typ in spec:
    ports=bindings(raw,allow_empty=True)
    for port,expr in ports.items():need(expr or (typ=='idma_backend_rw_axi_flat_wrap' and port=='busy_o'),'unapproved unconnected external output')
    need(set(ports)==set(spec[typ]['ports']),'external named-port inventory '+typ)
    need(set(params)==set(spec[typ]['parameters']),'external parameters '+typ)
    for key,want in spec[typ]['parameters'].items():
     val=params[key];need(re.fullmatch(r"(?:\d+'[hdb])?"+want,val) is not None,'external parameter value '+key)
    evidence.append({'parent':parent,'instance':name,'type':typ,'parameters':params,'bindings':ports})
  edges[parent]=items
 counts=collections.Counter();paths=[]
 def walk(typ,path,stack):
  need(typ not in stack,'cyclic module graph');paths.append(path);need(len(paths)<=20000,'instance graph cap')
  if typ in spec:counts[typ]+=1;return
  for name,child in edges[typ]:walk(child,path+'.'+name,stack+[typ])
 walk('ProductionQk16KernelBench','ProductionQk16KernelBench',[])
 need(dict(counts)=={n:x['instance_count'] for n,x in spec.items()},'reachable external resource counts')
 return {'reachable_external_counts':dict(counts),'named_port_bindings':evidence,'binding_widths_proved':False,'width_check_deferred_to_real_provider_lint':True}

_inventory_check=check
def check(path):
 import json
 result=_inventory_check(path);spec=json.loads((Path(__file__).parent/'EXTERNAL_INTERFACE_PINS.json').read_text());result['external_inventory']=external_inventory(Path(path).read_text(),spec);return result
