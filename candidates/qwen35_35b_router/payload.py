"""Only original L0 H2048 router gate weight; no shared or expert weights."""
import argparse
import json
from pathlib import Path
from ..qwen35_35b_payload import packer as p

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'model.language_model.layers.0.'
TENSORS = (
    ('mlp.gate.weight','BF16',[256,2048],540120,1588695,14),
)
HEADER_PINS = {
    14:(189080,'d6d6f3155bd210da84591c715306d39d0ba4c1a7878db8bdcc65dc52054e85d2'),
}


def selection(root=ROOT):
    root = Path(root)
    base = p.selection(root, include_qkv=True)  # all original pinned metadata gates
    bundle = json.loads(p.read_record(root, base['bundle']))
    index = json.loads(p.read_record(root, base['index']))['weight_map']
    specs=[];shards={}
    for suffix,dtype,shape,start,end,number in TENSORS:
        name=PREFIX+suffix;local='layers.0.'+suffix
        shard_name=f'model.safetensors-{number:05d}-of-00014.safetensors'
        p.require(index[name]==shard_name,'router N256K2048 shard drift')
        shard=next(x for x in bundle['shards'] if x['file']==shard_name)
        raw=p.read_record(root,shard['header']);size,digest=HEADER_PINS[number]
        p.require(len(raw)==size and p.sha256(raw)==digest,'router N256K2048 header drift')
        header=p.decode_header(raw,shard['file_bytes']);shards[shard_name]=shard
        offsets=[start-len(raw),end+1-len(raw)]
        p._same(header[name],dict(dtype=dtype,shape=shape,data_offsets=offsets),'original router N256K2048 tensor')
        spec=dict(name=name,local_name=local,file=local+'.bin',dtype=dtype,shape=shape,
            source_shape=shape,source_rows=None,source_data_offsets=offsets,
            source_tensor_start=start,source_tensor_end=end,source_tensor_bytes=end-start+1,
            start=start,end=end,bytes=end-start+1,shard=shard_name,header_bytes=len(raw),header_sha256=digest)
        p._spec_from_header(spec,shard,raw,header);specs.append(spec)
    config=json.loads(p.read_record(root,base['config']))['text_config']
    p.require(config['hidden_size']==2048 and config['num_experts']==256 and config['num_experts_per_tok']==8,'router N256K2048 geometry drift')
    plan = {k:base[k] for k in ('schema_version','model_id','revision','forward_revision','bundle','config','forward','index','profile','source_manifest')}
    plan.update(selection='l0_router_gate_only',shards=list(shards.values()),tensors=specs,payload_bytes=1048576,
        header_preflight_bytes=189080,total_download_bytes=1237656,max_range_bytes=p.MAX_RANGE_BYTES,
        full_block=False, rtl_executed=False)
    return plan


def collect(output, *, root=ROOT, **kwargs):
    return p.collect_plan(Path(root), Path(output), selection(root), **kwargs)


def load(output, manifest_sha256, *, root=ROOT):
    return p.load_plan(Path(root), Path(output), selection(root), manifest_sha256=manifest_sha256)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('plan','collect','verify'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--manifest-sha256')
    args=parser.parse_args()
    if args.command=='plan':
        result=selection()
    else:
        p.require(args.output is not None,'output required')
        if args.command=='collect':
            p.require(args.manifest_sha256 is None,'collect creates a fresh observed manifest')
            collect(args.output)
        else:load(args.output,args.manifest_sha256)
        result=dict(output=str(args.output),manifest_sha256=p.sha256((args.output/'manifest.json').read_bytes()),
                    payload_bytes=1048576,official_forward_executed=False,full_checkpoint_sha256_verified=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
