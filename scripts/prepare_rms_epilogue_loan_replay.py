#!/usr/bin/env python3
"""Prepare local-only RTL replay operands from a sealed actual postnorm run.

No arithmetic oracle is recomputed: expected FP32/BF16 values were observed at
actual Scalar-owner boundaries. Checkpoint-derived files must never enter Git.
"""
import argparse, hashlib, json, struct
from pathlib import Path

def require(ok, why):
    if not ok: raise ValueError(why)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def checked(rec):
    raw=Path(rec['path']).read_bytes()
    require(len(raw)==rec['bytes'] and sha(raw)==rec['sha256'],'record identity '+rec['path'])
    return raw

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    raw=a.summary.read_bytes();require(sha(raw)==a.sha256,'summary SHA')
    s=json.loads(raw);m=s['tokens'];require(m in (16,128),'actual M16/M128')
    require(s['sources_unchanged'] and s['source_sha256']==s['source_sha256_after'] and s['native_artifacts_unchanged'],'sealed actual sources')
    for path,digest in s['source_sha256'].items():require(sha(Path(path).read_bytes())==digest,'current producer source '+path)
    for rec in s['native_artifact_records']:checked(rec)
    terminals=s['execution']['terminals']
    require(len(terminals)==13 and all(x['status'] is None for x in terminals),'13 successful actual terminals')
    require(s['execution']['same_rms_owner_and_banks_reused'],'actual shared bank identity')
    obs={x['stage']:x for x in s['observations']}
    require(len(obs)==16,'complete observed prefix')
    residual=checked(obs['attention_residual']['output'])
    require(len(residual)==m*2048*2,'residual BF16 shape')
    x=struct.pack('<'+'I'*(m*2048),*(v[0]<<16 for v in struct.iter_unpack('<H',residual)))
    weights=checked(s['postnorm_reference_records']['weight_fp32'])
    words=[v[0] for v in struct.iter_unpack('<I',weights)]
    require(len(words)==2048 and all(v&65535==0 for v in words),'exact BF16-expanded weight')
    original=struct.pack('<2048H',*(v>>16 for v in words))
    require(sha(original)==s['execution']['postnorm_weight_sha256'],'actual owner checkpoint weight identity')
    def actual(name):
        rec=s['postnorm_actual_nodes'][name]
        require(rec['actual_observed'] is True,'actual node, not reconstructed formula')
        return checked(rec['actual'])
    inverse=actual('inverse');expected=actual('weighted')
    expected_bf16=checked(obs['post_attention_norm']['output'])
    require(len(inverse)==m*4 and len(expected)==m*2048*4 and len(expected_bf16)==m*2048*2,'actual node shapes')
    require(not a.out.exists(),'fresh output directory');a.out.mkdir(parents=True)
    files={'x.fp32le':x,'weights.fp32le':weights,'inverse.fp32le':inverse,'expected.fp32le':expected,'expected.bf16le':expected_bf16}
    records={}
    for name,data in files.items():
        (a.out/name).write_bytes(data);records[name]=dict(bytes=len(data),sha256=sha(data))
    report=dict(scope='LOCAL_FROZEN_ACTUAL_POSTNORM_EPILOGUE_STIMULUS_ONLY',tokens=m,width=2048,lanes=16,transactions=m*128,
        summary=dict(path=str(a.summary.resolve()),sha256=a.sha256),files=records,expected_source='actual owner FP32 weighted and BF16 output observations',
        scalar_source_unchanged=True,full_block=False,rtl_executed=False,script_sha256=sha(Path(__file__).read_bytes()))
    (a.out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(tokens=m,transactions=m*128,manifest_sha256=sha((a.out/'manifest.json').read_bytes()))))
if __name__=='__main__':main()
