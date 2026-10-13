"""Only original L0 A/B N32 weights and32-head log/bias;262336B, no Z or experts."""
import argparse
import json
from pathlib import Path
from ..qwen35_35b_payload import packer as p

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'model.language_model.layers.0.linear_attn.'
TENSORS = (
    ('in_proj_a.weight','BF16',[32,2048],277976,409047),
    ('in_proj_b.weight','BF16',[32,2048],409048,540119),
    ('A_log','F32',[32],189080,189207),
    ('dt_bias','BF16',[32],277912,277975),
)
HEADER_SHA = 'd6d6f3155bd210da84591c715306d39d0ba4c1a7878db8bdcc65dc52054e85d2'


def selection(root=ROOT):
    root = Path(root)
    base = p.selection(root, include_qkv=True)  # all original pinned metadata gates
    bundle = json.loads(p.read_record(root, base['bundle']))
    index = json.loads(p.read_record(root, base['index']))['weight_map']
    names=[PREFIX+t[0] for t in TENSORS]
    p.require(all(index[n]=='model.safetensors-00014-of-00014.safetensors' for n in names),'A/B parameter shard drift')
    shard=next(s for s in bundle['shards'] if s['file']==index[names[0]])
    raw=p.read_record(root,shard['header'])
    p.require(len(raw)==189080 and p.sha256(raw)==HEADER_SHA,'original A/B header drift')
    header=p.decode_header(raw,shard['file_bytes']);specs=[]
    for suffix,dtype,shape,start,end in TENSORS:
        name=PREFIX+suffix;local='layers.0.linear_attn.'+suffix
        offsets=[start-len(raw),end+1-len(raw)]
        p._same(header[name],dict(dtype=dtype,shape=shape,data_offsets=offsets),'original A/B tensor')
        spec=dict(name=name,local_name=local,file=local+'.bin',dtype=dtype,shape=shape,
            source_shape=shape,source_rows=None,source_data_offsets=offsets,
            source_tensor_start=start,source_tensor_end=end,source_tensor_bytes=end-start+1,
            start=start,end=end,bytes=end-start+1,shard=shard['file'],header_bytes=len(raw),header_sha256=HEADER_SHA)
        p._spec_from_header(spec,shard,raw,header);specs.append(spec)
    config=json.loads(p.read_record(root,base['config']))['text_config']
    p.require(config['hidden_size']==2048 and config['linear_num_value_heads']==32,'A/B geometry drift')
    plan = {k:base[k] for k in ('schema_version','model_id','revision','forward_revision','bundle','config','forward','index','profile','source_manifest')}
    plan.update(selection='l0_ab_log_bias_only',shards=[shard],tensors=specs,payload_bytes=262336,
        header_preflight_bytes=189080,total_download_bytes=451416,max_range_bytes=p.MAX_RANGE_BYTES,
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
                    payload_bytes=262336,official_forward_executed=False,full_checkpoint_sha256_verified=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
