"""Original sparse telemetry with tail debt context and complete deadline labels."""
from candidates.qwen2_live_attention_model_m128_bounded import telemetry as original
from . import statistics
SparseTelemetry = original.SparseTelemetry
BudgetExceeded = original.BudgetExceeded


def is_budget(error):
    text = str(error).lower()
    return isinstance(error, (TimeoutError, original.BudgetExceeded)) or any(
        phrase in text for phrase in ('budget exceeded','exceeded host budget','wall deadline','host time budget','timeout'))


def contextual_error(stage, error):
    return RuntimeError('M128 fullblock '+stage+': software wall deadline exceeded') if is_budget(error) else error


def attach_failure(report,error,**kwargs):
    original.attach_failure(report,error,**kwargs)
    report['failure_kind']='BUDGET_EXCEEDED' if is_budget(error) else report['failure_kind']
    report.update(fullblock_pass=False,whole_block_numeric_acceptance=False,
        backend_abort_drain_executed=False,
        failure_recovery='Outstanding simulated debts retained; OS process cleanup is not backend abort/drain')
    context=kwargs['context']
    if all(context.get(n) is not None for n in ('x','physical','memory')):
        try:
            report['failed_tail_debts']=statistics.debts(context['x'],context['physical'],context['memory'])
            ws=context['memory'].workspace
            report['failed_workspace']=dict(accepted=dict(ws.counts),finished=ws.finished,
                invalidated=ws.invalidated,group=ws.group,
                pending_read=ws.pending_read is not None,active_seed_contexts=sorted(ws.seeds),
                committed_seeds=len(ws.seed_commits),versions=len(ws.versions))
            h=context['x'].coupled
            if h is not None:
                report['failed_ffn']=dict(coordinator_state=h.c.state,current_ng=h.c.ng,silu_busy=h.silu_busy,
                    dense_window_terminals=len(h.window_reports),
                    drains=len(h.drain_reports),accepted=dict(h.counts))
        except Exception as error:
            report['failed_tail_snapshot_error']=repr(error)
    return report
