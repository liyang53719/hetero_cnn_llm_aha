"""One exact future M128 DUT execution, only via reviewed one-use pipe launcher.

This file is preparation, not launch authorization. No target import, input
read, native load or numerical operation occurs merely by importing this file.
"""
import argparse,hashlib,importlib,json,os,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import need,file_id,write_new,write_payload


def startup_inventory(out):
    targets={};vanished=[]
    for name in os.listdir('/proc/self/fd'):
        try:targets[int(name)]=os.readlink('/proc/self/fd/'+name)
        except FileNotFoundError:vanished.append(int(name))
    maps=Path('/proc/self/maps').read_text()
    write_new(out/'STARTUP_FDS_RAW.json',dict(fd_targets=targets,vanished_during_scan=vanished,
        note='vanished descriptor is normally the closed proc enumeration fd; live targets are re-fstat checked by gate'))
    (out/'STARTUP_MAPS_RAW.txt').write_text(maps)
    return targets,maps


def install_oracle(config,out):
    # Only these tiny exact full-source bootstrap definitions execute before the
    # oracle audit hook. No task/runtime module or payload is imported here.
    root=Path(config['candidate_root'])
    for name in ('__init__.py','oracle_path_gate.py'):
        need(file_id(root/name)==config['runtime_files'][str(root/name)],'oracle gate bootstrap source drift')
    sys.path.insert(0,str(root.parent))
    gate_module=importlib.import_module('qwen2_ordered_fullgraph_entry.oracle_path_gate')
    need(Path(gate_module.__file__).resolve()==root/'oracle_path_gate.py','oracle gate normal source origin')
    gate=gate_module.ExactOraclePathGate([config['oracle_root']],sorted(config['oracle_files']))
    fds,maps=startup_inventory(out)
    gate.install(fds,maps)
    gate.require_clean()
    write_new(out/'ORACLE_ACTIVATION.json',dict(report=gate.report(),
        scope='Installed before every task/source/metadata initialization; all relative open names denied including dir_fd ambiguity',
        limits='Python audited open/mmap plus inherited FD/maps check; not a kernel sandbox or native syscall interception'))
    return gate,gate_module.ExactOraclePathGate


def verify_tempdir(out,gettempdir):
    need(Path(gettempdir()).resolve()==Path(out)/'tmp','metadata TMPDIR cache must be inside this fresh run')


def terminal_guard(gate,gate_type):
    need(type(gate) is gate_type and gate.installed and gate.comparison_attempted and gate.state=='COMPARING',
        'exact one live-terminal comparison window required')
    gate.require_clean()


def event_totals(stream,path,limits):
    counts={name:0 for name in stream.NAMES};groups={0:0,2:0};iterator=stream.replay(path,**limits)
    while True:
        try:event=next(iterator)
        except StopIteration as stop:receipt=stop.value;break
        name,edge,values=event;counts[name]+=1
        if name=='accept_group':groups[values[4]]+=1
    return validate_service_totals(counts,groups,receipt,limits)


def validate_service_totals(counts,groups,receipt,limits):
    expected={'acquire':1,'accept_group':19200,'accept_step':847872,'retire_result':799488,
              'retire_done':19200,'retire_legacy_reply':792576,'retire_owner_response':1,'release':1,'abort':0}
    # Counts supplement, never replace, the original stream lifecycle replay.
    need(counts==expected and groups=={0:12288,2:6912},'complete M128 QK2/PV0 service workload differs')
    need(receipt['complete'] is True and receipt['count']==2478339,'complete successful event count required')
    return dict(receipt=receipt,counts=counts,groups=groups,expected_success_events=2478339,
        resource_event_capacity=limits['max_events'],hardware_cycles=None)


def retain_terminal(out,actual,registry,values):
    folder=out/'actual_terminal';folder.mkdir()
    manifest={}
    for name,value in sorted(actual.items()):
        need(name.replace('_','').isalnum(),'actual output name')
        raw=value.tobytes()
        manifest[name]=dict(write_payload(folder/(name+'.bin'),raw),shape=registry['entries'][name]['shape'])
    for name,key in (('x','readonly_x'),('silu','sealed_silu')):
        manifest[name]=write_payload(folder/(name+'.bin'),values[key])
    for name in ('cos','sin'):
        manifest[name]=dict(write_payload(folder/(name+'.bin'),values['rope_operands'][name]),shape=values['rope_physical_shape'])
    write_new(folder/'MANIFEST.json',dict(actual=manifest,source='Original terminal arrays and sealed original x/SiLU/RoPE bytes; no reconstructed nodes'))
    return manifest


