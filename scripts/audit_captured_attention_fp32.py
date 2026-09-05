#!/usr/bin/env python3
"""Read-only scan of completed partitions with real IEEE754 FP32 conversion."""
import hashlib,json,math,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    directory=ROOT/'work/results/q1024_captured_attention_payload'
    refpath=ROOT/'work/results/q1024_post_projection/attention_vectors/expected_fp32.memh'
    ref=[int(x,16) for x in refpath.read_text().splitlines()];refhash=sha(refpath)
    parts=[];total=0;maximum=0.0
    def f(w):return struct.unpack('<f',struct.pack('<I',w))[0]
    for path in sorted(directory.glob('qt[0-9][0-9].json')):
        r=json.loads(path.read_text())
        if r['status']!='PASS':continue
        assert r['identity'][str(refpath.relative_to(ROOT))]==refhash
        p=Path(r['output']);assert sha(p)==r['output_sha256']
        words=[int(x,16) for x in p.read_text().splitlines()];assert len(words)==24576
        error=0.0
        for i,w in enumerate(words):
            h=i//2048;row=(i//128)%16;d=i%128
            a=f(w);b=f(ref[(h*1024+r['qt']*16+row)*128+d]);assert math.isfinite(a) and math.isfinite(b)
            error=max(error,abs(a-b))
        assert error<=0.002,(r['qt'],error)
        parts.append(dict(qt=r['qt'],max_error=error,output_sha256=sha(p),receipt_sha256=sha(path)))
        total+=len(words);maximum=max(maximum,error)
    result=dict(status='PASS_COMPLETED_PARTITIONS_ONLY',partitions=parts,compared_fp32=total,
                max_error=maximum,threshold=0.002,expected_sha256=refhash,full1024_complete=len(parts)==64,
                supersedes='Verilator shortreal-based floating tolerance check is invalid; hashes and independent bit-exact checks unaffected')
    (ROOT/'reports/execution/Q1024_ATTENTION_INDEPENDENT_FP32_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','compared_fp32','max_error','full1024_complete']}))
if __name__=='__main__':main()
