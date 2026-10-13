"""Only original L0 BF16[8192,1,4] Conv weights; 65536 bytes, no expert data."""
import argparse
import json
from pathlib import Path
from ..qwen35_35b_payload import packer as p

ROOT = Path(__file__).resolve().parents[2]
NAME = 'model.language_model.layers.0.linear_attn.conv1d.weight'
LOCAL = 'layers.0.linear_attn.conv1d.weight'
HEADER_SHA = 'd6d6f3155bd210da84591c715306d39d0ba4c1a7878db8bdcc65dc52054e85d2'


def selection(root=ROOT):
    root = Path(root)
    base = p.selection(root, include_qkv=True)  # all original pinned metadata gates
    bundle = json.loads(p.read_record(root, base['bundle']))
    index = json.loads(p.read_record(root, base['index']))['weight_map']
    p.require(index[NAME] == 'model.safetensors-00014-of-00014.safetensors', 'Conv shard mapping drift')
    shard = next(s for s in bundle['shards'] if s['file'] == index[NAME])
    raw = p.read_record(root, shard['header'])
    p.require(len(raw) == 189080 and p.sha256(raw) == HEADER_SHA, 'Conv pinned header drift')
    header = p.decode_header(raw, shard['file_bytes'])
    tensor = header[NAME]
    p._same(tensor, {'dtype': 'BF16', 'shape': [8192,1,4], 'data_offsets': [23296,88832]}, 'Conv original tensor')
    config = json.loads(p.read_record(root, base['config']))['text_config']
    p.require(config['linear_conv_kernel_dim'] == 4 and config['hidden_act'] == 'silu' and
              2*config['linear_num_key_heads']*config['linear_key_head_dim'] +
              config['linear_num_value_heads']*config['linear_value_head_dim'] == 8192,
              'Conv channel/kernel/activation contract drift')
    spec = dict(name=NAME, local_name=LOCAL, file=LOCAL+'.bin', dtype='BF16', shape=[8192,1,4],
        source_shape=[8192,1,4], source_rows=None, source_data_offsets=[23296,88832],
        source_tensor_start=212376, source_tensor_end=277911, source_tensor_bytes=65536,
        start=212376, end=277911, bytes=65536, shard=shard['file'], header_bytes=len(raw),
        header_sha256=HEADER_SHA)
    p._spec_from_header(spec, shard, raw, header)
    plan = {k:base[k] for k in ('schema_version','model_id','revision','forward_revision','bundle','config','forward','index','profile','source_manifest')}
    plan.update(selection='l0_conv_only',shards=[shard],tensors=[spec],payload_bytes=65536,
        header_preflight_bytes=189080,total_download_bytes=254616,max_range_bytes=p.MAX_RANGE_BYTES,
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
                    payload_bytes=65536,official_forward_executed=False,full_checkpoint_sha256_verified=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
