"""Cold timer forwarding and registered-callback isolation; no arithmetic."""
import ast,inspect,unittest
from pathlib import Path
from .budget_probe import Timer,main
class BudgetCold(unittest.TestCase):
 def test_explicit_frame_identity_and_return(self):
  timer=Timer();seen=[];frame=object()
  def body(value):seen.append(value);return value
  callback=timer.wrap_frame_body(body)
  self.assertEqual(list(inspect.signature(callback).parameters),['frame'])
  for enabled in (False,True):
   timer.enabled=enabled;self.assertIs(callback(frame),frame)
  self.assertTrue(all(value is frame for value in seen));self.assertEqual(timer.calls['observer_line_body'],1)
 def test_registered_callbacks_not_replaced(self):
  tree=ast.parse(Path(__file__).with_name('budget_probe.py').read_text())
  attributes=[x.attr for n in ast.walk(tree) if isinstance(n,(ast.Assign,ast.AugAssign)) for x in ast.walk(n.targets[0] if isinstance(n,ast.Assign) else n.target) if isinstance(x,ast.Attribute)]
  self.assertNotIn('_line_callback',attributes);self.assertNotIn('_return_callback',attributes)
 def test_default_no_runtime(self):
  self.assertEqual(main([]),0)
if __name__=='__main__':unittest.main()
