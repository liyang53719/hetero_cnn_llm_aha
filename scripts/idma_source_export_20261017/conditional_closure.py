"""Bounded source-only conditional include walker; no macro expansion or EDA.
Undefined identifiers have the standard ifdef=false meaning. Unsupported
conditional syntax and directive-producing macro bodies fail closed.
"""
import re
from pathlib import Path
IDENT=r'[A-Za-z_][A-Za-z0-9_$]*'
CONTROL={'ifdef','ifndef','elsif','else','endif','define','undef','include','undefineall'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def lines(text):
 # Strip comments, retaining strings and newlines. Mask strings separately so
 # apparent directives inside ordinary literals never become control tokens.
 clean=[];mask=[];i=0
 while i<len(text):
  if text.startswith('//',i):
   end=text.find('\n',i);end=len(text) if end<0 else end
   clean.extend(' '*(end-i));mask.extend(' '*(end-i));i=end
  elif text.startswith('/*',i):
   end=text.find('*/',i+2);need(end>=0,'unterminated comment');end+=2
   blank=''.join('\n' if c=='\n' else ' ' for c in text[i:end]);clean.extend(blank);mask.extend(blank);i=end
  elif text[i]=='"' and not(i and text[i-1]=='`'):
   start=i;i+=1
   while i<len(text):
    if text[i]=='\\':i+=2;continue
    if text[i]=='"':i+=1;break
    i+=1
   else:raise ValueError('unterminated string')
   s=text[start:i];clean.extend(s);mask.extend('\n' if c=='\n' else ' ' for c in s)
  else:clean.append(text[i]);mask.append(text[i]);i+=1
 cs=''.join(clean).splitlines();ms=''.join(mask).splitlines();j=0
 while j<len(cs):
  c=cs[j];m=ms[j];j+=1;continued=False
  while c.rstrip().endswith('\\'):
   continued=True;need(j<len(cs),'unterminated continuation');c=c.rstrip()[:-1]+' '+cs[j];m=m.rstrip()[:-1]+' '+ms[j];j+=1
  yield c,m,continued

def walk(sources,include_dirs,root,defines=None):
 root=Path(root).resolve();macros=dict(defines or {});seen=set();visiting=[];steps=0
 need(len(macros)<10000,'macro cap')
 def visit(p):
  nonlocal steps
  p=p.resolve();need(p.is_relative_to(root) and p.is_file() and not p.is_symlink(),'invalid closure path')
  need(len(visiting)<128 and p not in visiting,'recursive include');visiting.append(p);seen.add(p)
  need(p.stat().st_size<=64*1024*1024,'source size cap')
  stack=[];active=True
  for c,m,continued in lines(p.read_text()):
   steps+=1;need(steps<=2000000,'preprocessor step cap')
   need(not re.search(r'`'+IDENT+r'``',m),'dynamic macro-name construction')
   need(not re.search(r'`(?![A-Za-z_`"])',m),'unsupported bare backtick')
   tokens=list(re.finditer(r'`('+IDENT+')',m));controls=[t for t in tokens if t[1] in CONTROL]
   # Macro definitions form one logical line; their body is not executed now.
   head=re.match(r'^\s*`('+IDENT+r')\b',m)
   if not controls:
    need('`"' not in m and '``' not in m,'unsupported macro argument quoting/pasting')
    continue
   need(head is not None and head[1] in CONTROL,'inline control directive')
   op=head[1];arg=c[head.end():].strip()
   need(not continued or op=='define','unsupported continued directive')
   if op!='define':need(len(controls)==1,'multiple control directives')
   if op in ('ifdef','ifndef','elsif'):
    need(re.fullmatch(IDENT,arg) is not None,'unsupported condition expression')
    cond=arg in macros
    if op=='ifndef':cond=not cond
    if op=='elsif':
     need(stack and not stack[-1][2],'unmatched elsif');parent,taken,_=stack[-1]
     active=parent and not taken and cond;stack[-1][1]=taken or cond
    else:
     need(len(stack)<128,'conditional depth cap');stack.append([active,cond,False]);active=active and cond
   elif op=='else':
    need(not arg and stack and not stack[-1][2],'unmatched else');parent,taken,_=stack[-1];active=parent and not taken;stack[-1][1:]=[True,True]
   elif op=='endif':
    need(not arg and stack,'unmatched endif');active=stack.pop()[0]
   elif op=='define':
    match=re.match('('+IDENT+')(.*)',arg);need(match is not None,'unsupported macro definition')
    name,body=match.groups()
    body_mask=re.match('('+IDENT+')(.*)',m[head.end():].strip()).group(2)
    need(name not in CONTROL,'reserved directive macro name')
    if body.startswith('('):
     depth=0;end=None
     for index,ch in enumerate(body_mask):
      if ch=='(':depth+=1
      elif ch==')':
       depth-=1
       if depth==0:end=index;break
     need(end is not None,'unterminated macro parameter list')
     params=[];start=1;depth=0
     for index,ch in enumerate(body_mask[1:end]+',',1):
      if ch in '([{':depth+=1
      elif ch in ')]}':depth-=1
      elif ch==',' and depth==0:
       part=body_mask[start:index].strip();start=index+1
       if part:
        param=re.match('('+IDENT+r')(?:\s*=.*)?$',part)
        need(param is not None,'unsupported macro formal');params.append(param[1])
     for formal in params:
      need(not re.search(r'`'+re.escape(formal)+r'\b',body_mask[end+1:]),'dynamic directive from macro formal')
    need(not re.search(r'`'+IDENT+r'``',body_mask),'dynamic macro-name construction')
    # Conditional directives deferred within a macro must be self-contained;
    # otherwise invoking a macro could change the outer include-active state.
    body_stack=[]
    for directive in re.findall(r'`(ifdef|ifndef|elsif|else|endif)\b',body_mask):
     if directive in ('ifdef','ifndef'):body_stack.append(False)
     elif directive in ('elsif','else'):
      need(body_stack and not body_stack[-1],'macro body conditional imbalance')
      if directive=='else':body_stack[-1]=True
     else:
      need(body_stack,'macro body conditional imbalance');body_stack.pop()
    need(not body_stack,'macro body conditional imbalance')
    # No token-pasting directive constructors or nested include/define mutation.
    need(not re.search(r'`(?:include|define|undef|undefineall)\b',body_mask),'directive-producing macro body')
    if active:macros[name]=body;need(len(macros)<10000,'macro cap')
   elif op=='undef':
    need(re.fullmatch(IDENT,arg) is not None,'unsupported undef')
    if active:macros.pop(arg,None)
   elif op=='undefineall':raise ValueError('unsupported undefineall')
   elif op=='include':
    literal=re.fullmatch(r'"([^"\n\\]+)"',arg);need(literal is not None,'unsupported include syntax')
    if active:
     rel=literal[1];need(not Path(rel).is_absolute(),'absolute include')
     candidates=[(base/rel).resolve() for base in [p.parent,*include_dirs]]
     q=next((q for q in candidates if q.is_file()),None)
     need(q is not None and q.is_relative_to(root),'unresolved/escaped include '+rel);visit(q)
  need(not stack,'unterminated conditional');visiting.pop()
 for p in sources:visit(p)
 return len(seen)
