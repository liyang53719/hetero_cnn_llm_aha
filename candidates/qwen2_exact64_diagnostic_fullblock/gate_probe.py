"""Two post-seal, same-shape official gate calls for private error isolation.

This separate fresh process is cold by default. It cannot feed a DUT operand,
upgrade a failed numerical verdict, or accept an incomplete/changed launch.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from candidates.qwen2_exact64_diagnostic_fullblock import job,recipe as R,retention,closure
from candidates.qwen2_official_platform_fullblock import aggregate as original_aggregate

ACTUAL=ROOT/'work/qwen2_exact64_diagnostic_fullblock_numeric/ci01'
OUT=ROOT/'work/qwen2_exact64_diagnostic_gate_probe/ci01'
STATUS='POSTSEAL_GATE_DIAGNOSTIC_COMPLETE'
STAGES=('LOCAL_GATE_ERROR','PROPAGATED_GATE_ERROR','UPSTREAM_N1_ERROR')
LIMIT_KEYS=('inner_seconds','outer_seconds','cpu_seconds','rss_bytes','file_bytes','output_bytes')
DIAGNOSTIC_IDENTITIES=frozenset(('projection','kernel','partial','n0_row','weights','original_a_payload','resident_scratch','resident_storage'))
DIAGNOSTIC_DEBTS=frozenset(('exact64_active','exact64_not_idle','exact64_poison','exact64_request','exact64_result',
    'exact64_kernel_not_idle','shared_a_guard_lease','shared_a_route_active','shared_a_route_fault','shared_a_owner',
    'shared_a_pending','shared_a_hold','shared_a_valid_lines','attention_local_pending','attention_local_request','attention_deferred_finish'))


def need(ok,message):
    if not ok:raise ValueError(message)


def authorize():
    review=job.authorize()
    need(review.get('postseal_gate_invocations')==2 and type(review.get('postseal_gate_invocations')) is int,
        'new review must explicitly authorize two full same-shape postseal gate calls')
    limits={key:review.get('postseal_gate_'+key) for key in LIMIT_KEYS}
    need(all(type(v) is int and v>0 for v in limits.values()),'explicit positive postseal limits required')
    need(limits['outer_seconds']>=limits['inner_seconds']+2 and limits['file_bytes']<=limits['output_bytes'],
        'postseal inner/outer and file/total margins')
    return review,limits


def validate_seal(report):
    """Numerical FAIL is eligible; structural/incomplete/failure state is not."""
    need(report.get('status') in ('PASS_DIAGNOSTIC_SOFTWARE_OWNER','FAIL_DIAGNOSTIC_SOFTWARE_OWNER') and
        report.get('scope')=='DIAGNOSTIC_SOFTWARE_OWNER' and report.get('performance')=='NO_GO' and
        report.get('hardware_mapping')=='NOT_IMPLEMENTED','terminal diagnostic result required')
    need(report.get('whole_block_terminal') is True and report.get('actual_outputs_sealed') is True and
        report.get('finalfence') is True and report.get('fullblock_pass') is False and
        report.get('acceptance_sealed') is False and report.get('chisel_full_prefill_pass') is False,
        'complete diagnostic output seal without formal acceptance required')
    need(report.get('local_retention_verified_before_seal') is True and
        report.get('local_retention_verified_after_comparison') is True,'complete actual retention verification required')
    numeric=report.get('diagnostic_numeric_pass')
    need(type(numeric) is bool and report.get('official_observed_node_pass') is numeric and
        report.get('diagnostic_acceptance_sealed') is numeric and
        (report['status']=='PASS_DIAGNOSTIC_SOFTWARE_OWNER') is numeric,
        'numeric status/diagnostic seal disagreement')
    need(original_aggregate._counts(report.get('execution',{}).get('host',{})) and
        original_aggregate._same_live(report) and original_aggregate._debts(report),
        'original real 21/17/1, same-live identities and all debt gates required')
    need(original_aggregate._comparison(report,require_pass=False),
        'complete original post-seal numerical comparison receipts required')
    debts=report.get('diagnostic_backend_debts')
    need(type(debts) is dict and set(debts)==DIAGNOSTIC_DEBTS and all(v is False for v in debts.values()),
        'all extra software-owner/shared-A debts must be clear')
    before=report.get('diagnostic_identity_initial');after=report.get('diagnostic_identity_final')
    need(type(before) is dict and set(before)==DIAGNOSTIC_IDENTITIES and before==after and
        all(type(v) is int and v>0 for k,v in before.items() if k!='original_a_payload') and
        type(before['original_a_payload']) is list and len(before['original_a_payload'])==2 and
        all(type(v) is int and v>0 for v in before['original_a_payload']),'extra live storage identities required')
    for before_key,after_key in (('source_sha256_before','source_sha256_after'),('tools_before','tools_after'),
            ('evidence_sha256_before','evidence_sha256_after'),('input_identity_before','input_identity_after')):
        # Input before contains original role records and after is the checked
        # identity projection. Compare only the exact shared byte commitments.
        a,b=report.get(before_key),report.get(after_key)
        need(type(a) is dict and bool(a) and type(b) is dict and set(a)==set(b),'complete final identity boundary')
        if before_key=='input_identity_before':
            need(all(a[n]['sha256']==b[n]['sha256'] for n in a),'actual input identity changed')
        else:need(a==b,'source/runtime/evidence changed')
    need(report.get('failure_kind') is None,'failed actual process cannot be diagnosed as a sealed run')
    return True


def validate_launch(report,launch):
    numeric=report['diagnostic_numeric_pass']
    need(launch.get('scope')=='DIAGNOSTIC_SOFTWARE_OWNER' and
        launch.get('performance')=='NO_GO' and launch.get('hardware_mapping')=='NOT_IMPLEMENTED' and
        launch.get('child_status')==report['status'] and
        launch.get('status')==('PASS' if numeric else 'FAILED') and
        type(launch.get('returncode')) is int and launch['returncode']==(0 if numeric else 1),
        'completed bounded diagnostic child required')
    need(launch.get('failure_kind') is None and launch.get('cleanup_incomplete') is False and
        launch.get('accepted_final_launch_result') is True and launch.get('automatic_retry') is False and
        launch.get('fullblock_pass') is False and launch.get('acceptance_sealed') is False and
        launch.get('diagnostic_numeric_pass') is numeric and launch.get('diagnostic_acceptance_sealed') is numeric and
        launch.get('reviewed_source_manifest')==report['reviewed_source_manifest'],
        'supervisor cleanup/resource/terminal/source gates must be complete')
    return True


def gate_constructor(nodes):
    """Extract the original whole gate_proj assignment without rewriting it."""
    classes=[n for n in nodes if isinstance(n,ast.ClassDef) and n.name=='Qwen2MLP']
    need(len(classes)==1,'one original Qwen2MLP AST')
    init=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name=='__init__']
    need(len(init)==1,'one original MLP constructor')
    target=ast.parse('self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)').body[0]
    matches=[n for n in init[0].body if ast.dump(n,include_attributes=False)==ast.dump(target,include_attributes=False)]
    need(len(matches)==1,'original whole no-bias gate constructor required')
    return deepcopy(matches[0])


def replay_pair(linear,reference_n1,actual_n1,reference_gate,export):
    """Exactly two calls; an exact control reproduction precedes actual input."""
    control=export(linear(reference_n1))
    need(control==reference_gate,'same-shape official gate control is not bit-exact to fresh reference')
    replay=export(linear(actual_n1))
    return control,replay


def _read_json(path,maximum=256<<20):
    need(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),'private receipt alias')
    need(path.is_file() and 0<path.stat().st_size<=maximum,'bounded private receipt')
    return R.parse(path.read_bytes())


def run():
    review,limits=authorize()  # No inputs, numeric imports or writes before review.
    started=time.monotonic();cpu=time.process_time()
    need(not any(n in sys.modules for n in ('numpy','torch','transformers')),'fresh isolated numerical process required')
    resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],limits['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_AS,(limits['rss_bytes'],limits['rss_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],limits['file_bytes']))
    report=_read_json(ACTUAL/'RESULT.json');validate_seal(report)
    launch_path=ACTUAL.with_name(ACTUAL.name+'.LAUNCH.json')
    launch=_read_json(launch_path);validate_launch(report,launch)
    need(report['reviewed_source_manifest']==review['source_closure_sha256'] and
        closure.digest()==review['source_closure_sha256'],'same reviewed actual and probe source')
    retention.verify(ACTUAL,report['local_retention'])
    pins=R.load_pins();frozen=R.require_frozen_references(pins)
    reference=R.validate_bootstrap_metadata(pins,seal_sha256=frozen['bootstrap_seal']['sha256'])['manifest']
    context=R.execution_context();sources=closure.digest()
    need(not OUT.exists() and OUT.resolve()==OUT and not any(p.is_symlink() for p in (OUT,*OUT.parents)),
        'one fresh private postseal invocation')
    OUT.mkdir(parents=True)
    receipt=dict(schema=1,status='STARTED',scope='POSTSEAL_GATE_ERROR_ISOLATION_ONLY',
        performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',fullblock_pass=False,
        original_diagnostic_numeric_pass=report['diagnostic_numeric_pass'],
        official_gate_invocations=0,control_bit_exact=False,local_only=True,upload_authorized=False,
        resource_limits=limits,source_closure_sha256=sources,comparison_order=list(STAGES))
    def save():
        (OUT/'RESULT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+'\n')
    def check():
        need(time.monotonic()-started<limits['inner_seconds'],'postseal wall budget exceeded')
        need(sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())<=limits['output_bytes'],'postseal output budget')
    save()
    try:
        expected=pins['runtime_requirements']
        need({k:os.getenv(k) for k in pins['capture_environment']}==pins['capture_environment'],
            'same explicit official capture environment required')
        rawspec=next(s for s in pins['raw_tensors'] if s['local_name']=='mlp.gate_proj.weight')
        need(rawspec['shape']==[8960,1536],'full original gate weight geometry')
        weight=R.checked(ROOT,rawspec['path'],rawspec)
        payload={n:R.checked(ROOT,R.REFERENCE+'/'+n+'.f32le',reference['outputs'][n]) for n in ('n1','gate')}
        actual={n:(ACTUAL/('actual_'+n+'.f32le')).read_bytes() for n in ('n1','gate')}
        for n,raw in actual.items():
            need(retention.identity(ACTUAL/('actual_'+n+'.f32le'))==report['sealed_actual_outputs'][n],
                'actual propagation input no longer matches sealed bytes')
        nodes=R.N.official_nodes(ROOT,pins['model_ast_nodes'],R.N.MODEL_SOURCE,pins['sources'])
        assignment=gate_constructor(nodes)
        platform_before=R.N.observe_platform_before(execute=True)
        import numpy as np
        import torch
        from torch import nn
        need(np.__version__==expected['numpy'] and str(torch.__version__)==expected['torch'] and
            torch.version.git_version==expected['torch_commit'] and
            torch.backends.cpu.get_cpu_capability()==expected['capability'] and
            R.sha(torch.__config__.show().encode())==expected['torch_build_sha256'],'official numeric runtime drift')
        need(Path(torch._C.__file__).resolve()==(ROOT/pins['runtime_native_files']['torch_C']['path']).resolve() and
            Path(np._core._multiarray_umath.__file__).resolve()==(ROOT/pins['runtime_native_files']['numpy_multiarray']['path']).resolve(),
            'official native runtime import origin')
        torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
        torch.backends.mkldnn.enabled=False
        def runtime_state():
            return dict(profile=os.environ.get('QWEN2_CI_RUNTIME_PROFILE'),mkldnn_enabled=torch.backends.mkldnn.enabled,
                threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),
                deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),capability=torch.backends.cpu.get_cpu_capability())
        backend=runtime_state()
        need(backend==dict(profile='avx2-aten-gemm-v1',mkldnn_enabled=False,threads=4,interop_threads=1,
            deterministic_algorithms=True,capability=expected['capability']),'official same gate backend required')
        def materialized(raw,width):
            need(len(raw)==128*width*4,'complete same-shape materialized tensor')
            a=np.frombuffer(raw,dtype='<u4')
            need(bool(np.all((a&0xffff)==0)) and bool(np.all((a&0x7f800000)!=0x7f800000)),'finite exact BF16 materialization required')
            return torch.from_numpy((a>>16).astype('<u2')).view(torch.bfloat16).reshape(1,128,width)
        holder=nn.Module();holder.hidden_size=1536;holder.intermediate_size=8960
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(ROOT/R.N.MODEL_SOURCE),'exec'),{'self':holder,'nn':nn})
        holder.gate_proj.weight=nn.Parameter(torch.from_numpy(np.frombuffer(weight,dtype='<u2').copy()).view(torch.bfloat16).reshape(8960,1536),requires_grad=False)
        holder.eval()
        need(holder.gate_proj.bias is None and holder.gate_proj.weight.dtype==torch.bfloat16 and
            not holder.gate_proj.weight.requires_grad and not holder.training,'original raw BF16 no-bias gate binding')
        def export(value):
            need(value.dtype==torch.bfloat16 and list(value.shape)==[1,128,8960] and bool(torch.isfinite(value).all()),'finite complete gate output')
            return value.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
        def linear(value):
            check();receipt['official_gate_invocations']+=1
            need(receipt['official_gate_invocations']<=2,'two official calls only')
            return holder.gate_proj(value)
        with torch.inference_mode():
            control,replay=replay_pair(linear,materialized(payload['n1'],1536),materialized(actual['n1'],1536),payload['gate'],export)
        receipt['control_bit_exact']=True
        need(receipt['official_gate_invocations']==2 and runtime_state()==backend,'exact replay count/backend stability')
        (OUT/'gate_on_actual_n1.f32le').write_bytes(replay)
        from scripts import qwen2_layer0_model_gate as native
        numerical_policy=native.load_policy(ROOT)
        need(numerical_policy['operator']==dict(max_abs=0.03125,mean_abs=0.005),'unchanged original operator gates')
        comparisons={}
        pairs=((STAGES[0],actual['gate'],replay),(STAGES[1],replay,payload['gate']),(STAGES[2],actual['n1'],payload['n1']))
        for stage,a,b in pairs:
            metrics=native.compare(np.frombuffer(a,dtype='<f4'),np.frombuffer(b,dtype='<f4'))
            verdict=native.stage_verdict('n1' if stage==STAGES[2] else 'gate',metrics,'bf16',numerical_policy)
            comparisons[stage]=dict(metrics=metrics,verdict=verdict,official_numeric_pass=verdict['passed'])
        # Recheck all bytes/identities after replay. These metrics cannot change
        # the previously sealed main receipt or its original gate verdicts.
        retention.verify(ACTUAL,report['local_retention'])
        need(_read_json(ACTUAL/'RESULT.json')==report and _read_json(launch_path)==launch,
            'main diagnostic/supervisor receipt changed')
        need(R.execution_context()==context and closure.digest()==sources,'postseal runtime/source context drift')
        R.require_frozen_references(pins)
        for n in ('n1','gate'):
            need(R.checked(ROOT,R.REFERENCE+'/'+n+'.f32le',reference['outputs'][n])==payload[n],'reference changed during replay')
        need(R.checked(ROOT,rawspec['path'],rawspec)==weight,'raw gate weight changed during replay')
        R.N.observe_platform_after(platform_before)
        check()
        receipt.update(status=STATUS,comparisons=comparisons,original_numerical_policy=numerical_policy,
            interpretation='Same-input gate difference and propagated input difference; max/mean errors are not additive.',
            same_actual_seal_verified=True,same_fresh_reference_verified=True,same_runtime_verified=True,
            native_metric_authority='scripts/qwen2_layer0_model_gate.py:compare/stage_verdict')
    except BaseException as error:
        receipt.update(status='POSTSEAL_GATE_DIAGNOSTIC_FAILED',exception_class=type(error).__name__,error=str(error))
        raise
    finally:
        receipt.update(host_wall_seconds=time.monotonic()-started,host_cpu_seconds=time.process_time()-cpu,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        save()
    return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(status='NOT_EXECUTED',scope='POSTSEAL_GATE_ERROR_ISOLATION_ONLY',numerical_execution_allowed=False)))
        return 0
    try:run()
    except Exception:
        print('POSTSEAL_GATE_DIAGNOSTIC_FAILED_LOCAL_DETAILS_ONLY');return 2
    print(STATUS);return 0

if __name__=='__main__':raise SystemExit(main())
