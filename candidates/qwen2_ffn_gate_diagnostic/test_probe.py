import ast
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from . import probe as p


class ColdTests(unittest.TestCase):
    def test_default_is_cold(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('unexpected read')):
            self.assertEqual(p.run(), {'status':'NOT_EXECUTED'})
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('numpy', sys.modules)

    def test_original_gate_source(self):
        self.assertEqual(p.source_check(), p.SOURCE_PINS)

    def test_fixed_bounds(self):
        self.assertEqual((p.ROWS,p.K,p.WIDTH,p.NCOLS),(128,1536,8960,32))
        self.assertEqual(p.WINDOWS,(0,4480,8928))
        self.assertTrue(all(ng%32==0 and ng+32<=8960 for ng in p.WINDOWS))
        self.assertEqual((p.CPU_SECONDS,p.AS_BYTES,p.OUTPUT_BYTES),(120,4<<30,64<<20))

    def test_original_constructor_only(self):
        pins=json.loads((p.ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_text())
        node=p.gate_constructor(pins['model_ast_nodes'])
        self.assertEqual(ast.unparse(node),'self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)')
        specs=p.raw_specs(pins)
        self.assertEqual(len(specs),11)
        self.assertNotIn('mlp.up_proj.weight',specs)
        self.assertNotIn('mlp.down_proj.weight',specs)

    def test_audit_refuses_historical_payload(self):
        a=p.payload_audit([p.PREFIX/'input_layernorm.weight.bin'],p.OUT)
        for path in ('work/qwen2_fresh_reference_recovery_m128/recovered01/frozen/n1.f32le',
                     'work/qwen2_fullblock_recovery_numeric_m128_20261015/attempt01/n1.f32le',
                     'work/private_ci_dut/gate.f32le'):
            with self.assertRaises(ValueError): a('open',(str(p.ROOT/path),'r',0))
        a('open',(str(p.PREFIX/'input_layernorm.weight.bin'),'r',0))
        a('open',(str(p.OUT/'selected.f32le'),'w',0))
        with self.assertRaises(ValueError): a('open',(str(p.HERE/'oops.py'),'w',0))
        with self.assertRaises(ValueError): a('subprocess.Popen',())

    def test_ast_stops_before_mlp(self):
        tree=ast.parse((p.HERE/'probe.py').read_text())
        method=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='official_to_n1')
        calls=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(any(n.func.attr in ('up_proj','down_proj','mlp') for n in calls))
        self.assertEqual(sum(n.func.attr=='gate_proj' for n in calls),1)


if __name__=='__main__': unittest.main()
