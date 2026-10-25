"""Narrow live association for pinned PyYAML's normal Cython initialization.

Does not claim to observe internal C module-creation calls. Original inventory
failures remain immutable. No arbitrary no-file module is accepted.
"""
import importlib.machinery
from pathlib import Path
import types

NAMES=('cython_runtime','_cython_3_1_4')
META={'__name__','__doc__','__package__','__loader__','__spec__'}


def need(value,message):
    if not value:raise ValueError(message)


def qualify(modules, native_before, native_events, root, expected_elf_sha, maps, audit):
    root=Path(root).resolve();elf=root/'yaml/_yaml.cpython-312-x86_64-linux-gnu.so'
    need(native_events and native_before=={name:False for name in NAMES},'Cython names preexisting or native import not observed')
    need(all(e.get('module')=='yaml._yaml' and e.get('origin') in (None,str(elf)) for e in native_events) and
         any(e.get('origin')==str(elf) for e in native_events),
         'exact native extension import origin not observed')
    y=modules.get('yaml');extension=modules.get('yaml._yaml');cyaml=modules.get('yaml.cyaml')
    need(all(type(m) is types.ModuleType for m in (y,extension,cyaml)),'normal yaml modules missing')
    need(vars(y).get('__with_libyaml__') is True,'silent pure Python yaml fallback')
    need(Path(vars(y).get('__file__','')).resolve()==root/'yaml/__init__.py' and
         Path(vars(cyaml).get('__file__','')).resolve()==root/'yaml/cyaml.py','yaml source origin differs')
    values=vars(extension);spec=values.get('__spec__');loader=values.get('__loader__')
    need(type(spec) is importlib.machinery.ModuleSpec and type(loader) is importlib.machinery.ExtensionFileLoader and
         spec.loader is loader and spec.name=='yaml._yaml' and spec.origin==str(elf) and values.get('__file__')==str(elf),
         'normal yaml extension loader/origin differs')
    mapped=[r for r in maps.get('mappings',[]) if r.get('path')==str(elf)]
    need(mapped and all(r.get('match') is True and r.get('sha256')==expected_elf_sha and not r.get('reasons') for r in mapped),
         'actual exact yaml ELF map missing or changed')
    rows={r['name']:r for r in audit.get('modules',[])}
    result={}
    for name in NAMES:
        module=modules.get(name);row=rows.get(name)
        need(type(module) is types.ModuleType and row is not None and row.get('object_id')==hex(id(module)),
             'live canonical Cython module object differs: '+name)
        data=vars(module)
        need(all(type(key) is str for key in data),'non-string Cython module member name')
        need(data.get('__name__')==name and data.get('__file__') is None and data.get('__spec__') is None and
             data.get('__loader__') is None and data.get('__package__') is None,'Cython module metadata differs: '+name)
        need(row.get('errors')==[{'code':'unregistered_no_file_module','detail':name}],
             'Cython original audit has additional errors: '+name)
        result[name]={'object_id':hex(id(module)),'keys':sorted(data),'original_errors':row['errors']}
    runtime=vars(modules[NAMES[0]])
    need(set(runtime)<=META|{'cline_in_traceback'} and
         ('cline_in_traceback' not in runtime or type(runtime['cline_in_traceback']) is bool),'foreign Cython runtime member')
    shared=vars(modules[NAMES[1]])
    need(set(shared)<=META|{'cython_function_or_method','_common_types_metatype'} and
         {'cython_function_or_method','_common_types_metatype'}<=set(shared),'foreign Cython shared type member')
    function_type=shared['cython_function_or_method'];meta_type=shared['_common_types_metatype']
    # Member names are static keys in the exact native-created module dict.
    # Do not evaluate C metatype metadata descriptors to derive a type name.
    need(type(function_type) is meta_type and type(meta_type) is type,
         'shared Cython type identity differs')
    linked=[]
    for name in ('get_version','get_version_string'):
        fn=values.get(name)
        need(fn is not None and type(fn) is function_type,
             'extension dictionary export type not linked: '+name)
        linked.append(name)
    return {'status':'PASS_BOUNDED_DEPENDENCY_INITIALIZATION_ASSOCIATION','modules':result,
            'extension_exports_linked':linked,'actual_extension_mapping':True,'cyaml_enabled':True,
            'internal_c_creation_call_observed':False,'original_audit_modified':False,
            'function_globals_descriptor_evaluated':False,'function_internal_globals_identity_claimed':False,
            'association':'Exact native module dictionary exports share the exact Cython common type object.'}


def whole_result(old_result, qualification, audit, expected_targets):
    need(old_result.get('status')=='FAIL_NORMAL_BINDING','unexpected original wrapper status')
    need(all(item.get('kind')=='bytecode_cache_not_admitted' for item in old_result.get('blocked',[])),
         'original guard recorded a non-cache rejection')
    binding=old_result.get('binding') or {};service=old_result.get('service_binding') or {}
    need(binding.get('module_targets')==expected_targets and len(expected_targets)==15,'complete 15 runtime roles missing')
    expected=('acquire','accept_group','accept_step','retire_result','retire_done','retire_legacy_reply','retire_owner_response','release','abort')
    need(set(service)==set(expected) and all(v.get('normal_source_bound') is True for v in service.values()),'complete nine source method bindings missing')
    for name,value in service.items():
        need(value.get('class')==('OfficialMatrixService' if name=='acquire' else 'MatrixService') and value.get('method')==name,
             'wrong service inheritance binding')
    permitted=set(NAMES)
    failures=[f for f in audit.get('failures',[]) if f.get('code')!='namespace_path_mismatch']
    need({f.get('name') for f in failures}==permitted and all(f.get('code')=='unregistered_no_file_module' for f in failures),
         'unknown or additional module failures')
    errors=old_result.get('errors',[])
    need(errors and all(e.get('gate')=='modules' and
         {f.get('name') for f in e.get('qualification',{}).get('remaining_failures',[])}==permitted and
         all(f.get('code')=='unregistered_no_file_module' for f in e['qualification']['remaining_failures']) for e in errors),
         'old wrapper has a non-Cython failure')
    need(qualification['status']=='PASS_BOUNDED_DEPENDENCY_INITIALIZATION_ASSOCIATION','dependency initialization gate')
    return {'status':'PASS_NORMAL_FULLGRAPH_BINDING_ONLY','roles':15,'service_method_bindings':9,
            'old_wrapper_status':old_result['status'],'old_wrapper_original_errors_preserved':True,
            'qualification':qualification,'fullgraph_numeric_status':'TEMP_NOT_EXECUTED',
            'native_task_executed':False,'user_tensor_read':False,'matrix_elf_loaded':False}
