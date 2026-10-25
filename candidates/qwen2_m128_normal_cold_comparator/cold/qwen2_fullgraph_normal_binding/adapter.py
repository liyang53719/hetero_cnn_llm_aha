"""Reuse unchanged cold wrapper with one exact yaml-only dependency root.

No yaml preloading, aliases, removed cyaml, broad site-packages, or task service.
The old wrapper retains project-code, task-call, modules and maps audit gates.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--config-sha',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    raw=args.config.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.config_sha:raise ValueError('exact new config hash')
    config=json.loads(raw)
    if config['actual_numeric_authorized'] is not False:raise ValueError('normal import only')
    here=Path(__file__).resolve().parent
    for name in ('__init__.py','adapter.py','dependency.py','initialization.py','safe_metadata.py'):
        path=here/name;pin=config['files'][str(path)]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('new adapter source drift')
    sys.path.insert(0,str(here.parent))
    from qwen2_fullgraph_normal_binding import dependency
    if Path(dependency.__file__).resolve()!=here/'dependency.py':raise ValueError('foreign dependency helper')
    spec=dependency.manifest(config['dependency_manifest'],config['dependency_manifest_sha256'])
    files=dependency.verify_copy(config['yaml_root'],spec)
    if any(config['files'].get(path)!=pin for path,pin in files.items()):raise ValueError('dependency runtime pin mismatch')
    if any(name=='yaml' or name.startswith('yaml.') for name in sys.modules):raise ValueError('yaml was preloaded')
    for source,pin in config['candidate_files'].items():
        dependency.check_file(Path(source),pin)
    helper=Path(config['cold_helper_root']).resolve(strict=True)
    dependency.check_file(helper/'runtime_closure.py',config['files'][str(helper/'runtime_closure.py')])
    sys.path.insert(0,str(helper))
    closure=importlib.import_module('runtime_closure')
    if Path(closure.__file__).resolve()!=helper/'runtime_closure.py':raise ValueError('foreign runtime graph helper')
    closure.verify_graph(config['runtime_graph'],config['files'])
    old=Path(config['old_candidate_root']).resolve(strict=True)
    wrapper=old/'cold_binding.py'
    if dependency.digest(wrapper)!=config['old_wrapper_sha256']:raise ValueError('old wrapper differs')
    sys.path[:0]=[config['yaml_root'],str(old.parent)]
    module=importlib.import_module('qwen2_ordered_fullgraph_entry.cold_binding')
    if Path(module.__file__).resolve()!=wrapper:raise ValueError('old wrapper origin differs')
    from qwen2_fullgraph_normal_binding import initialization, safe_metadata
    before=None;events=[]
    def watch(event, values):
        nonlocal before
        if event=='import' and values and values[0]=='yaml._yaml':
            if before is None:before={name:name in sys.modules for name in initialization.NAMES}
            events.append({'module':values[0],'origin':values[1] if len(values)>1 else None})
    sys.addaudithook(watch)
    old_exit=module.main(['--config',str(args.config),'--config-sha',args.config_sha,'--output',str(args.output)])
    out=args.output.resolve()
    # The unchanged wrapper's complete evidence has already been persisted.
    # Preserve its FAIL if it rejects the two expected Cython no-file modules.
    original=json.loads((out/'RESULT.json').read_text())
    audit=json.loads((out/'01_after_import_or_failure/MODULE_AUDIT.json').read_text())
    maps=json.loads((out/'01_after_import_or_failure/MAP_AUDIT.json').read_text())
    # Collect all member IDs before validation; never ask unknown C objects for
    # type names, repr, __module__, __qualname__, or descriptor values.
    object_rows=safe_metadata.snapshot(dict(sys.modules),
        (*initialization.NAMES,'yaml','yaml.cyaml','yaml._yaml'))
    with (out/'DEPENDENCY_OBJECTS_RAW.json').open('x') as stream:
        json.dump({'before_native_import':before,'import_events':events,'objects':object_rows},stream,indent=2,sort_keys=True);stream.write('\n')
    errors=[];result=None
    try:
        if any(row['errors'] for row in object_rows):raise ValueError('dependency raw inventory incomplete')
        if old_exit != 1:raise ValueError('expected original module-identity-only exit 1')
        qualification=initialization.qualify(dict(sys.modules),before,events,config['yaml_root'],
            spec['files']['yaml/_yaml.cpython-312-x86_64-linux-gnu.so']['sha256'],maps,audit)
        result=initialization.whole_result(original,qualification,audit,config['expected_runtime_targets'])
    except Exception as error:
        errors.append({'gate':'dependency_initialization_qualification',
                       'message':'Qualification rejected; complete raw records are preserved.',
                       'error':safe_metadata.value_record(error)})
        result={'status':'FAIL_NORMAL_BINDING_ADAPTER','fullgraph_numeric_status':'TEMP_NOT_EXECUTED'}
    result.update(errors=errors,original_wrapper_exit=old_exit,native_import_events=events,
                  before_native_import=before,config_sha256=args.config_sha,
                  original_result_sha256=hashlib.sha256((out/'RESULT.json').read_bytes()).hexdigest())
    with (out/'ADAPTER_RESULT.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    return int(bool(errors))

if __name__=='__main__':raise SystemExit(main())