def annotate_comparison(response,provenance):
    """Report metadata projection only; retain every original numeric field."""
    historical=response['configuration_difference']
    need(type(historical) is dict and historical['project_rotary_positions']==256 and
         historical['official_max_position_embeddings']==32768,'pinned original comparator note differs')
    result=dict(response)
    result['historical_comparator_configuration_note']=dict(historical)
    result['configuration_difference']=dict(
        historical_project_reference=dict(rotary_positions=provenance['historical_project_reference_rotary_positions'],
            origin='Unmodified comparator r2 historical diagnostic note, not actual DUT table capacity'),
        actual_DUT_provider=dict(public_table_capacity=provenance['actual_DUT_public_table_capacity'],
            canonical_generated_positions=provenance['canonical_generated_positions'],active_rows=provenance['active_rows'],
            table_shape=provenance['table_shape'],generated_position_range=provenance['generated_position_range'],
            inactive_zero_position_range=provenance['inactive_zero_position_range'],source=provenance['source'],
            generation_source_contract=provenance['provider_generation_source_contract'],provider_pin=provenance['actual_provider_pin']),
        official_reference=dict(max_position_embeddings=provenance['official_max_position_embeddings'],
            rope_theta=provenance['official_rope_theta'],official_config_modified=False),
        positions_compared=historical['positions_compared'],numeric_metrics_or_thresholds_modified=False,
        isolated_configuration_causality_claimed=False)
    return result


