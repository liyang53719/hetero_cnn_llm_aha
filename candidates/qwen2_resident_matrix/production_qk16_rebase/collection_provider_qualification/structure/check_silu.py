"""Restricted CHIRRTL assignment/register checks, not whole-design loop proof."""
import re
from pathlib import Path
def need(ok,msg):
 if not ok:raise ValueError(msg)
def check_text(text):
 modules={};current=None
 for line in text.splitlines():
  m=re.match(r'  (?:ext)?module (\w+)\s*:',line)
  if m:
   current=m[1];need(current not in modules,'duplicate module');modules[current]=[]
  elif current:modules[current].append(line.split(' @[')[0])
 def lines(name):need(name in modules,'missing '+name);return modules[name]
 def reg(name,r):need(any(re.fullmatch(r'    regreset '+re.escape(r)+r' : UInt<1>, clock, reset, UInt<1>\(0h0\)',l) for l in lines(name)),'registered '+name+'.'+r)
 def assignment(name,target):
  ls=lines(name);nodes={};connects=[]
  for l in ls:
   m=re.match(r'    node (\w+) = (.+)$',l)
   if m:need(m[1] not in nodes,'duplicate node');nodes[m[1]]=m[2]
   m=re.match(r'\s*(?:connect|invalidate) ([\w.\[\]]+)(?:, (.+))?$',l)
   if m:
    t=m[1];overlap=t==target or t.startswith(target+'.') or t.startswith(target+'[') or target.startswith(t+'.') or target.startswith(t+'[')
    if overlap:connects.append((l,m[1],m[2]))
  need(len(connects)==1,'unique target '+target);l,t,rhs=connects[0]
  need(l.startswith('    connect ') and not l.startswith('     ') and t==target and rhs is not None,'unconditional leaf '+target)
  def expand(v,seen=()):
   if v in nodes:need(v not in seen,'node cycle');return expand(nodes[v],seen+(v,))
   return re.sub(r'[A-Za-z_][\w.\[\]]*',lambda m:expand(m[0],seen) if m[0] in nodes else m[0],v)
  return rhs,expand(rhs)
 name='FfnTileSiluBridge';reg(name,'poison')
 need(assignment(name,'io.silu.abort')[1]=='or(io.abort, poison)','SFU abort only external or registered poison')
 need(assignment(name,'io.tiles.abort')[0]=='bad','tile abort stays bad')
 name='FfnResidentCoordinator';reg(name,'poison');need(assignment(name,'bridge.io.abort')[1]=='or(io.group.abort, poison)','resident registered cut')
 name='Public21QkvReductionRouter';reg(name,'fault');need(assignment(name,'io.resident.abort')[1]=='or(or(fault, io.residentHost.abort), io.backendReset)','router registered cut')
 name='TransposedDownDenseBanks';reg(name,'poison');reg(name,'responseValid');need(assignment(name,'io.tiles.response.valid')[1]=='responseValid','bank valid reg');need(assignment(name,'io.tiles.resetRequired')[1]=='poison','bank reset reg')
 name='VectorSiluOwner';reg(name,'loanPoison');need(assignment(name,'io.loan.resetRequired')[1]=='loanPoison','SFU reset reg')
 return {'single_sfu_abort_external_or_registered_poison':True,'tiles_abort_still_bad':True,'checked_register_cuts':5,'whole_design_no_combination_cycle_proven':False}
def check(path):return check_text(Path(path).read_text())
