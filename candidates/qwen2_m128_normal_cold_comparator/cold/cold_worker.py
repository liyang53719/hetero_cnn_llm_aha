"""Exact supervised normal binding only; never loads Matrix ELF or DUT inputs."""
import argparse,hashlib,importlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from supervisor_common import need,read_checked,write_new,file_id
from admission import claim

EXTRA_MODULES=('runner','registry','bridge','stream','oracle_path_gate',
               'rope_operand_capture.rope_capture','terminal_comparator')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True);parser.add_argument('--config-sha',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--capability-fd',type=int,required=True)
    args=parser.parse_args();cfg=read_checked(args.config,args.config_sha);out=Path(args.output).resolve(strict=True)
    claim(args.capability_fd,cfg,args.config_sha,out)
    need(not any(k.startswith('LD_') for k in os.environ),'loader environment forbidden')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize,'exact cold interpreter flags')
    sys.path.insert(0,str(Path(cfg['normal_adapter_root']).parent))
    from qwen2_fullgraph_normal_binding import adapter,initialization,safe_metadata
    need(file_id(adapter.__file__)==cfg['files'][str(Path(adapter.__file__).resolve())],'original adapter identity')
    child=out/'binding'
    code=adapter.main(['--config',str(Path(args.config).resolve()),'--config-sha',args.config_sha,'--output',str(child)])
    prior=json.loads((child/'ADAPTER_RESULT.json').read_text())
    need(code==0 and prior['status']=='PASS_NORMAL_FULLGRAPH_BINDING_ONLY','original 15-role/9-method normal gate failed')
    # These extra modules contain only stdlib definitions and pinned metadata.
    # Normal source execution is attested; no AST-definition runtime aliases.
    from qwen2_ordered_fullgraph_entry import runtime_binding,cold_policy
    root=Path(cfg['old_candidate_root']);files={str(Path(p).relative_to(root)):v for p,v in cfg['files'].items() if Path(p).is_relative_to(root)}
    cold=importlib.import_module('cold_import');inventory=importlib.import_module('module_inventory')
    extras={};extra_error=None;gate=runtime_binding.ProjectCodeGate(root,files)
    sites=cold_policy.metadata_sites(cfg['source_root'],cfg['files'])
    Guard=cold_policy.guard_class(cold.ColdGuard,sites,cfg['files'])
    task_guard=Guard(cfg,cfg['files'],child);callback=task_guard.profile
    need(sys.getprofile() is None,'unexpected preexisting task profiler')
    sys.setprofile(callback)
    try:
        with gate:
            for name in EXTRA_MODULES:
                extras[name]=importlib.import_module('qwen2_ordered_fullgraph_entry.'+name)
    except BaseException as error:
        extra_error={'type':type(error).__name__,'detail':str(error)}
    finally:
        profile_errors=cold.stop_task_profile(task_guard,callback)
    if profile_errors and extra_error is None:
        extra_error={'type':'TaskProfileFailure','detail':'task callback changed or recorded forbidden call'}
    # Even failed imports preserve the complete resulting inventory before audit.
    target=child/'final_normal_inventory';target.mkdir()
    modules=dict(sys.modules)
    # Preserve both complete raw inventories BEFORE any validation.
    cold.write_json(target/'MODULES_RAW.json',cold.raw_modules(modules))
    maps=Path('/proc/self/maps').read_text();cold.write_text(target/'MAPS_RAW.txt',maps)
    cold.write_json(child/'EXTRA_IMPORT_STATUS.json',dict(error=extra_error,events=gate.events,completed=list(extras),task_profile_errors=profile_errors,task_profile_blocked=task_guard.blocked))
    namespaces,repetitions=cold_policy.namespace_registration(modules,cfg['namespaces'])
    synthetic=cold.observer_registration(modules['_qualified_runtime_observer'],cfg['observer_root'])
    audit=inventory.collect_modules(modules,cfg['files'],namespaces=namespaces,synthetic=synthetic,registered_objects=cfg['registered_module_objects'])
    cold.write_json(target/'MODULE_AUDIT.json',audit)
    mapped=cold.collect_maps(maps,cfg['files'],cfg['elf'],cfg['mapping_allowlist'])
    cold.write_json(target/'MAP_AUDIT.json',mapped)
    repetition=cold_policy.qualify_namespace_repetitions(audit,repetitions,modules)
    cold.write_json(target/'NAMESPACE_QUALIFICATION.json',repetition)
    native_objects=safe_metadata.snapshot(modules,(*initialization.NAMES,'yaml','yaml.cyaml','yaml._yaml'))
    cold.write_json(target/'DEPENDENCY_OBJECTS_RAW.json',native_objects)
    need(not mapped['failures'] and not mapped['matrix_elf_loaded'],'cold mappings differ or Matrix loaded')
    need(all(not row['errors'] for row in native_objects),'dependency raw object inventory errors')
    dependency=initialization.qualify(modules,prior['before_native_import'],prior['native_import_events'],cfg['yaml_root'],cfg['yaml_extension_sha256'],mapped,audit)
    remaining=repetition['remaining_failures']
    need({e['name'] for e in remaining}==set(initialization.NAMES) and all(e['code']=='unregistered_no_file_module' for e in remaining),'unknown remaining module failure')
    need(not any(k=='torch' or k.startswith(('torch.','transformers')) for k in modules),'ML/oracle imported')
    cold.write_json(child/'EXACT_COLD_RESULT.json',dict(status='PASS_EXACT_M128_NORMAL_COLD_ONLY' if extra_error is None else 'FAIL_EXTRA_NORMAL_IMPORT',config_sha256=args.config_sha,
        original_binding_result=prior,extra_module_exec_events=gate.events,extra_modules=list(extras),extra_import_error=extra_error,
        dependency_qualification=dependency,roles=15,service_methods=9,matrix_elf_loaded=False,
        services_constructed=False,jobs_submitted=False,user_tensor_read=False,
        full_native_mapping_qualified=False,numeric_execution_authorized=False,
        extra_import_task_monitor_scope='Original TaskGuard covers source/observer task calls; new adapter helpers are source-attested definitions, not a broad function sandbox'))
    return 0 if extra_error is None else 1


if __name__=='__main__':
    raise SystemExit(main())
