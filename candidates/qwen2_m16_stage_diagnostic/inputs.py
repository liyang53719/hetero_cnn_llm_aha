"""Fixed recovered raw identities; only x has a declared leading-token slice."""
import hashlib,json
from pathlib import Path
from .geometry import need,ROWS,H,ROPE_BYTES
ROOT=Path(__file__).resolve().parents[2]
ROLES={'bk': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/bk.bin', 'bytes': 1024, 'sha256': 'c77424743b1f69c60e2de1b4780666973af58831169c3ee02d7443701bc6d03d'}, 'bq': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/bq.bin', 'bytes': 6144, 'sha256': '47506ca51cfd69119a774c09466b718c0b400b84b9a392bc1e9bcb691f28b72d'}, 'bv': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/bv.bin', 'bytes': 1024, 'sha256': 'e0ba90f0d591f0266f0140802b6e4ccc24a9961ef26e96ee00f5b1567f8b2f70'}, 'gamma0': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/gamma0.bin', 'bytes': 6144, 'sha256': '320e4ac88269676897cf9c3b4996f966a6100ced2bc0f684216c200bc82b7180'}, 'rope': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/rope.bin', 'bytes': 524288, 'sha256': 'f6c6e15e3f480afe2e9ebfb05719ff8d20a77a5a5551aa8a44bf2a49870d77af'}, 'wk': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/wk.bin', 'bytes': 786432, 'sha256': '313f8c46dec3be020734db5647f124467f86b0f637c1e80a5c85814971413344'}, 'wq': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/wq.bin', 'bytes': 4718592, 'sha256': 'ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72'}, 'wv': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/wv.bin', 'bytes': 786432, 'sha256': 'a00fd3873f1d0ab098694b6003fd27f464e769c3395e227c729bb856246de84a'}, 'x': {'path': 'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/x.bin', 'bytes': 786432, 'sha256': 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'}, 'gamma1': {'path': 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/gamma1.bin', 'bytes': 6144, 'sha256': 'e8e9d18c28e26e06d89fbb591b749cb77617e32cc17607f2b92e4b6a1828c70a'}, 'wd': {'path': 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/wd.bin', 'bytes': 27525120, 'sha256': '90b75c3a30d975516e17cc61ba0fe2e41eff5b7d98c1cc9361b25f0d172a53ec'}, 'wg': {'path': 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/wg.bin', 'bytes': 27525120, 'sha256': 'be5cdf567f7ac2f91f63bfad26194336f4f857596716b3c365986b4ad1e5a44f'}, 'wo': {'path': 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/wo.bin', 'bytes': 4718592, 'sha256': '69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c'}, 'wu': {'path': 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/wu.bin', 'bytes': 27525120, 'sha256': '59f200f6eb3b67e947248d6f5f0308c28ec0256b93893342e2f27d028c80a040'}}
MANIFESTS={'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs/INPUTS_READY.json': '2bce967bd75b90ff599586d47867e851c4a3e29f2a8cbb61f3177dfd55b95ee6', 'work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs/INPUTS_READY.json': 'f52b57f5331e04a95abcd235e036f5d2035f12c8b947f27b4b1d1f5d9060aca2'}
PREFIX_RAW='work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/raw'
TAIL_RAW='work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/raw'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()
def checked(path,spec):
    path=ROOT/path
    need(path.resolve()==path and path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'canonical fixed input')
    raw=path.read_bytes();need(len(raw)==spec['bytes'] and hashlib.sha256(raw).hexdigest()==spec['sha256'],'fixed input source identity');return raw

def load_inputs():
    for path,digest in MANIFESTS.items():need(sha(ROOT/path)==digest,'original input manifest changed')
    values={};records={}
    for role,spec in ROLES.items():
        raw=checked(spec['path'],spec);value=raw[:ROWS*H*4] if role=='x' else raw
        values[role]=value;records[role]=dict(source=spec,offset=0,bytes=len(value),sha256=hashlib.sha256(value).hexdigest(),
          rule='LEADING_16_TOKEN_ROWS' if role=='x' else 'EXACT_COMPLETE_ORIGINAL_ROLE')
    need(len(values['rope'])==ROPE_BYTES,'full cos1024/sin1024 physical layout must remain')
    return values,records

def raw13(pins):
    result={}
    for spec in pins['raw_tensors']:
        directory=PREFIX_RAW if spec['local_name'].startswith(('embed_tokens','input_layernorm','self_attn.q_','self_attn.k_','self_attn.v_')) else TAIL_RAW
        path=str(Path(directory)/(spec['local_name']+'.bin'))
        result[spec['local_name']]=checked(path,spec)
    need(len(result)==13,'all original raw inputs, no intermediates');return result
