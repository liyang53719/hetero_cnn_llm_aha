import os
import ast
import hashlib
from pathlib import Path
import sys
import unittest
from router_local_observer import LocalReturnObserver,OFFICIAL_SOURCE_SHA256
class Fixture:
 def __init__(self):self.actual=object();self.result=(object(),object(),object());self.order=[]
 def forward(self, x):
  self.order.append('linear');self.order.append('softmax');router_probs=self.actual
  self.order.append('topk');self.order.append('normalize');return self.result
class Observer(unittest.TestCase):
 def test_same_objects_and_unmodified_order(self):
  f=Fixture();o=LocalReturnObserver(f,Fixture.forward);code=Fixture.forward.__code__
  with o: result=f.forward(object())
  self.assertIs(result,f.result);self.assertIs(o.events[0][0],f.actual);self.assertIs(o.events[0][1],result)
  self.assertEqual(f.order,['linear','softmax','topk','normalize']);self.assertIs(Fixture.forward.__code__,code);self.assertIsNone(sys.getprofile())
 def test_only_exact_instance(self):
  f=Fixture();other=Fixture();o=LocalReturnObserver(f,Fixture.forward)
  with o: other.forward(None);f.forward(None)
  self.assertEqual(len(o.events),1)
 def test_cleanup_exception(self):
  o=LocalReturnObserver(Fixture(),Fixture.forward)
  with self.assertRaisesRegex(RuntimeError,'original'):
   with o:raise RuntimeError('original')
  self.assertIsNone(sys.getprofile())
 def test_original_exception_retained_with_profiler_conflict(self):
  o=LocalReturnObserver(Fixture(),Fixture.forward)
  with self.assertRaisesRegex(RuntimeError,'original'):
   with o:
    sys.setprofile(None)
    raise RuntimeError('original')
  self.assertIsNone(sys.getprofile())
 def test_existing_instrumentation_not_overwritten(self):
  callback=lambda *args:None
  sys.setprofile(callback)
  try:
   with self.assertRaises(ValueError):
    with LocalReturnObserver(Fixture(),Fixture.forward):pass
   self.assertIs(sys.getprofile(),callback)
  finally:sys.setprofile(None)
 def test_exact_upstream_original_probs_assignment_only(self):
  p=Path(os.environ['OFFICIAL_MODEL_SOURCE'])
  self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),OFFICIAL_SOURCE_SHA256)
  tree=ast.parse(p.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen3_5MoeTopKRouter');f=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='forward')
  stores=[n for n in ast.walk(f) if isinstance(n,ast.Name) and n.id=='router_probs' and isinstance(n.ctx,ast.Store)]
  self.assertEqual(len(stores),1)
  loads=[n for n in ast.walk(f) if isinstance(n,ast.Name) and n.id=='router_probs' and isinstance(n.ctx,ast.Load)]
  self.assertEqual(len(loads),1)
  topk=f.body[3].value;self.assertEqual(ast.unparse(topk.func),'torch.topk');self.assertEqual(ast.unparse(topk.args[0]),'router_probs')
 def test_wrapper_still_checks_baseline_and_cache_before_save(self):
  t=Path(__file__).with_name('run_reference.py').read_text()
  self.assertLess(t.index('require(raw(observed) == baseline_bytes'),t.index('router_observer.take(torch)'))
  self.assertLess(t.index('== baseline_state_bytes'),t.index('router_observer.take(torch)'))
if __name__=='__main__':unittest.main()
