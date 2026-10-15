"""One unused reference budget after an explicit posthoc recovery seal."""
import argparse,hashlib,json,resource,signal,time,traceback
from pathlib import Path
from . import audit as a
from candidates.qwen2_m16_stage_diagnostic import common as c,geometry as g,inputs as inp,reference as old
from candidates.qwen2_m16_stage_diagnostic.stage_log import StageLog,COUNTER_LIMITS,safe_last
OUT=a.BASE/'reference_recovered'

def run():
    c.limits(60,85);start=time.monotonic();cpu=time.process_time()
    g.need(not OUT.exists() and OUT.resolve()==OUT,'fresh recovered-reference namespace');OUT.mkdir()
    report=dict(status='STARTED',scope='RECOVERED_M16_DIAGNOSTIC',original_model_run='FAIL',
      original_inprocess_postchecks='NOT_REACHED',continuous_identity_claim=False,original_completion_seal=False,
      formal_reference_contract=False,fullblock_pass=False,performance='NO_GO',model_reexecuted=False)
    counters={n:0 for n in COUNTER_LIMITS};log=StageLog(OUT/'STAGES.jsonl',g.LIMITS_REFERENCE)
    log.begin('REFERENCE',counters=counters)
    try:
        sources=a.require_sources();r,seal,seal_sha=a.sealed();counters=r['failure_counters']
        pins,native=c.check_environment();d=c.dependencies();values,records=inp.load_inputs();raw=inp.raw13(pins)
        oracle,info=old.capture(d['recipe'],pins,raw,native)
        old.validate_input_relation(values,raw,pins,oracle,d['qwen2_layer0_model_gate'])
        log.transition('POSTSEAL_COMPARISON',counters=counters)
        comparison=old.compare_actuals(a.MODEL,r,oracle,d['qwen2_layer0_model_gate'])
        inventory={}
        for name,value in oracle.items():
            data=value.tobytes();(OUT/(name+'.f32le')).write_bytes(data)
            inventory[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),shape=list(value.shape))
        log.transition('FINAL_SEAL',counters=counters)
        _,after,after_sha=a.sealed();g.need(after==seal and after_sha==seal_sha and a.require_sources()==sources,'recovered execution evidence remains unchanged')
        g.need(inp.raw13(pins)==raw,'original raw reference operands unchanged')
        report.update(status='RECOVERED_M16_DIAGNOSTIC_REFERENCE_COMPLETE',sources=sources,recovery_seal_sha256=seal_sha,
          fixed_original_sha256=a.FIXED,outputs=inventory,comparison=comparison,capture=info,
          native_before=native,native_after=after['native_posthoc'],input_records=records,
          reference_source_and_operand_postchecks=True,host_cpu_seconds=time.process_time()-cpu,
          host_wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        log.finish(counters=counters);report['safe_last_stage']=safe_last(OUT/'STAGES.jsonl');c.save(OUT/'RESULT.json',report)
        print(json.dumps(dict(status=report['status'],numerical_pass=comparison['numerical_pass'],original_model_run='FAIL',formal_reference_contract=False)));return 0
    except BaseException as e:
        original=traceback.format_exc()
        try:
            if log.active:log.failure(log.active[0],'TIMEOUT' if isinstance(e,TimeoutError) else 'VALIDATION' if isinstance(e,ValueError) else 'INTERNAL',counters=counters)
        except BaseException:pass
        report.update(status='RECOVERED_M16_REFERENCE_FAILED',error_type=type(e).__name__,error=str(e),traceback=original,
          host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-start)
        try:report['safe_last_stage']=safe_last(OUT/'STAGES.jsonl');c.save(OUT/'RESULT.json',report)
        except BaseException:pass
        print(json.dumps(dict(status='RECOVERED_M16_REFERENCE_FAILED')));return 1
    finally:signal.setitimer(signal.ITIMER_REAL,0)

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args(argv)
    if not args.execute:print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    return run()
if __name__=='__main__':raise SystemExit(main())
