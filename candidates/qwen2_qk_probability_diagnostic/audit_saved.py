"""Read-only persisted-array bit audit. No numerical runtime or model call."""
import argparse
import ast
from array import array
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
from candidates.qwen2_qk_probability_diagnostic import model

OUT=model.ROOT/'work/qwen2_qk_probability_diagnostic/local01'

def read_arrays(path):
    arrays={}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            with archive.open(name) as f:
                model.need(f.read(6)==b'\x93NUMPY','numpy format')
                version=f.read(2)
                size=struct.unpack('<H' if version[0]==1 else '<I',f.read(2 if version[0]==1 else 4))[0]
                header=ast.literal_eval(f.read(size).decode())
                model.need(header['descr']=='<f4' and not header['fortran_order'],'saved array format')
                words=array('I');words.frombytes(f.read())
                if sys.byteorder!='little':words.byteswap()
                count=1
                for d in header['shape']:count*=d
                model.need(len(words)==count,'saved array extent')
                arrays[name[:-4]]=(header['shape'],words)
    return arrays

def run(execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    target=OUT/'BIT_AUDIT.json';model.need(not target.exists(),'fresh bit audit')
    path=OUT/'LOCAL_ARRAYS.npz';identity=model.sha(path)
    arrays=read_arrays(path)
    pairs={
      'OFFICIAL_INPUT_CURRENT_QK':('official_input_current_score','official_score'),
      'HISTORICAL_INPUT_CURRENT_QK_VS_OFFICIAL_INPUT':('historical_input_current_score','official_score'),
      'HISTORICAL_INPUT_OFFICIAL_QK_VS_OFFICIAL_INPUT':('historical_input_official_score','official_score'),
      'HISTORICAL_INPUT_CURRENT_QK':('historical_input_current_score','historical_input_official_score'),
      'OFFICIAL_INPUT_CURRENT_DOT':('official_input_current_dot','official_dot'),
      'HISTORICAL_INPUT_CURRENT_DOT':('historical_input_current_dot','historical_input_official_dot')}
    indices=[(h*128+t)*128+k for h in range(12) for t in range(128) for k in range(t+1)]
    result={}
    for name,(a,b) in pairs.items():
        model.need(arrays[a][0]==arrays[b][0]==(12,128,128),'QK array geometry')
        aw,bw=arrays[a][1],arrays[b][1]
        diff=sum(aw[i]!=bw[i] for i in indices)
        signed_zero=sum((aw[i]!=bw[i]) and not ((aw[i]|bw[i])&0x7fffffff) for i in indices)
        result[name]={'count':len(indices),'bit_diff_count':diff,'signed_zero_bit_diff_count':signed_zero}
    report=json.loads((OUT/'RESULT.json').read_text())
    tops=[x for x in report['worst_scores'] if x['abs_error']==8.0]
    def bf_steps(a,b):
        aw=struct.unpack('<I',struct.pack('<f',a))[0];bw=struct.unpack('<I',struct.pack('<f',b))[0]
        return abs((aw>>16)-(bw>>16))
    score_steps=[bf_steps(x['a'],x['b']) for x in tops]
    dot_steps=[bf_steps(x['current_bf16_dot'],x['official_bf16_dot']) for x in tops]
    public={'status':'SAVED_ARRAY_UINT32_AUDIT_COMPLETE','comparisons':result,
      'max_score_error_count':len(tops),'max_score_error_bf16_steps':max(score_steps),
      'max_score_error_dot_bf16_steps':max(dot_steps),
      'max_score_error_class':'ONE_DOT_BF16_STEP_TO_TWO_SCORE_BF16_STEPS',
      'qk_arithmetic_verification':'NATIVE_BATCH_VS_ORIGINAL_OWNER_AST_WORDS',
      'full_owner_protocol':'NOT_EXECUTED'}
    details={}
    for name,official in [('historical_q','official_q'),('historical_k','official_k')]:
        shape,aw=arrays[name];bw=arrays[official][1]
        details[name]=[{'flat_index':i,'historical_bits':x,'official_bits':y}
                        for i,(x,y) in enumerate(zip(aw,bw)) if x!=y]
    model.need(model.sha(path)==identity,'saved arrays changed')
    target.write_text(json.dumps({'public':public,'input_sha256':identity,
        'source_sha256':model.sha(Path(__file__)),'input_differences':details},indent=2,sort_keys=True)+'\n')
    (OUT/'SAFE_BIT_AUDIT.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    print(json.dumps(public,sort_keys=True));return public

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    run(a.execute)
