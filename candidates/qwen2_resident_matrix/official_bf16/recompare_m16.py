"""Recompare the sealed completed M16 after correcting reference-only layout.

Never runs an owner or arithmetic recipe. Original summary/FAIL is read-only.
Every saved output and observation array is checked against the original seal.
"""
import argparse
from array import array
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from . import check_numeric as n

ORIGINAL_RESULT_SHA = '1543618fb894864d1e8a97605b69b424518e9d209ee38de3aa4064ba3367b3bd'
ORIGINAL_SNAPSHOT_SHA = '88cc7fe74bbe0a982490f138c99928314c325ded5de73fc50296d5c0cf5c17e2'
RUNNER = n.PREFIX + 'check_numeric.py'


def verify_terminal(r):
    h=r['execution']['host']
    n.require(r['rows']==16 and r['status']=='PASS_BF16_DATAFLOW_NATIVE_GATE_REPORTED' and
        r['comparison']['fixed_arithmetic_pass'] and r['source_sha256']==r['source_sha256_after'] and
        h['launch_result']['status'] is None and h['launch_result']['completed']==21 and
        h['launch_result']['jobs']==h['accepted']['owner_result_fire']==17 and
        h['accepted']['result_fire']==1 and not h['reset_required'], 'original full terminal invalid')


def functional_run_ast(source):
    """Normalize only exact, reviewed read-only transport/diagnostic changes.

    The budget is host time, not a numerical threshold. Failure preservation
    runs only after the original failure and cannot make it a success. Any
    altered arithmetic, driver call, terminal check or exception path remains
    in the comparison and is rejected against the actual M16 frozen source.
    """
    tree=ast.parse(source)
    run=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run')
    def shape(node):return ast.dump(node,include_attributes=False)
    def statement(text):return ast.parse(text).body[0]
    prefix_time=shape(statement("report['prefix_host_wall_seconds'] = time.monotonic() - started"))
    terminal_time=shape(statement("report['whole_terminal_host_wall_seconds'] = time.monotonic() - started"))
    failure=shape(statement("try:\n    report['failure_capture'] = retain_failed_run(out, locals().get('physical'), locals().get('capture'))\nexcept Exception as preservation_error:\n    report['failure_capture_error'] = str(preservation_error)"))
    prefix_status=shape(statement("report['status'] = 'ACTUAL_PREFIX_COMPLETE'"))
    save=shape(statement('save()'))
    memory=shape(statement("if 'physical' in locals(): report['failed_memory'] = physical.report()"))
    # The fresh/budget guard is the second statement, before all execution.
    new_guard=statement("require(not out.exists() and 0 < wall_budget <= 1800, 'fresh bounded official model run required')")
    old_guard=statement("require(not out.exists() and 0 < wall_budget <= 1200, 'fresh bounded official model run required')")
    if len(run.body)>1 and shape(run.body[1])==shape(new_guard):run.body[1]=old_guard
    class DiagnosticOnly(ast.NodeTransformer):
        def generic_visit(self,node):
            if hasattr(node,'body') and isinstance(node.body,list):
                original=node.body
                keep=[]
                for i,item in enumerate(original):
                    previous=original[i-1] if i else None
                    following=original[i+1] if i+1<len(original) else None
                    match=shape(item)
                    prefix=(match==prefix_time and i>=2 and shape(original[i-2])==prefix_status
                        and shape(previous)==save and isinstance(following,ast.With)
                        and shape(following.items[0].context_expr)==shape(ast.Name(id='capture',ctx=ast.Load())))
                    terminal=(match==terminal_time and isinstance(previous,ast.With)
                        and shape(previous.items[0].context_expr)==shape(ast.Name(id='capture',ctx=ast.Load()))
                        and isinstance(following,ast.Expr) and isinstance(following.value,ast.Call)
                        and isinstance(following.value.func,ast.Name) and following.value.func.id=='require'
                        and any(isinstance(c,ast.Constant) and c.value=='whole public terminal missing'
                                for c in following.value.args))
                    failed=(match==failure and isinstance(node,ast.ExceptHandler) and node.name=='error'
                        and isinstance(node.type,ast.Name) and node.type.id=='Exception'
                        and previous is not None and shape(previous)==memory
                        and following is not None and shape(following)==save
                        and i+2==len(original)-1 and isinstance(original[i+2],ast.Raise)
                        and original[i+2].exc is None and original[i+2].cause is None)
                    if not (prefix or terminal or failed):keep.append(item)
                node.body=keep
            return super().generic_visit(node)
        def visit_Attribute(self,node):
            if node.attr=='OfficialAttentionMonitoringObservation':
                node.attr='OfficialAttentionObservation'
            return self.generic_visit(node)
    return ast.dump(DiagnosticOnly().visit(run),include_attributes=False)


