"""Recompute conditional resource bounds from sealed actual prefix counters.

No model execution and no conversion of typed transport ticks to hardware time.
These prefix conditions are not complete-block performance predictions.
"""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PHASES=('input_norm','qkv_columns_0','conv4_silu','a','b','ab_pack','prep','z','chunk','gated_norm','output_projection','attention_residual','post_attention_norm')
PINS={
'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala':'9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala':'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedIdma.scala':'b7e424bca21cecc561045a707b62ee24a7cc7a0314cf8d218ce8e64bb24f29ee',
'rtl/integration/idma_backend_rw_axi_flat_wrap.sv':'a82bc50fac9b29df3f5f68527361f9dfac4792dfea3178b84eb488428d8d12c0'}

def require(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def analyze(s):
    require(s['tokens']==128 and not s['full_block'] and not s['rtl_executed'],'actual M128 prefix only')
    require(s['sources_unchanged'] and s['native_artifacts_unchanged'],'sealed producer identity')
    e=s['execution'];require(tuple(x['stage'] for x in e['terminals'])==PHASES and all(x['status'] is None for x in e['terminals']),'13 accepted successful prefix terminals')
    require(tuple(x['stage'] for x in e['stages'])==PHASES,'exact prefix phase order')
    phase=[]
    for x in e['stages']:
        c=x['report']['counts']
        read=c.get('read_bytes',64*(c.get('a_read_beats',0)+c.get('b_read_beats',0)))
        write=c.get('write_bytes',c.get('write_data_bytes',0))
        require(all(type(v) is int and v>=0 for v in (read,write,c['ticks'])),'nonnegative integer counts')
        phase.append(dict(stage=x['stage'],read_bytes=read,write_bytes=write,transport_ticks=c['ticks']))
    require(len(phase)==13 and len({x['stage'] for x in phase})==13,'complete prefix phase enumeration')
    read=sum(x['read_bytes'] for x in phase);write=sum(x['write_bytes'] for x in phase)
    require(all(type(v) is int and v>=0 for v in e['scalar_operations'].values()),'scalar counts')
    basic=sum(e['scalar_operations'][n] for n in ('add','mul','mul_ieee_rne'))
    executed=e['matrix_service']['dense_fma_calls'];require(executed==e['matrix_service']['counters']['dense_steps']*4096,'full-array executed work')
    require(basic>0 and read+write>0,'nonempty fixed resource work')
    payload=(read+write+63)//64;basic_span=3*basic-1
    # This sealed M128 projection set has no M-row padding. Scalar/Vector work
    # remains separate and is never counted as Matrix useful MAC.
    require(e.get('full_qkv') is True and e.get('output_columns')==[{'columns':8192,'start':0}],'full original QKV geometry')
    useful=128*(2048*8192 + 2*2048*32 + 2048*4096 + 4096*2048)
    require(executed==useful,'fixed QKV/A/B/Z/O shape work; cannot infer useful from M128 alone')
    return dict(scope='SOURCE_BOUND_CONDITIONAL_PREFIX_RESOURCE_BOUNDS_ONLY',phase_counts=phase,
        matrix_macs=4096,matrix_useful=useful,matrix_executed=executed,ideal_matrix_issue_slots=executed//4096,
        scalar_external_requests=sum(e['scalar_operations'].values()),scalar_basic_requests=basic,
        ddr_read_bytes=read,ddr_write_bytes=write,ddr_single_512bit_payload_floor_slots=payload,
        scalar_basic_II3_floor_span=basic_span,
        conditional_prefix_upper_bounds=dict(ddr_only=useful/(4096*payload),scalar_basic_only=useful/(4096*basic_span)),
        assumptions=['current operation-to-resource assignment remains unchanged','one shared Scalar with existing idle-normal-done wrapper','one 512-bit DDR payload service, no overlap of read/write transfer','M128 has no Matrix M-padding in these recorded projections'],
        omitted_costs=['Div/Sqrt/exp and new unbound op latency','Vector Add/Mul latency','DRAM timing and control/ACK latency','descriptor and missing MoE/final block commit'],
        transport_tick_sum=sum(x['transport_ticks'] for x in phase),transport_ticks_are_hardware_cycles=False,
        full_block_cycles=None,full_block_mac_utilization=None,busy_duty=None,rtl_measured=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--summary',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    require(not a.out.exists(),'fresh report');raw=a.summary.read_bytes();require(sha(raw)==a.sha256,'summary pin')
    for path,digest in PINS.items():require(sha((ROOT/path).read_bytes())==digest,'production source drift '+path)
    report=analyze(json.loads(raw));report.update(summary=dict(path=str(a.summary.resolve()),sha256=a.sha256),source_pins=PINS)
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('scalar_basic_II3_floor_span','ddr_single_512bit_payload_floor_slots','conditional_prefix_upper_bounds')}))
if __name__=='__main__':main()
