"""Strict original Conv gates, kept separate from actual owner execution."""
import json
from pathlib import Path
from ..qwen35_gdn_prefill.conv import reference as r


def compare(actual, fixed, native, end_to_end, *, root=r.ROOT):
    raw = (Path(root)/r.GATE_SOURCE).read_bytes()
    thresholds = json.loads(raw)['native_thresholds']
    wanted = dict(conv_same_canonical_input_max_bf16_ulp=1,
                  silu_same_canonical_input_max_bf16_ulp=1,
                  end_to_end_max_abs=.03125,end_to_end_mean_abs=.005)
    r.require(all(thresholds.get(k)==v for k,v in wanted.items()), 'original Conv gates changed')
    result={}
    for name in ('conv','silu','history'):
        r.require(actual[name]==fixed[name], 'actual differs from fixed recipe: '+name)
        same=r.compare_bf16(actual[name],native[name])
        end=r.compare_bf16(actual[name],end_to_end[name])
        same['passed']=same['max_bf16_ulp']<=1 if name!='history' else same['bit_mismatches']==0
        end['passed']=end['max_abs']<=.03125 and end['mean_abs']<=.005
        result[name]=dict(same_input=same,end_to_end=end)
    return dict(passed=all(v[k]['passed'] for v in result.values() for k in ('same_input','end_to_end')),
                comparisons=result,thresholds=wanted,gate_source=r.GATE_SOURCE,
                gate_source_sha256=r.sha(raw),full_block=False,rtl_executed=False)


def save_raw(directory, groups):
    directory=Path(directory); directory.mkdir(exist_ok=False)
    records={}
    for group,values in groups.items():
        records[group]={}
        for name,raw in values.items():
            path=directory/(group+'_'+name+'.bf16le');path.write_bytes(raw)
            records[group][name]=dict(path=str(path.resolve()),bytes=len(raw),sha256=r.sha(raw))
    return records


def main():
    import argparse
    from . import reference,payload
    parser=argparse.ArgumentParser()
    parser.add_argument('--execution',type=Path,required=True)
    parser.add_argument('--execution-sha256',required=True)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=args.execution.read_bytes()
    r.require(r.sha(raw)==args.execution_sha256,'sealed execution digest')
    report=json.loads(raw)
    r.require(report['sources_unchanged'] and report['source_sha256']==report['source_sha256_after'], 'execution source drift')
    r.require(report['execution']['status']=='PASS_TYPED_PREFIX_EXECUTION_ONLY','actual execution incomplete')
    r.require(report['conv_requested'] and not report['full_block'] and not report['rtl_executed'],'prefix scope')
    def read(item):
        data=Path(item['path']).read_bytes()
        r.require(len(data)==item['bytes'] and r.sha(data)==item['sha256'],'frozen artifact drift')
        return data
    observations=report['observations']
    r.require([x['stage'] for x in observations]==['input_norm','qkv_columns_0','conv4_silu','conv_history_staging'],'exact observed inventory')
    actual=dict(conv=read(report['conv_preact_record']),silu=read(observations[2]['output']),history=read(observations[3]['output']))
    _,values=payload.load(args.payload,args.manifest_sha256)
    weight=values[payload.LOCAL];qkv=read(observations[1]['output'])
    qkv_reference=json.loads(read(report['reference']))
    original=read(qkv_reference['official_output'])
    fixed,fixed_id=reference.fixed_conv(qkv,weight,report['tokens'])
    native,native_id=reference.native_conv(qkv,weight,report['tokens'])
    end,end_id=reference.native_conv(original,weight,report['tokens'])
    result=compare(actual,fixed,native,end)
    r.require(args.output.resolve().is_relative_to(r.ROOT/'work') and not args.output.exists(),'fresh ignored output')
    result['raw_records']=save_raw(args.output,dict(fixed=fixed,same_input=native,end_to_end=end))
    result.update(execution_sha256=args.execution_sha256,execution_source_sha256=report['source_sha256'],
        verifier_sha256=r.sha(Path(__file__).read_bytes()),reference_sha256=r.sha(Path(reference.__file__).read_bytes()),
        identities=dict(fixed=fixed_id,native=native_id,end_to_end=end_id),
        status='PASS_STRICT_POST_EXECUTION_CONV_GATES' if result['passed'] else 'FAILED')
    (args.output/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    r.require(result['passed'],'original strict Conv gates failed')

if __name__=='__main__':main()