def recompare(directory,out):
    directory,out=Path(directory).resolve(),Path(out).resolve()
    n.require(os.environ.get('OPENBLAS_NUM_THREADS')=='1' and os.environ.get('OMP_NUM_THREADS')=='1',
              'postprocessing must use original single-thread numerical diagnostic environment')
    n.require(not out.exists(),'fresh postprocessing output required')
    original=directory/'summary.json'
    n.require(n.file_sha(original)==ORIGINAL_RESULT_SHA,'original M16 result changed')
    r=json.loads(original.read_text());verify_terminal(r)
    snapshot=Path(r['snapshot'])
    n.require(n.file_sha(snapshot)==ORIGINAL_SNAPSHOT_SHA==r['snapshot_sha256'],'original snapshot changed')
    s=json.loads(snapshot.read_text())
    n.require(s['source_sha256']==r['source_sha256'] and s['policy']==r['policy']==n.policy.POLICY,
              'original source/policy binding differs')
    for name,digest in s['source_sha256'].items():
        frozen=snapshot.parent/'frozen_sources'/name
        n.require(n.file_sha(frozen)==digest,'original frozen source changed: '+name)
        if name!=RUNNER:n.require(n.file_sha(n.ROOT/name)==digest,'actual execution source changed: '+name)
    before=(snapshot.parent/'frozen_sources'/RUNNER).read_text()
    n.require(functional_run_ast(before)==functional_run_ast(Path(n.__file__).read_text()),
              'actual run changed beyond reviewed read-only transport/host diagnostics')
    n.require(n.reference_spec(16)==s['reference'],'frozen reference provenance changed')
    _,dense,_,native=n.runtime()
    n.require(dense.verify_library(r['binaries']['compile_receipt'])['library']==r['binaries']['library'] and
        n.file_sha(r['binaries']['library'])==r['binaries']['library_sha256'],'actual arithmetic library changed')
    actual={}
    for name,rec in r['sealed_actual_outputs'].items():
        raw=(directory/('actual_'+name+'.f32le')).read_bytes()
        n.require(len(raw)==rec['bytes'] and n.sha(raw)==rec['sha256'],'sealed actual changed: '+name)
        v=array('f');v.frombytes(raw);actual[name]=v
    silu=(directory/'actual_silu.f32le').read_bytes()
    n.require(n.sha(silu)==r['sealed_silu_sha256'],'sealed SiLU changed')
    o=r['observation']; fields={}; raws={}
    n.require(json.loads((directory/'attention_observation/summary.json').read_text())==o,
              'observation receipt differs from sealed terminal')
    for name,rec in o['fields'].items():
        raw=(directory/'attention_observation'/(name+'.u32le')).read_bytes()
        present=(directory/'attention_observation'/(name+'.presence')).read_bytes()
        count=(directory/'attention_observation'/(name+'.count.u16le')).read_bytes()
        n.require((n.sha(raw),n.sha(present),n.sha(count))==
            (rec['raw_sha256'],rec['presence_sha256'],rec['frequency_sha256']),
            'sealed observed data changed: '+name)
        n.require(len(raw)==rec['words']*4 and len(present)==rec['words'] and
                  set(present)<=set((0,1)) and sum(present)==rec['observed_words'],
                  'observation presence/extent differs')
        raws[name]=raw;fields[name]=dict(shape=rec['shape'],observed=present)
    capture=SimpleNamespace(fields=fields,_bytes=raws.__getitem__)
    inputs=n.load_inputs(s['input_spec'],16,s['reference'])
    n.require(n.base.identities(inputs)==s['loaded_inputs']==r['loaded_inputs'],'raw input changed')
    comparison=n.compare(s,actual,inputs,capture,silu,native)
    n.require(comparison['fixed_arithmetic_pass'] and comparison['whole_outputs']==r['comparison']['whole_outputs'] and
              comparison['actual_observed_nodes']==r['comparison']['actual_observed_nodes'],
              'reference-only repair changed fixed arithmetic comparison')
    for method,old in r['comparison']['methods'].items():
        for name,v in old['stages'].items():
            if name not in ('q','k'):
                n.require(comparison['methods'][method]['stages'][name]==v,'unrelated native comparison changed')
    result=dict(status='PASS_RECOMPARISON_OF_SEALED_M16',rows=16,policy=n.policy.POLICY,
        original_result_sha256=ORIGINAL_RESULT_SHA,original_snapshot_sha256=ORIGINAL_SNAPSHOT_SHA,
        original_fail_preserved=True,actual_execution_repeated=False,reference_forward_repeated=False,
        actual_source_sha256=s['source_sha256'],source_sha256=n.source_hashes(),
        postprocessor_sha256=n.file_sha(Path(__file__)),arithmetic_and_physical_driver_sources_unchanged=True,
        functional_run_ast_unchanged_except_readonly_transport=True,
        host_diagnostics_only_changes=['budget_max_1800_default_1200', 'host_phase_timestamps', 'failure_actual_preservation'],
        input_spec=s['input_spec'],binaries=s['binaries'],sealed_actual_outputs=r['sealed_actual_outputs'],
        execution=r['execution'],comparison=comparison,
        source_sha256_after=n.source_hashes(),
        diagnostic_threads=dict(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
        full_29_node_acceptance=False,hardware_execution=False)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(n.encoded(result))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actual',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r=recompare(a.actual,a.out)
    print(json.dumps(dict(status=r['status'],failed={k:v['failed_stages'] for k,v in r['comparison']['methods'].items()})))


if __name__=='__main__':main()
