"""Reuse reviewed normal/source/module/maps gates; numeric phase is separate.

No target import or native load on module import. Normal initialization uses the
unchanged task restrictions. The audit router never leaves a permanent cold
hook active and never obtains numeric permission by changing the old config.
"""
import hashlib,importlib,importlib.machinery,importlib.util,json,marshal,os,sys
from pathlib import Path
from common import need,file_id,write_new

_normal_observer_object=None


# Capture the trusted CPython loader methods once. Qualification is an exact
# implementation/stack check, not acceptance based on a class or module name.
_SOURCE_LOADER=importlib.machinery.SourceFileLoader
_LOADER_METHODS={name:(getattr(_SOURCE_LOADER,name),getattr(_SOURCE_LOADER,name).__code__)
                 for name in ('get_data','get_code','source_to_code','exec_module')}
_COMPILE=compile


class PinnedCacheFallback:
    """Classify denied cache reads without admitting any cache bytes.

    An open audit event is pre-I/O, not proof of a completed read or import.
    Qualification therefore requires the same exact SourceFileLoader invocation
    to submit pinned source bytes to compile and matching source-derived code to
    exec. Exec is also pre-execution: this proves source/code selection ONLY,
    not successful module-body completion, which remains the caller's duty.
    No hook is replaced, no denial deleted, and no path is temporarily allowed.
    """
    def __init__(self,router):
        self.router=router;self.events=[];self.pending={};self.compiling=False
        self.normal_denials={}

    def context(self,method):
        frame=sys._getframe(1);target=_LOADER_METHODS[method][1]
        while frame is not None and frame.f_code is not target:frame=frame.f_back
        if frame is None:return None
        loader=frame.f_locals.get('self')
        if type(loader) is not _SOURCE_LOADER:return None
        for name,(function,code) in _LOADER_METHODS.items():
            actual=getattr(loader,name,None)
            if (getattr(actual,'__func__',None) is not function or
                getattr(actual,'__code__',None) is not code):return None
        if method=='exec_module':return frame,loader,None
        get_code=frame.f_back
        if get_code is None or get_code.f_code is not _LOADER_METHODS['get_code'][1]:return None
        execution=get_code.f_back
        if (execution is None or execution.f_code is not _LOADER_METHODS['exec_module'][1] or
            execution.f_locals.get('self') is not loader or get_code.f_locals.get('self') is not loader):return None
        return execution,loader,get_code

    def fail(self,row,kind,value):
        row['status']='REJECTED';row['failure']=kind
        self.router.reject(kind,value)

    def cache_open(self,path,raw,args):
        router=self.router
        row=dict(sequence=len(self.events)+1,phase=router.phase,cache=str(path),
                 cache_bytes_admitted=False,status='PENDING_SOURCE_FALLBACK',
                 source_open_observed=False,source_bytes_verified=False,exec_code_verified=False)
        self.events.append(row)
        context=self.context('get_data')
        if context is None:self.fail(row,'cache_without_exact_source_loader',path)
        execution,loader,get_code=context
        source=loader.path
        if (type(source) is not str or not Path(source).is_absolute() or
            str(Path(source).resolve())!=source or Path(source).suffix!='.py' or
            source not in router.config['runtime_files'] or source in router.config['oracle_files']):
            self.fail(row,'cache_source_not_pinned',source)
        row.update(source=source,module=loader.name,source_pin=dict(router.config['runtime_files'][source]))
        expected=importlib.util.cache_from_source(source)
        if (raw!=expected or str(path)!=expected or get_code.f_locals.get('source_path')!=source or
            get_code.f_locals.get('bytecode_path')!=expected):
            self.fail(row,'cache_source_path_mismatch',path)
        key=id(execution)
        if key in self.pending:self.fail(row,'duplicate_cache_in_loader_invocation',path)
        self.pending[key]=dict(row=row,execution=execution,loader=loader,get_code=get_code,expected_code=None)
        if router.phase=='NORMAL':
            count=len(router.cold.blocked)
            try:router.cold.audit('open',args)
            except PermissionError:
                new=router.cold.blocked[count:]
                if len(new)!=1 or new[0].get('kind')!='bytecode_cache_not_admitted':
                    self.fail(row,'unexpected_normal_cache_denial',path)
                self.normal_denials[count]=row
                raise
        # SourceLoader.get_code catches OSError and reads source. This denial is
        # never suppressed by us; the raw cache event remains in the report.
        raise PermissionError('bytecode_cache_not_admitted: '+str(path))

    def source_open(self,name):
        context=self.context('get_data')
        if context is None:return
        execution,loader,get_code=context;pending=self.pending.get(id(execution))
        if pending is None:return
        row=pending['row']
        if name!=row['source'] or get_code is not pending['get_code']:
            self.fail(row,'cache_fallback_wrong_source',name)
        row['source_open_observed']=True

    def observe(self,event,args):
        if event=='compile' and not self.compiling:
            context=self.context('source_to_code')
            if context is None:return
            execution,loader,get_code=context;pending=self.pending.get(id(execution))
            if pending is None:return
            row=pending['row'];data,path=args
            if (get_code is not pending['get_code'] or path!=row['source'] or
                type(data) is not bytes or not row['source_open_observed']):
                self.fail(row,'cache_fallback_compile_context_mismatch',path)
            pin=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            if pin!=row['source_pin']:self.fail(row,'cache_fallback_source_bytes_drift',path)
            # Hash the actual bytes presented by the loader, never reopen source
            # from this audit callback. Private comparison compile is not exec.
            self.compiling=True
            try:code=_COMPILE(data,path,'exec',dont_inherit=True,optimize=sys.flags.optimize)
            finally:self.compiling=False
            pending['expected_code']=marshal.dumps(code)
            row.update(source_bytes_verified=True,compiled_code_sha256=hashlib.sha256(pending['expected_code']).hexdigest())
        elif event=='exec':
            context=self.context('exec_module')
            if context is None:return
            execution,loader,_=context;pending=self.pending.get(id(execution))
            if pending is None:return
            row=pending['row'];code=args[0]
            actual=marshal.dumps(code)
            if (pending['expected_code'] is None or actual!=pending['expected_code'] or
                code.co_filename!=row['source'] or execution.f_locals.get('code') is not code):
                self.fail(row,'cache_fallback_exec_code_mismatch',row['source'])
            row.update(status='EXPECTED_PINNED_SOURCE_FALLBACK',exec_code_verified=True,
                       exec_code_sha256=hashlib.sha256(actual).hexdigest(),module_body_completed_not_claimed=True)
            del self.pending[id(execution)]

    def finalize(self):
        for pending in self.pending.values():
            row=pending['row']
            if row['status']=='PENDING_SOURCE_FALLBACK':
                row.update(status='REJECTED_UNRESOLVED',failure='cache_source_fallback_unresolved')
                self.router.denied.append(dict(phase=row['phase'],kind='cache_source_fallback_unresolved',value=row['cache']))
        self.pending.clear()


