#!/usr/bin/env python3
"""Exact golden memoization ONLY for position-independent layer0 norm/QKV.

The RTL must still execute all1024 rows. Never reuse this for RoPE/attention.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'work/results/qwen2_q1024_projection_fixtures'
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
TOKEN_HASH = 'e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_beats(path, width):
    lines = path.read_text().splitlines()
    assert len(lines) == 16*width//32, f'wrong shape: {path}'
    for line in lines:
        assert len(line) == 128 and 0 <= int(line,16) < 1 << 512
    return [tuple(lines[r*width//32:(r+1)*width//32]) for r in range(16)]


def main():
    tokens_path = ROOT/'work/results/llama_cpp_qwen2_baseline/tokens.txt'
    tokens = [int(x) for x in tokens_path.read_text().split()]
    assert len(tokens) == 1024
    assert hashlib.sha256(struct.pack('<1024i', *tokens)).hexdigest() == TOKEN_HASH
    pairs = [
        ('work/results/qwen2_canonical_tile16_vectors', 'work/results/qwen2_canonical_q_tile16_all'),
        ('work/results/qwen2_true_rows16_31', 'work/results/qwen2_true_rows16_31_projection'),
    ]
    widths = {'norm':1536, 'q':1536, 'k':256, 'v':256}
    cache = {kind:{} for kind in widths}
    hashes = {}; weights = {}; repeated_checks = 0
    for batch,(norm_dir,proj_dir) in enumerate(pairs):
        norm_dir=ROOT/norm_dir;proj_dir=ROOT/proj_dir
        manifest=json.loads((norm_dir/'result.json').read_text())
        projection_manifest=json.loads((proj_dir/'result.json').read_text())
        assert manifest['revision']==REVISION and manifest['token_start']==batch*16
        assert manifest['token_ids']==tokens[batch*16:(batch+1)*16]
        assert projection_manifest['token_start']==batch*16
        assert projection_manifest['token_slice_sha256']==manifest['token_slice_sha256']
        assert hashlib.sha256(struct.pack('<16i',*manifest['token_ids'])).hexdigest()==manifest['token_slice_sha256']
        for path in (norm_dir/'result.json',proj_dir/'result.json'):
            hashes[str(path.relative_to(ROOT))]=digest(path)
        for kind,width in widths.items():
            path=norm_dir/'norm_token_major.memh' if kind=='norm' else proj_dir/f'{kind}_expected_token_major.memh'
            hashes[str(path.relative_to(ROOT))]=digest(path)
            if kind=='norm':
                assert digest(path)==manifest['files'][path.name]
            else:
                weight=proj_dir/f'{kind}_weight_ddr_beats.memh'
                hashes[str(weight.relative_to(ROOT))]=digest(weight)
                if kind in weights: assert weights[kind]==digest(weight), 'weight mismatch across golden batches'
                weights[kind]=digest(weight)
            rows=row_beats(path,width)
            for token,row in zip(manifest['token_ids'],rows):
                if token in cache[kind]:
                    assert cache[kind][token]==row, f'position dependence or inconsistent golden: {kind}/{token}'
                    repeated_checks+=1
                cache[kind][token]=row
    OUT.mkdir(parents=True,exist_ok=True)
    output={}
    for kind,width in widths.items():
        missing=set(tokens)-cache[kind].keys()
        assert not missing, f'need independently generated golden tokens: {missing}'
        path=OUT/f'{kind}_token_major.memh'
        with path.open('w') as stream:
            for token in tokens:
                stream.write(''.join(line+'\n' for line in cache[kind][token]))
        output[kind]={'path':str(path.relative_to(ROOT)), 'rows':1024, 'columns':width,
                      'beats':1024*width//32, 'sha256':digest(path)}
    result=dict(status='PASS_Q1024_LAYER0_PROJECTION_FIXTURES_ONLY',revision=REVISION,
        tokens_sha256=TOKEN_HASH,rows=1024,unique_tokens=len(set(tokens)),
        reference_token_positions=list(range(32)),repeated_row_consistency_checks=repeated_checks,
        source_sha256=hashes,output=output,
        golden_method='exact token-ID memoization of position-independent layer0 norm and raw projections',
        forbidden_reuse=['RoPE','attention','later-layer hidden states'],
        rtl_q1024_numerical_pass=False)
    (OUT/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    (ROOT/'reports/execution/Q1024_PROJECTION_FIXTURES_RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('status','rows','unique_tokens','repeated_row_consistency_checks')}))


if __name__=='__main__':
    main()
