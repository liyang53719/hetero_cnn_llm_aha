"""Pure Python source-contract oracle. Never a generated binding or RTL evidence."""
import re,types
from pathlib import Path
SOURCE=Path(__file__).with_name('silu_observer.hpp').read_text()
FIELDS=('raw_valid','resident_selected','group_matched','loan_matched','context_active','context_poison','context_abort','router_bad','bridge_bad','group_abort','group_reset','input_binary_add','vector_issue','phase_five','all_ready','vector_error','operands_match')
POSITIVE={'raw_valid','resident_selected','group_matched','loan_matched','context_active','vector_issue','phase_five','all_ready','operands_match'}
EXPR=re.search(r'inline bool qualified\(const Qualification& q\)\s*\{\s*return ([^;]+);',SOURCE).group(1)
EXPR=EXPR.replace('&&',' and ').replace('||',' or ');EXPR=re.sub(r'!(?!=)',' not ',EXPR)
CODE=compile(EXPR,'<exact C++ qualified expression>','eval')
def need(ok,message):
 if not ok:raise ValueError(message)
def guard(fields):
 need(type(fields)is dict and set(fields)==set(FIELDS),'exact guard fields')
 need(all(type(v)is bool for v in fields.values()),'exact boolean observations')
 return eval(CODE,{'__builtins__':{}},{'q':types.SimpleNamespace(**fields)})
def good_guard():return {n:n in POSITIVE for n in FIELDS}
def key(k,slot,ng,index):
 need(type(k)is tuple and len(k)==4 and all(type(x)is int for x in k),'exact cold key types')
 need(k==((7<<16)|17,ng,index,slot) and ng in range(0,8960,160) and 0<=index<1280,'key identity/slot/ng/index')
def coordinate(k,lane):
 key(k,1,k[1],k[2]);need(type(lane)is int and 0<=lane<16,'lane')
 return (0,(k[2]//160)*16+lane,k[1]+k[2]%160)
class Trace:
 """Small contract examples only; mirrors ordering, never emits actual data."""
 def __init__(self):self.loan=None;self.read=None;self.gate=None;self.raw=False;self.fatal=False;self.count=0
 def require_alive(self):need(not self.fatal,'sticky failure')
 def fail(self):self.fatal=True;raise ValueError('invalid cold trace')
 def accept_read(self,k):
  self.require_alive()
  try:key(k,0 if self.gate is None else 1,0,0);need(self.read is None and self.loan is None,'unique read');self.read=k
  except ValueError:self.fail()
 def response(self,k,payload,loan_fires=None,loan_payloads=None):
  self.require_alive()
  try:
   need(self.read is not None and k==self.read,'prior read identity');self.read=None
   need(type(payload)is tuple and len(payload)==16,'16 raw words')
   if k[3]==0:need(loan_fires is None,'gate not loan');self.gate=payload
   else:
    need(self.gate is not None and loan_fires==(True,)*5,'five actual path fires')
    need(loan_payloads==((self.gate,payload),)*5,'same actual gate/up words')
    self.loan=k
  except ValueError:self.fail()
 def capture(self,fields):
  self.require_alive()
  try:need(self.loan is not None and not self.raw and guard(fields),'matched one raw');self.raw=True;self.count+=1
  except ValueError:self.fail()
 def result(self):
  self.require_alive()
  try:need(self.loan is not None and self.raw,'cannot substitute product for intermediate');self.loan=None
  except ValueError:self.fail()
 def coverage(self):
  self.require_alive()
  try:need(self.loan is None and self.read is None and self.count==71680,"complete coverage")
  except ValueError:self.fail()
 def abort(self):self.fail()