class PhaseAudit:
    def __init__(self,config,cold_guard,oracle,out):
        self.config=config;self.cold=cold_guard;self.oracle=oracle;self.out=Path(out)
        self.phase='NORMAL';self.denied=[];self.native_loads=[];self.checking=set();self.verified=set()
        self.cache_fallback=PinnedCacheFallback(self)
    def reject(self,kind,value):
        self.denied.append(dict(phase=self.phase,kind=kind,value=str(value)))
        raise PermissionError(kind+': '+str(value))
    def audit(self,event,args):
        path=None;name=None;writing=False
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            raw=os.fsdecode(args[0]);path=Path(raw).resolve();name=str(path)
            flags=args[2] if len(args)>2 and type(args[2]) is int else 0
            mode=args[1] if len(args)>1 else ''
            writing=bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)) or (type(mode) is str and any(c in mode for c in 'wax+'))
            if not writing and (path.suffix=='.pyc' or Path(raw).suffix=='.pyc'):self.cache_fallback.cache_open(path,raw,args)
        if self.phase=='NORMAL':
            nested=name in getattr(self.cold,'checking',set())
            self.cold.audit(event,args)
            if path is not None and not writing and not nested:self.cache_fallback.source_open(name)
            self.cache_fallback.observe(event,args)
            return
        if event.startswith('socket.') or event in ('subprocess.Popen','os.fork','os.forkpty','os.posix_spawn','os.exec','os.system') or event.startswith(('os.exec','os.spawn')):
            self.reject('network_or_child_process_forbidden',event)
        if event=='ctypes.dlopen':
            if args[0] not in (None,self.config['elf']):self.reject('unapproved_native_load',args[0])
            self.native_loads.append(args[0])
        if event=='import' and args:
            if str(args[0]).split('.')[0] in ('torch','transformers'):
                self.reject('oracle_implementation_import_forbidden',args[0])
            if len(args)>1 and args[1]:
                imported=Path(args[1]).resolve();origin=str(imported)
                if origin not in self.config['runtime_files']:self.reject('unapproved_import_origin',origin)
                if file_id(imported)!=self.config['runtime_files'][origin]:self.reject('import_origin_drift',origin)
        if path is not None:
            if writing:
                if not path.is_relative_to(self.out):self.reject('write_outside_run',name)
                return
            if name in self.checking:return
            if path.is_relative_to(self.out) or name.startswith('/proc/'):return
            if name in self.config['oracle_files']:
                if self.oracle.state!='COMPARING':self.reject('oracle_outside_terminal_window',name)
                return
            allowed={**self.config['runtime_files'],**self.config['provider_files']}
            if name not in allowed:self.reject('unapproved_read',name)
            if name not in self.verified:
                self.checking.add(name)
                try:
                    if file_id(path)!=allowed[name]:self.reject('read_source_provider_drift',name)
                finally:self.checking.remove(name)
                self.verified.add(name)
            self.cache_fallback.source_open(name)
        self.cache_fallback.observe(event,args)
    def report(self):
        return dict(phase=self.phase,denied=[dict(row) for row in self.denied],native_loads=list(self.native_loads),
                    bytecode_cache_events=[dict(row) for row in self.cache_fallback.events],
                    oracle_denied=[dict(row) for row in self.oracle.denied],
                    cache_evidence_scope='Denied cache; pinned source bytes and exact source-derived code submitted to exec. Not proof module body completed; not native/numerical permission.')
    def require_clean(self):
        self.cache_fallback.finalize()
        need(not self.denied,'sticky runtime policy violation')
        need(not self.oracle.denied,'sticky oracle isolation violation')
    def leave_normal(self):
        need(self.phase=='NORMAL','single normal transition')
        self.require_clean()
        for index,row in enumerate(self.cold.blocked):
            qualified=self.cache_fallback.normal_denials.get(index)
            need(row['kind']=='bytecode_cache_not_admitted' and qualified is not None and
                 qualified['status']=='EXPECTED_PINNED_SOURCE_FALLBACK' and row.get('detail')==qualified['cache'],
                 'normal guard recorded an unqualified denial')
        self.phase='NATIVE'

