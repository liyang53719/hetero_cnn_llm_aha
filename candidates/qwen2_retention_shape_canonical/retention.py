"""Narrow shape-container normalization before the unchanged retention verifier.

Only the ten PV32 observation shape tuples become JSON arrays. No data,
commitment, status, count, terminal or original report is mutated.
"""
import copy
from candidates.qwen2_exact64_diagnostic_fullblock import retention as original


def need(ok,message):
    if not ok:raise ValueError(message)


def expected_shapes(rows):
    need(type(rows) is int and rows in (16,128),'only fixed M16 or M128 retention geometry')
    shapes={n:(12,rows,rows) for n in ('unrounded_dot_sum','dot_bf16','scores_bf16',
        'softmax_exp','softmax_fp32','prob_bf16')}
    shapes.update(dot_parts=(12,rows,rows,16),normalizer=(12,rows,3),
        pv_raw=(12,rows,128),pv_bf16=(12,rows,128))
    return shapes


def canonical_report_view(report):
    need(type(report) is dict and type(report.get('observation')) is dict,'original report/observation required')
    observation=report['observation'];job=observation.get('job');fields=observation.get('fields')
    need(type(job) is dict and type(fields) is dict,'original observed job/fields required')
    expected=expected_shapes(job.get('m'))
    need(observation.get('schema')=='qwen2-pv32-readonly-observation-v1' and
        observation.get('status')=='COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED' and
        set(fields)==set(expected),'exact original PV32 complete observation fields')
    for name,shape in expected.items():
        need(type(fields[name]) is dict,'original field record')
        value=fields[name].get('shape')
        need(type(value) in (tuple,list) and all(type(v) is int for v in value) and tuple(value)==shape,
            'exact native integer shape for fixed geometry')
    # Deep copy the observation so the caller's original tuples and nested
    # records remain untouched. All other report fields retain original values.
    result=dict(report);result['observation']=copy.deepcopy(observation)
    for field in result['observation']['fields'].values():field['shape']=list(field['shape'])
    return result


def seal(out,actual,silu,capture,report):
    # The original verifier still checks every actual and observer byte, every
    # commitment and the original terminal/ACK/closed-capture requirements.
    return original.seal(out,actual,silu,capture,canonical_report_view(report))

verify=original.verify
