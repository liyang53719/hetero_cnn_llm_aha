"""One disposable normal fullgraph import; never a numeric launch.

Reuse the previously reviewed cold read/mapping/module gates. Source metadata initialization is permitted; explicit service/owner creation
and task entry points remain prohibited. Exact module source/code and file
gates are independent, not a blanket Python function sandbox.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import types

INITIALIZERS = {
    'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py': 'load_module',
    'candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py': 'load_module',
    'candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py': 'load_module',
    'candidates/qwen2_resident_matrix/ffn_window/model.py': '_pinned_module',
}
PROFILE = 'candidates/qwen2_resident_matrix/dense_block_reduce/profile.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--config-sha', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if sha(args.config) != args.config_sha:
        raise ValueError('exact config hash differs')
    config = json.loads(args.config.read_text())
    out = args.output.resolve();out.mkdir(exist_ok=False)
    helper_root = Path(config['cold_helper_root'])
    for name in ('cold_import.py', 'module_inventory.py'):
        path = helper_root / name
        if sha(path) != config['files'][str(path)]['sha256']:
            raise ValueError('cold helper source differs')
    for path, pin in config['candidate_files'].items():
        if sha(path) != pin['sha256'] or Path(path).stat().st_size != pin['bytes']:
            raise ValueError('candidate source differs')
    sys.path[:0] = [str(helper_root), str(Path(__file__).resolve().parent.parent), config['numpy_root']]
    cold = importlib.import_module('cold_import')
    inventory = importlib.import_module('module_inventory')
    from qwen2_ordered_fullgraph_entry import runtime_binding as binding
    from qwen2_ordered_fullgraph_entry import service_trace
    if Path(cold.__file__).resolve() != helper_root/'cold_import.py' or Path(inventory.__file__).resolve() != helper_root/'module_inventory.py':
        raise ValueError('cold helper module origin')
    files = config['files']
    root = Path(config['source_root'])
    from qwen2_ordered_fullgraph_entry import cold_policy
    sites=cold_policy.metadata_sites(root,files)
    Guard=cold_policy.guard_class(cold.ColdGuard,sites,files)
    guard = Guard(config, files, out)
    sys.addaudithook(guard.audit)
    errors = []
    receipt = None
    synthetic = {}
    service_binding = None
    def snapshot(stage):
        target=out/stage;target.mkdir()
        modules=dict(sys.modules)
        cold.write_json(target/'MODULES_RAW.json',cold.raw_modules(modules))
        maps=Path('/proc/self/maps').read_text();cold.write_text(target/'MAPS.txt',maps)
        namespaces,repetitions=cold_policy.namespace_registration(modules,config['namespaces'])
        cold.write_json(target/'NAMESPACE_REPETITIONS.json',{'repetitions':repetitions})
        mr=inventory.collect_modules(modules,files,namespaces=namespaces,
                                     synthetic=synthetic, registered_objects=config.get('registered_module_objects',{}))
        cold.write_json(target/'MODULE_AUDIT.json',mr)
        qualification=cold_policy.qualify_namespace_repetitions(mr,repetitions,modules)
        cold.write_json(target/'MODULE_QUALIFICATION.json',qualification)
        mapped=cold.collect_maps(maps,files,config['elf'],config['mapping_allowlist'])
        cold.write_json(target/'MAP_AUDIT.json',mapped)
        if qualification['remaining_failures']:
            errors.append({'stage':stage,'gate':'modules','qualification':qualification})
        if mapped['failures']:
            errors.append({'stage':stage,'gate':'maps','failures':mapped['failures']})
        cold.write_json(target/'VALIDATION.json',{'errors':errors,'status':'FAIL' if errors else 'PASS'})
    try:
        cold.write_json(out/'INITIALIZATION_SITES.json',{'sites':sites})
        rows=[cold.pin_record(Path(p),v) for p,v in sorted(files.items())]
        cold.write_json(out/'PIN_AUDIT.json',{'files':rows,'failures':[r for r in rows if not r['match']]})
        if any(not r['match'] for r in rows):raise ValueError('cold pins differ')
        snapshot('00_before_import')
        if errors:raise ValueError('preflight inventory or maps differ')
        callback=guard.profile;sys.setprofile(callback)
        try:
            runtime,receipt=binding.load_runtime(root,config['source_manifest'],config['source_manifest_sha256'])
            observer_root=Path(config['observer_root'])
            package=cold.create_observer_namespace(observer_root)
            synthetic=cold.observer_registration(package,observer_root)
            observer_files={str(Path(p).relative_to(observer_root)):pin for p,pin in files.items()
                            if Path(p).is_relative_to(observer_root)}
            with binding.ProjectCodeGate(observer_root,observer_files) as observer_gate:
                monitor=importlib.import_module('_qualified_runtime_observer.monitor')
            specs=service_trace.service_specs(runtime.binding.ProfiledMatrixService,config)
            service_binding={}
            for name,(fn,path,pin,cls,method) in specs.items():
                code=monitor.bind(fn,path,pin,cls,method,False)
                service_binding[name]={'class':cls,'method':method,'source_sha256':pin,
                                       'co_filename':code.co_filename,'normal_source_bound':True}
            receipt['observer_module_exec_events']=observer_gate.events
        finally:
            errors.extend(cold.stop_task_profile(guard,callback))
    except BaseException as error:
        sys.setprofile(None)
        errors.append({'gate':'normal_import','type':type(error).__name__,'error':str(error)})
    finally:
        sys.setprofile(None)
        snapshot('01_after_import_or_failure')
        cold.write_json(out/'RESULT.json',{'status':'FAIL_NORMAL_BINDING' if errors else 'PASS_NORMAL_BINDING_ONLY',
            'errors':errors,'binding':receipt,'service_binding':service_binding,'config_sha256':args.config_sha,'blocked':guard.blocked,
            'dependency_initialization_events':guard.events,'definition_codegen_events':guard.codegen_events,
            'numeric_executed':False,'task_services_constructed':False,'task_tensor_read':False,
            'explicit_matrix_cdll':False,'fullgraph_acceptance':'TEMP_NOT_EXECUTED'})
    return int(bool(errors))

if __name__ == '__main__':raise SystemExit(main())
