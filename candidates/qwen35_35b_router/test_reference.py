"""Cold source/producer gates; no Torch or downloaded router payload."""
import ast, hashlib, json, tempfile, unittest
from pathlib import Path
from . import reference as r

class ReferenceTests(unittest.TestCase):
    def test_original_complete_router_and_operation_order(self):
        c=r.definition();f=next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='forward')
        self.assertEqual([n.lineno for n in f.body],list(range(846,854)))
        text=ast.unparse(f)
        self.assertIn('F.linear(hidden_states, self.weight)',text)
        self.assertIn('softmax(router_logits, dtype=torch.float, dim=-1)',text)
        self.assertIn('torch.topk(router_probs, self.top_k, dim=-1)',text)
        self.assertIn('router_top_value /= router_top_value.sum(dim=-1, keepdim=True)',text)
        self.assertIn('router_top_value.to(router_logits.dtype)',text)
    def test_producer_is_pinned_actual_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p=d/'post_attention_norm.actual.bf16le';p.write_bytes(bytes(16*2048*2));h=r.sha(p.read_bytes())
            s=dict(tokens=16,sources_unchanged=True,native_artifacts_unchanged=True,observations=[dict(stage='post_attention_norm',output=dict(path=str(p),sha256=h),owner=dict(complete=True,output_published=True,status=None,output_sha256=h))])
            sp=d/'summary.json'
            def write():sp.write_text(json.dumps(s));return r.sha(sp.read_bytes())
            digest=write();self.assertEqual(r.producer(d,digest,16)[0],p.read_bytes())
            with self.assertRaisesRegex(ValueError,'summary pin'):r.producer(d,'0'*64,16)
            s['observations'][0]['owner']['output_published']=False
            with self.assertRaisesRegex(ValueError,'published'):r.producer(d,write(),16)
            s['observations'][0]['owner']['output_published']=True;digest=write();p.write_bytes(b'X'+p.read_bytes()[1:])
            with self.assertRaisesRegex(ValueError,'bytes'):r.producer(d,digest,16)
if __name__=='__main__':unittest.main()
