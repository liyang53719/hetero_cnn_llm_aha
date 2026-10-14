"""Pure control/receipt failure capture; no arithmetic or oracle reads."""
import resource,time,traceback
from candidates.qwen2_live_attention_model_m128 import boundary

def stage_message(stage,error):
    if str(error)=='public FFN host budget exceeded':
        return 'M16 '+stage+': public Host software deadline exceeded'
    return 'M16 '+stage+': '+str(error)

def contextual_error(stage,error):
    return RuntimeError(stage_message(stage,error)) if str(error)=='public FFN host budget exceeded' else error

def attach_failure(report,error,*,stage,started,cpu,gate,physical=None,x=None,service=None,shared=None):
    report.update(status='FAILED',failure_stage=stage,error=repr(error),original_error_message=str(error),
        stage_error=stage_message(stage,error),failure_kind='BUDGET_EXCEEDED' if 'budget' in str(error) and 'exceeded' in str(error) else 'EXECUTION_FAILURE',
        traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-started,
        host_cpu_seconds=time.process_time()-cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        oracle_opened=gate.opened,oracle_reference_reads=list(gate.reference_reads),oracle_blocked_reads=gate.blocked)
    if physical is not None:report['failed_physical_memory']=physical.report()
    if x is not None:
        report['failed_execution']=x.report()
        report['failed_attention_owner']=dict(x.attention_owner.report(),exact_state=x.attention_owner.state,
            memory_pending=x.attention_owner.memory_pending,matrix_client_live=x.attention_owner.matrix_client is not None)
        if physical is not None:report['failed_backend_debts']=boundary.debts(x,physical)
    if service is not None:report['failed_matrix']=service.report()
    if shared is not None:
        report['failed_scalar_calls']=dict(shared.calls);report['failed_scalar_owned']=shared.client is not None
    return report
