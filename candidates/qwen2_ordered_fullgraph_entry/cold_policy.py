"""Narrow task prohibitions for source-pinned fullgraph initialization.

Not a general Python sandbox. Source loading/metadata helpers are allowed;
exact read, ELF, subprocess and complete module code gates remain independent.
"""
import ast
from pathlib import Path
import types

TASK_CALLS = frozenset(('configure_library','build_library','compile_fresh','load_library',
    'td_reset','sf_reset','reset','run','op','_op','tick','_matrix_step','run_owner',
    'execute_public_prefix','execute_public_suffix','execute_attention_owner','execute_windows',
    'run_recipe','install','capture_reference','acquire','accept_group','accept_step',
    'retire_result','retire_done','retire_legacy_reply','retire_owner_response','release','abort',
    'load_inputs','main','__new__'))


def metadata_sites(source_root, files):
    """Inventory all eager constructor calls in method defaults and module data.

    Method bodies are not traversed as initialization. The actual permission
    additionally requires a frozen dataclass, exact class/method/globals and
    source-pinned definition caller, so a Services name is not an exemption.
    """
    root=Path(source_root);sites=[]
    for path in sorted(Path(p) for p in files if Path(p).is_relative_to(root) and Path(p).suffix=='.py'):
        tree=ast.parse(path.read_bytes(),filename=str(path))
        def calls(expr, caller, kind):
            if expr is None:return
            for call in ast.walk(expr):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Name):
                    sites.append(dict(path=str(path),caller=caller,line=call.lineno,
                                      constructor=call.func.id,kind=kind,expression=ast.unparse(call)))
        def body(nodes, caller='<module>'):
            for node in nodes:
                if isinstance(node,ast.ClassDef):body(node.body,node.name if caller=='<module>' else caller+'.'+node.name)
                elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    for value in (*node.args.defaults,*node.args.kw_defaults):calls(value,caller,'definition_default')
                elif caller=='<module>' and isinstance(node,(ast.Assign,ast.AnnAssign)):
                    calls(node.value,caller,'module_constant')
        body(tree.body)
    return sites


def metadata_default(frame, sites, files):
    code=frame.f_code
    if code.co_name!='__init__' or code.co_filename!='<string>':return False
    obj=frame.f_locals.get('self');cls=type(obj);params=vars(cls).get('__dataclass_params__')
    fn=vars(cls).get('__init__');caller=frame.f_back
    if (not getattr(params,'frozen',False) or type(fn) is not types.FunctionType or
        fn.__code__ is not code or fn.__globals__ is not frame.f_globals or caller is None or
        caller.f_code.co_flags & 0x02):return False
    origin=frame.f_globals.get('__file__');caller_path=caller.f_code.co_filename
    if origin not in files or caller_path not in files:return False
    if frame.f_globals.get(cls.__name__) is not cls:return False
    return any(s['path']==caller_path and s['caller']==caller.f_code.co_qualname and
               s['line']==caller.f_lineno and s['constructor']==cls.__name__ for s in sites)


def guard_class(base, sites, files):
    class TaskGuard(base):
        def profile(self, frame, event, arg):
            if event!='call' or not self.task_frame(frame):return
            if self.dataclass_definition_factory(frame):return
            code=frame.f_code
            # Normal class/module bodies do not submit work. Frozen record
            # construction is allowed only at its exact eager definition site.
            if not code.co_flags & 0x02:return
            if code.co_name=='__init__':
                if metadata_default(frame,sites,files):return
                self.reject('task_execution_forbidden',str(code.co_filename)+':'+code.co_qualname)
            if code.co_name in TASK_CALLS:
                self.reject('task_execution_forbidden',str(code.co_filename)+':'+code.co_qualname)
    return TaskGuard


def namespace_registration(modules, declared):
    """Preserve duplicate ordered locations after checking every exact origin.

    Does not deduplicate or mutate a namespace. A repeated canonical source
    directory is recorded as repeated, never broadened to a foreign location.
    """
    registered={name:{'paths':list(row['paths'])} for name,row in declared.items()}
    repetitions=[]
    for name,row in declared.items():
        module=modules.get(name)
        if type(module) is not types.ModuleType or '__path__' not in vars(module):continue
        paths=vars(module)['__path__']
        raw=getattr(paths,'_path',paths)
        if type(raw) not in (list,tuple):continue
        raw=list(raw)
        if raw and all(type(p) is str and p in row['paths'] and str(Path(p).resolve())==p for p in raw):
            registered[name]={'paths':raw}
            if len(raw)>len(row['paths']):
                repetitions.append(dict(name=name,ordered_paths=raw,canonical_paths_verified=True,
                                        object_modified=False,paths_deduplicated=False))
    return registered,repetitions


def qualify_namespace_repetitions(report, repetitions, modules=None):
    """Separate decision; never rewrite the immutable original audit report."""
    rows=report.get('modules',[])
    ledger=[dict(name=row.get('name'),**error) for row in rows for error in row.get('errors',[])]
    valid=(report.get('schema')==1 and report.get('entry_count')==len(rows)
           and report.get('failures')==ledger
           and report.get('status')==('FAIL_MODULE_IDENTITY' if ledger else 'PASS_MODULE_IDENTITY'))
    if not valid:
        return {'status':'FAIL_NAMESPACE_QUALIFICATION','remaining_failures':[{'code':'invalid_original_audit_ledger'}],
                'accepted_repetition_names':[],'original_audit_modified':False,'live_snapshot_checked':False}
    permitted={item['name']:item for item in repetitions}
    accepted=[]
    for row in report.get('modules',[]):
        name=row.get('name');note=permitted.get(name)
        if note is None:continue
        paths=note['ordered_paths'];directories=row.get('namespace_directories',[])
        errors=row.get('errors',[])
        ok=(row.get('kind')=='normal_namespace_package' and row.get('__file__') is None
            and row.get('object_type')=='builtins.module'
            and row.get('module_name')==row.get('spec_name')==name
            and row.get('loader')==row.get('spec_loader')=='_frozen_importlib_external.NamespaceLoader'
            and row.get('namespace_paths')==row.get('spec_search_locations')==row.get('namespace_loader_paths')==paths
            and len(paths)>len(set(paths)) and len(errors)==1 and errors[0].get('code')=='namespace_path_mismatch'
            and directories and all(d.get('path')==d.get('realpath') and d.get('path') in paths
                                    and d.get('pinned_descendants') for d in directories)
            and all(any(d.get('path')==p for d in directories) for p in paths))
        if modules is not None:
            module=modules.get(name)
            ok=ok and type(module) is types.ModuleType and hex(id(module))==row.get('object_id')
        if ok:accepted.append(name)
    remaining=[f for f in report.get('failures',[]) if not (
        f.get('name') in accepted and f.get('code')=='namespace_path_mismatch')]
    return {'status':'FAIL_NAMESPACE_QUALIFICATION' if remaining else 'PASS_PINNED_MODULES_WITH_RECORDED_REPETITIONS',
            'remaining_failures':remaining,'accepted_repetition_names':accepted,
            'original_status':report.get('status'),'original_audit_modified':False,
            'namespace_objects_modified':False,'ordered_paths_deduplicated':False,
            'live_snapshot_checked':modules is not None,
            'scope':'Module identity only; no numeric or execution qualification.'}
