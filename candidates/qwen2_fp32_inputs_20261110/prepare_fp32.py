"""Materialize pinned Qwen2 L0 tensors in original FP32 storage. No model execution.
Input token IDs 0..127 use exact trained embedding rows; no normalized/QKV or
other intermediate values are supplied. Output payloads remain local.
"""
from pathlib import Path
import argparse,hashlib,json,numpy as np

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def lift(raw):
    return (np.frombuffer(raw,dtype='<u2').astype('<u4') << np.uint32(16)).astype('<u4').tobytes()
def prepare(raw_dir,out):
    pins=json.loads(Path(__file__).with_name('RAW13_PINS.json').read_text())
    # Validate ALL inputs before creating any output. Never truncate a prior run.
    for t in pins['tensors']:
        p=raw_dir/(t['name']+'.bin')
        if p.stat().st_size!=t['bytes'] or sha(p)!=t['sha256']:
            raise ValueError('input hash/size mismatch: '+t['name'])
    out.mkdir(exist_ok=False,parents=True); result=[]
    for t in pins['tensors']:
        raw=(raw_dir/(t['name']+'.bin')).read_bytes(); data=lift(raw)
        name=t['name'];shape=t['shape']
        if name=='embed_tokens.rows_0_255':
            name='input.tokens_0_127';shape=[128,1536];data=data[:128*1536*4]
        target=out/(name+'.f32le');target.write_bytes(data)
        # Exact bit-lift, not numerical cast/FMA/rounding or BF16 activation replacement.
        words=np.frombuffer(data,dtype='<u4'); original=np.frombuffer(raw,dtype='<u2')[:len(words)]
        if not (np.all((words&65535)==0) and np.array_equal(words>>16,original)):
            raise ValueError('non-reversible FP32 lift: '+name)
        result.append(dict(name=name,shape=shape,bytes=len(data),sha256=sha(target),dtype='FP32_LE',layout='row_major_original_checkpoint',original_name=t['name']))
    summary=dict(status='PASS_INPUT_BYTES_ONLY',tokens=128,token_ids='0..127',model=pins['model'],revision=pins['revision'],layer=0,tensors=result,full_block_pass=False,reference_forward_executed=False,chisel_executed=False,rtl_executed=False,weights_or_data_publish_allowed=False)
    (out/'INPUT_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.raw_dir,a.output),indent=2))
