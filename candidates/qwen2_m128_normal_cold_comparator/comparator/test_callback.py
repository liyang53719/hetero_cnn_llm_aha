"""One synthetic full-shape callback, no target imports/native/original inputs."""
from array import array
import importlib.util
from pathlib import Path
import json
import struct
import tempfile
from types import SimpleNamespace
import unittest
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('comparison',HERE/'comparator.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def w(x):return struct.unpack('<I',struct.pack('<f',x))[0]
class FullShape(unittest.TestCase):
 def test_callback_and_capture_negatives(self):
  r=128; actual={n:array('I',[0])*(r*v) for n,v in c.WIDTHS.items()}
  actual.update({n:array('I',[0])*(r*v) for n,v in {'qraw':1536,'kraw':256,'vraw':256,'kv':512}.items()})
  fields={}
  for name in c.ATTENTION_FIELDS:
   causal=name not in ('normalizer','pv_raw','pv_bf16')
   width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
   shape=[12,r,r,16] if name=='dot_parts' else [12,r,width] if not causal else [12,r,r]
   count=c.math.prod(shape);a=array('I',[0xa5963cc3])*count;observed=bytearray(count);freq=array('H',[0])*count
   for i in range(count):
    at=i//width;t=(at//r)%r
    if not causal or at%r<=t:
     observed[i]=1;freq[i]=8 if name in ('prob_bf16','softmax_fp32') else 1
     a[i]=w(1/(t+1)) if name=='softmax_fp32' else 0
   fields[name]={'shape':shape,'words':a,'observed':observed,'frequency':freq}
  obs={'capture':SimpleNamespace(data=SimpleNamespace(fields=fields))}
  extra=dict(readonly_x=bytes(r*1536*4),sealed_silu=bytes(r*8960*4),x_shape=[r,1536],silu_shape=[r,8960],rope_operands={'cos':bytes(r*64*4),'sin':bytes(r*64*4)},rope_physical_shape=[r,64],provenance='ORIGINAL_READONLY_ALLOCATION_AND_ORIGINAL_PHASE4_SEAL')
  reg=dict(whole_terminal=True,resources_clean=True,rows=r,status='COMPLETE_ACTUAL_INVENTORY_NUMERIC_TEMP',entries={n:{'raw_sha256':c.sha(v)} for n,v in actual.items()})
  reg['entries']['silu']={'raw_sha256':c.sha(extra['sealed_silu'])}
  reg['entries'].update({n:{'raw_sha256':c.sha(v['words']),'presence_sha256':c.sha(v['observed']),'frequency_sha256':c.sha(v['frequency'])} for n,v in fields.items()})
  reg['entries'].update(cache_k={},cache_v={})
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);ex={}
   for n in c.NODES:
    raw=fields['softmax_fp32']['words'].tobytes() if n=='softmax_fp32' else bytes(c.math.prod(c.shape(n,r))*4)
    # Future ref probabilities are true zeros; actual future remains sentinel.
    if n=='softmax_fp32':
     a=array('I');a.frombytes(raw)
     for i in range(len(a)):
      if i%r>(i//r)%r:a[i]=0
     raw=a.tobytes()
    ex[n]=dict(shape=c.shape(n,r),native_dtype='float32' if n=='softmax_fp32' else 'bfloat16',fp32_file=n+'.f32.bin',fp32_bytes=len(raw),fp32_sha256=c.sha(raw));(root/(n+'.f32.bin')).write_bytes(raw)
   reads=0
   def guard():
    nonlocal reads;reads+=1
   cb=c.make_comparator(root,ex,terminal_guard=guard)
   result=cb(actual,obs,reg,terminal_values=extra)
   self.assertTrue(result['observed_domain_passed']);self.assertFalse(result['full29_numeric_pass']);self.assertEqual(result['nodes']['scores']['compared_elements'],99072);self.assertEqual(result['nodes']['scores']['unobserved_elements'],97536);self.assertEqual(reads,27)
   (HERE/'SYNTHETIC_RESULT_R2.json').write_text(json.dumps(result,indent=2)+'\n')
   for key,idx,field in [('prob_bf16',0,'frequency'),('scores_bf16',1,'observed')]:
    old=fields[key][field][idx];fields[key][field][idx]=9
    with self.assertRaisesRegex(ValueError,'capture|digest'):
     c.make_comparator(root,ex,terminal_guard=guard)(actual,obs,reg,terminal_values=extra)
    fields[key][field][idx]=old
   old=actual['y'][0];actual['y'][0]=0x3f800000
   with self.assertRaisesRegex(ValueError,'registry .*digest'):
    c.make_comparator(root,ex,terminal_guard=guard)(actual,obs,reg,terminal_values=extra)
   actual['y'][0]=old
if __name__=='__main__':unittest.main()
