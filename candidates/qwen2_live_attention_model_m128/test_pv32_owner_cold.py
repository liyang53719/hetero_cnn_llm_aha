"""No numeric imports: source-bound unchanged QK/softmax and lifecycle structure."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
NEW=ROOT/'candidates/qwen2_live_attention_model_m128/pv32_owner.py'
OLD=ROOT/'candidates/qwen2_resident_matrix/official_bf16/owners.py'
def attention(path,name):
    cls=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.ClassDef) and x.name==name)
    return next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='_attention')
class ColdOwner(unittest.TestCase):
    def test_qk_softmax_ast_exact(self):
        old=attention(OLD,'OfficialAttentionOwner');new=attention(NEW,'OfficialPV32AttentionOwner')
        def without_pv(node):
            body=node.body[0].body[0].body
            pv=[i for i,x in enumerate(body) if isinstance(x,ast.For) and isinstance(x.target,ast.Name) and x.target.id=='col']
            self.assertEqual(len(pv),1)
            body[pv[0]:pv[0]+1]=[]
            return ast.dump(node,include_attributes=False)
        self.assertEqual(without_pv(old),without_pv(new))
    def test_one_base_tick_call(self):
        cls=next(n for n in ast.parse(NEW.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='OfficialPV32AttentionOwner')
        tick=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick')
        calls=[n for n in ast.walk(tick) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='tick']
        self.assertEqual(len(calls),1)
    def test_two_ack_marker_and_single_16_hold(self):
        source=NEW.read_text();self.assertIn('self.ack_bytes==self.pv32_ack_at_borrow+128',source)
        self.assertIn('for half in (0,16):',source);self.assertIn('for i in range(16))',source)
        self.assertNotIn('lanes=tuple',source)
if __name__=='__main__':unittest.main()