def imports(config):
    sys.path[:0]=[config['cold_helper_root'],str(Path(config['candidate_root']).parent),
                  str(Path(config['normal_adapter_root']).parent),config['numpy_root'],config['yaml_root']]
    cold=importlib.import_module('cold_import');inventory=importlib.import_module('module_inventory')
    binding=importlib.import_module('qwen2_ordered_fullgraph_entry.runtime_binding')
    policy=importlib.import_module('qwen2_ordered_fullgraph_entry.cold_policy')
    initialization=importlib.import_module('qwen2_fullgraph_normal_binding.initialization')
    safe=importlib.import_module('qwen2_fullgraph_normal_binding.safe_metadata')
    return cold,inventory,binding,policy,initialization,safe


def snapshot(config,out,stage,components,native_before,native_events,*,native=False):
    cold,inventory,binding,policy,initialization,safe=components
    folder=Path(out)/stage;folder.mkdir();modules=dict(sys.modules)
    cold.write_json(folder/'MODULES_RAW.json',cold.raw_modules(modules))
    maps=Path('/proc/self/maps').read_text();cold.write_text(folder/'MAPS_RAW.txt',maps)
    namespaces,repetitions=policy.namespace_registration(modules,config['namespaces'])
    synthetic={}
    if '_qualified_runtime_observer' in modules:
        # Registration is tied to the actual source-bound factory. The normal
        # initializer creates it via cold helper; task runtime recreates it via
        # the reviewed runtime_observer.load_observer factory.
        if modules['_qualified_runtime_observer'] is _normal_observer_object:
            synthetic=cold.observer_registration(modules['_qualified_runtime_observer'],config['observer_root'])
        else:
            observer=modules['runtime_observer']
            synthetic={'_qualified_runtime_observer':dict(kind='namespace_package',module=modules['_qualified_runtime_observer'],
                paths=[config['observer_root']],allowed_children=['monitor','capture'],creator_source=str(Path(observer.__file__).resolve()),creator_function=observer.load_observer)}
    audit=inventory.collect_modules(modules,config['runtime_files'],namespaces=namespaces,synthetic=synthetic,registered_objects=config['registered_module_objects'])
    cold.write_json(folder/'MODULE_AUDIT.json',audit)
    qualification=policy.qualify_namespace_repetitions(audit,repetitions,modules)
    cold.write_json(folder/'NAMESPACE_QUALIFICATION.json',qualification)
    # Same exact mapping collector, with no forbidden Matrix path ONLY after
    # the authorized native phase. Every mapping must still be in exact pins.
    mapped=cold.collect_maps(maps,config['runtime_files'],None if native else config['elf'],config['mapping_allowlist'])
    cold.write_json(folder/'MAP_AUDIT.json',mapped)
    raw=safe.snapshot(modules,(*initialization.NAMES,'yaml','yaml.cyaml','yaml._yaml'))
    cold.write_json(folder/'DEPENDENCY_OBJECTS_RAW.json',raw)
    need(not mapped['failures'],'runtime mapping qualification failed')
    need(all(not row['errors'] for row in raw),'dependency raw object errors')
    dep=initialization.qualify(modules,native_before,native_events,config['yaml_root'],config['yaml_extension_sha256'],mapped,audit)
    remaining=qualification['remaining_failures']
    need({x['name'] for x in remaining}==set(initialization.NAMES) and all(x['code']=='unregistered_no_file_module' for x in remaining),'unknown module identity failure')
    if native:
        need(any(r['path']==config['elf'] and r['match'] for r in mapped['mappings']),'actual Matrix mapping absent')
    result=dict(status='PASS_CURRENT_NATIVE_RUNTIME_IDENTITIES' if native else 'PASS_NORMAL_RUNTIME_IDENTITIES_ONLY',
        stage=stage,dependency=dep,modules=len(modules),matrix_mapping_qualified=native)
    cold.write_json(folder/'RESULT.json',result)
    return result