def execute(config,config_sha,out,cap):
    gate,gate_type=install_oracle(config,out)
    from runtime_admission import normal_initialize,snapshot
    from native_binding import load_library
    router=None;components=None;before=None;events=[];result=None;error=None;native=False;stage='ORACLE_INSTALLED'
    try:
        runtime,router,components,before,events=normal_initialize(config,out,gate)
        stage='NORMAL_QUALIFIED'
        import tempfile
        verify_tempdir(out,tempfile.gettempdir)
        closure=importlib.import_module('runtime_closure')
        closure.verify_graph(config['runtime_graph'],config['runtime_files'])
        library,identity=load_library(config,out)
        runtime.matrix.configure_library(library)
        runtime.library=library;runtime.selected=runtime.dense.selected_library(library)
        native=True;stage='NATIVE_ABI_CONFIGURED'
        write_new(out/'NATIVE_BINDING.json',identity)
        snapshot(config,out,'NATIVE_LOADED',components,before,events,native=True)
        raw={};providers={}
        for role,record in config['providers'].items():
            payload=Path(record['path']).read_bytes()
            need(len(payload)==record['bytes'] and hashlib.sha256(payload).hexdigest()==record['sha256'],'provider identity '+role)
            raw[role]=payload;providers[role]=runtime.base.bytes_provider(payload)
        write_new(out/'PROVIDER_ADMISSION.json',dict(providers={role:{'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()} for role,value in raw.items()},
            immutable_bytes=True,raw13_not_supplied_to_DUT=True,oracle_not_supplied_to_DUT=True))
        profile=dict(config['profile']);profile['files']=config['runtime_files']
        runner=importlib.import_module('qwen2_ordered_fullgraph_entry.runner')
        comparator=importlib.import_module('qwen2_ordered_fullgraph_entry.terminal_comparator')
        compare=comparator.make_comparator(Path(config['oracle_root'])/'capture',config['oracle_exports'],rows=128,
            terminal_guard=lambda:terminal_guard(gate,gate_type))
        captured={}
        def callback(actual,observation,registry,*,terminal_values):
            terminal_guard(gate,gate_type)
            captured.update(retain_terminal(out,actual,registry,terminal_values))
            original_response=compare(actual,observation,registry,terminal_values=terminal_values)
            response=annotate_comparison(original_response,config['rotary_provenance'])
            write_new(out/'TERMINAL_COMPARISON.json',response)
            return response
        admission=dict(execution_authorized=True,source_manifest_sha256=config['source_manifest_sha256'],
            profile_sha256=config['profile_sha256'],elf_sha256=config['runtime_files'][config['elf']]['sha256'],
            runtime_manifest_sha256=config['runtime_manifest_sha256'],input_manifest_sha256=config['input_manifest_sha256'],run_id=cap['run_id'])
        stage='ORIGINAL_PUBLIC21_RUNNING'
        actual,report=runner.run_actual(runtime,providers,profile,out/'dut',enabled=True,admission=admission,
            compare_after_terminal=callback,oracle_gate=gate)
        stage='WHOLE_TERMINAL_RETURNED'
        gate.require_clean();need(gate.state=='CLOSED' and gate.comparison_attempted,'one terminal comparison completed')
        need(report['status']=='ACTUAL_INVENTORY_COMPLETE_NUMERIC_TEMP','original runner terminal inventory failed')
        comparison=report['comparison']
        need(comparison['observed_domain_passed'] is True and comparison['full29_numeric_pass'] is False,'observed numerical domain failed or full29 overclaim')
        stream=importlib.import_module('qwen2_ordered_fullgraph_entry.stream')
        limits=dict(expected_groups=19200,expected_events=2478339,max_events=config['resources']['event_limit'],max_bytes=config['resources']['trace_bytes'])
        protocol=event_totals(stream,out/'dut/attention_service_events.q2evt',limits)
        write_new(out/'SERVICE_PROTOCOL.json',protocol)
        for role,payload in raw.items():
            record=config['providers'][role]
            need(type(payload) is bytes and len(payload)==record['bytes'] and hashlib.sha256(payload).hexdigest()==record['sha256'],'retained provider drift '+role)
        router.require_clean()
        result=dict(status='PASS_OBSERVED_DOMAIN_M128_DUT_NOT_FULL29',passed=True,observed_domain_passed=True,
            full29_numeric_pass=False,hardware_acceptance=False,actual_terminal_verified=True,event_protocol_passed=True,
            config_sha256=config_sha,run_id=cap['run_id'],oracle=gate.report(),runtime_policy=router.report(),
            comparison=comparison,service_protocol=protocol,actual_terminal_files=len(captured),cold_provenance_scope='Normal source loading only, not inherited native/ABI/numerical PASS')
    except BaseException as exc:
        error=exc
        result=dict(status='FAIL',passed=False,stage=stage,error=dict(type=type(exc).__name__,detail=str(exc)),
            full29_numeric_pass=False,hardware_acceptance=False,oracle=gate.report(),
            runtime_policy=None if router is None else router.report())
    finally:
        # Always persist complete raw inventory first. Audit failure is failure,
        # but never substitutes an active original DUT exception identity.
        audit_error=None
        if components is not None:
            try:snapshot(config,out,'WORKER_FINAL',components,before,events,native=native)
            except BaseException as exc:audit_error=dict(type=type(exc).__name__,detail=str(exc))
        else:
            cold=sys.modules.get('cold_import')
            modules=dict(sys.modules)
            raw=cold.raw_modules(modules) if cold is not None else [{'name':name,'file':vars(module).get('__file__') if hasattr(module,'__dict__') else None} for name,module in modules.items()]
            write_new(out/'FAILURE_MODULES_RAW.json',raw)
            (out/'FAILURE_MAPS_RAW.txt').write_text(Path('/proc/self/maps').read_text())
        if audit_error is not None:
            result.update(passed=False,status='FAIL',final_runtime_audit_error=audit_error)
        # Snapshot itself can import pinned source. Finalize classification only
        # after it, and refresh the report on both success and original failure.
        if router is not None:
            try:router.require_clean()
            except BaseException as exc:
                result.update(passed=False,status='FAIL',final_runtime_policy_error=dict(type=type(exc).__name__,detail=str(exc)))
            result['runtime_policy']=router.report()
        result['rotary_provenance']=config['rotary_provenance']
        write_new(out/'COMPARISON_PROVENANCE.json',config['rotary_provenance'])
        write_new(out/'WORKER_RESULT.json',result)
    if error is not None:raise error
    need(result['passed'],'final runtime qualification failed')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--config-sha',required=True)
    p.add_argument('--output',required=True);p.add_argument('--cap-fd',type=int,required=True)
    p.add_argument('--parent-pid',type=int,required=True);p.add_argument('--parent-start-ticks',required=True);a=p.parse_args()
    config_path=Path(a.config).resolve();need(file_id(config_path)['sha256']==a.config_sha,'config hash')
    config=json.loads(config_path.read_text());out=Path(a.output).resolve()
    from admission import claim
    cap=claim(a.cap_fd,config,a.config_sha,out,a.parent_pid,a.parent_start_ticks)
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize,'fixed worker interpreter flags')
    need(not any(k.startswith('LD_') for k in os.environ),'loader overrides forbidden')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        need(os.environ.get(key)=='1','single-thread environment '+key)
    execute(config,a.config_sha,out,cap)

if __name__=='__main__':main()