def normal_initialize(config,out,oracle):
    global _normal_observer_object
    c=imports(config);cold,inventory,binding,policy,initialization,safe=c
    runtime_files=config['runtime_files'];sites=policy.metadata_sites(config['source_root'],runtime_files)
    Guard=policy.guard_class(cold.ColdGuard,sites,runtime_files)
    cold_guard=Guard(config,runtime_files,out);router=PhaseAudit(config,cold_guard,oracle,out)
    sys.addaudithook(router.audit)
    before=None;events=[]
    def watch(event,args):
        nonlocal before
        if event=='import' and args and args[0]=='yaml._yaml':
            if before is None:before={name:name in sys.modules for name in initialization.NAMES}
            events.append(dict(module=args[0],origin=args[1] if len(args)>1 else None))
    sys.addaudithook(watch)
    callback=cold_guard.profile;need(sys.getprofile() is None,'preexisting normal profiler')
    error=None;profile_errors=[];runtime=None;receipt=None;service={}
    sys.setprofile(callback)
    try:
        runtime,receipt=binding.load_runtime(config['source_root'],config['source_manifest'],config['source_manifest_sha256'])
        _normal_observer_object=cold.create_observer_namespace(config['observer_root'])
        obs_files={str(Path(p).relative_to(config['observer_root'])):v for p,v in runtime_files.items() if Path(p).is_relative_to(config['observer_root'])}
        with binding.ProjectCodeGate(Path(config['observer_root']),obs_files):
            monitor=importlib.import_module('_qualified_runtime_observer.monitor')
        trace=importlib.import_module('qwen2_ordered_fullgraph_entry.service_trace')
        for name,(fn,path,pin,cls,method) in trace.service_specs(runtime.binding.ProfiledMatrixService,config).items():
            code=monitor.bind(fn,path,pin,cls,method,False)
            service[name]=dict(source=str(path),sha256=pin,qualname=code.co_qualname,filename=code.co_filename)
        root=Path(config['candidate_root']);candidate_files={str(Path(p).relative_to(root)):v for p,v in runtime_files.items() if Path(p).is_relative_to(root)}
        with binding.ProjectCodeGate(root,candidate_files):
            for name in config['normal_candidate_imports']:
                importlib.import_module('qwen2_ordered_fullgraph_entry.'+name)
        # All task-time helper imports are loaded as definitions in this phase.
        with binding.ProjectCodeGate(Path(config['source_root']),json.loads(Path(config['source_manifest']).read_text())['source_files']):
            for name in config['normal_project_imports']:importlib.import_module(name)
        for name in ('runtime_observer','reference_capture','harness'):importlib.import_module(name)
        path=Path(config['buffer_source']);spec=importlib.util.spec_from_file_location('_qualified_runtime_fields',path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        with binding.ProjectCodeGate(path.parent,{path.name:runtime_files[str(path)]}):spec.loader.exec_module(module)
    except BaseException as exc:error=dict(type=type(exc).__name__,detail=str(exc))
    finally:profile_errors=cold.stop_task_profile(cold_guard,callback)
    if error is not None or profile_errors:router.cache_fallback.finalize()
    write_new(Path(out)/'NORMAL_LOAD_STATUS.json',dict(error=error,profile_errors=profile_errors,blocked=cold_guard.blocked,
        binding=receipt,services=service,native_before=before,native_events=events,runtime_policy=router.report()))
    try:
        snapshot(config,out,'NORMAL_FINAL',c,before,events,native=False)
        need(error is None and not profile_errors and len(service)==9,'normal initialization failed')
        router.leave_normal()
        return runtime,router,c,before,events
    finally:
        # A failed initializer never returns its router to the worker. Persist
        # all late snapshot events here without replacing its original error.
        router.cache_fallback.finalize()
        write_new(Path(out)/'NORMAL_POLICY_FINAL.json',router.report())
