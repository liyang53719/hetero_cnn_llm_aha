"""Only synthetic mocked packages and small data files; no acquired package."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,builtins,copy,hashlib,itertools,json,os,struct,tempfile,types
from pathlib import Path
from unittest import mock
# TARGET, REPO, TEST_ROOT are supplied only by same-buffer run_cold.py.
g=TARGET
checks=[]
def check(name,fn):
    fn();checks.append(name)
def rejects(fn,text):
    try:fn()
    except (ValueError,OSError,SystemExit) as e:
        g.need(text in str(e),'wrong rejection '+str(e));return
    raise ValueError('missing rejection '+text)
s=g.load_sources(REPO)
raw=(Path(g.__file__)).read_bytes()
check('fixed_eight_source_pins_and_unbound_original',lambda:g.need(len(s['raw'])==8 and s['pins']['actual_identity_review'] is None,'fixed sources'))
check('fixed_five_original_debs',lambda:g.need(len(s['plan']['artifacts'])==5 and sum(x['known_size_bytes'] for x in s['plan']['artifacts'])==2466616,'fixed bytes'))
check('fixed_67_members_and_data_only_template',lambda:g.need(len(s['selected'])==67 and sum(x['bytes'] for x in s['selected'].values())==3598623,'67 data'))
check('source_only_entry_no_execution',lambda:g.need(g.source_check(REPO)['status']=='SOURCE_ONLY_UNBOUND_NO_ACQUISITION_OR_NATIVE','source status'))
check('no_native_process_or_network_API',lambda:g.need(not any(isinstance(n,(ast.Import,ast.ImportFrom)) and any(x.name in ('subprocess','socket','urllib','ctypes') for x in n.names) for n in ast.walk(ast.parse(raw))),'no process imports'))
check('no_assert_acceptance',lambda:g.need(not any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(raw))),'no assert acceptance'))
check('unchanged_8GiB_single_cpu_and_make',lambda:g.need(g.UNCHANGED_RESOURCES=={'shared_job_wall_seconds':6600,'cpu_affinity_count':1,'host_memory_floor_bytes':8*1024**3,'host_disk_floor_bytes':3*1024**3,'make_jobs':1,'make_as_bytes':4*1024**3,'host_as_bytes':6*1024**3},'resources'))
check('original_bootstrap_limits',lambda:g.need(g.ACQUIRE_LIMITS['total_seconds']==180 and g.ACQUIRE_LIMITS['work_seconds']==160 and g.STAGE_LIMITS['total_seconds']==60 and g.STAGE_LIMITS['cpu_seconds']==40,'limits'))

def flag_refusals():
    for values in itertools.product((False,True),repeat=3):
        if all(values):continue
        seen=[]
        def importer(name,*a,**k):
            seen.append(name)
            if name=='sys':return types.SimpleNamespace(flags=types.SimpleNamespace(isolated=values[0],no_site=values[1],dont_write_bytecode=values[2]))
            raise ValueError('late import')
        ns={'__name__':'cold','__file__':g.__file__,'__builtins__':dict(vars(builtins),__import__=importer)}
        rejects(lambda:exec(compile(raw,'bootstrap','exec'),ns),'require Python')
        g.need(seen==['sys'],'guard before project imports')
check('seven_flag_combinations_fail_before_project_load',flag_refusals)

def binding_cases():
    template={'schema':'LOCAL_FIXED_DEPENDENCY_BINDING_V1','work_root':None,'system_programs':None,'native_profile':None}
    data=json.dumps(template).encode();rejects(lambda:g.binding(data,g.pin(data),REPO),'UNBOUND')
    rejects(lambda:g.binding(data,{'bytes':len(data),'sha256':'0'*64},REPO),'same-buffer')
    bad=b'{"schema":1,"schema":2}';rejects(lambda:g.binding(bad,g.pin(bad),REPO),'duplicate JSON')
    template.update(work_root=str(REPO/'bad'),system_programs={x:{} for x in g.SYSTEM});data=json.dumps(template).encode()
    rejects(lambda:g.binding(data,g.pin(data),REPO),'outside repository')
    for path in ('relative','/tmp/a b','/tmp/a/../b','/tmp/x\nq','/tmp/private+root'):
        template['work_root']=path;data=json.dumps(template).encode();rejects(lambda:g.binding(data,g.pin(data),REPO),'absolute make-safe')
check('unbound_hash_duplicate_and_unsafe_binding_refusals',binding_cases)

def source_read_cases():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        p=Path(t)/'input';p.write_bytes(b'fixed');fixed=g.pin(b'fixed')
        g.need(g.checked(p,fixed)==b'fixed','fixed read')
        rejects(lambda:g.checked(p,{'bytes':5,'sha256':'0'*64}),'stable exact')
        rejects(lambda:g.checked(p,{'bytes':4,'sha256':fixed['sha256']}),'regular exact')
        link=Path(t)/'link';link.symlink_to(p);rejects(lambda:g.checked(link,fixed),'Too many levels')
        fifo=Path(t)/'fifo';os.mkfifo(fifo);rejects(lambda:g.checked(fifo,g.pin(b'')),'regular exact')
check('same_buffer_hash_size_symlink_fifo',source_read_cases)

def argv_cases():
    b={'work_root':'/synthetic/local_dependency_root'}
    argv=g.acquisition_argv(s,b,10.,170.)
    g.need(argv[:5]==['/usr/bin/python3','-I','-S','-B','-c'],'exact isolated argv')
    for name in (g.ACQUIRER,g.PUBLISHED,g.PLAN):g.need(repr(s['raw'][name]) in argv[-1],'embedded exact buffer')
    for node in ast.walk(ast.parse(argv[-1])):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):g.need(node.func.attr!='main','no legacy CLI main')
    rejects(lambda:g.acquisition_argv(s,b,10.,181.),'timestamps')
    rejects(lambda:g.acquisition_argv(s,b,10.,float('nan')),'timestamps')
check('same_buffer_acquisition_argv_and_original_deadline',argv_cases)

def env_cases():
    b={'work_root':'/synthetic/local_dependency_root'}
    with mock.patch.dict(os.environ,{'HTTPS_PROXY':'synthetic-only','SECRET':'no'},clear=True):
        acquire=g.child_environment(b,True);native=g.tool_environment(b)
        g.need(acquire.get('HTTPS_PROXY')=='synthetic-only' and 'SECRET' not in acquire and 'HTTPS_PROXY' not in native,'transport scope')
        g.need(native['M4']=='/synthetic/local_dependency_root/tools/usr/bin/m4' and native['AUTOM4TE_CFG']=='/synthetic/local_dependency_root/stage/relocation/autom4te.cfg','fixed private env')
        g.need(native['OBJCACHE']==native['ac_cv_prog_OBJCACHE']=='' and 'LD_LIBRARY_PATH' not in native,'no cache or library fallback')
check('finite_private_environment_and_acquisition_transport_only',env_cases)

def elf_fixture(needed=('libc.so.6',),rpath=False,duplicate=False):
    raw=bytearray(1024);ident=b'\x7fELF\x02\x01\x01'+b'\0'*9
    struct.pack_into('<16sHHIQQQIHHHHHH',raw,0,ident,3,62,1,0,64,0,0,64,56,3,0,0,0)
    interp=b'/lib64/ld-linux-x86-64.so.2\0';raw[256:256+len(interp)]=interp
    table=b'\0';offsets=[]
    for name in needed:offsets.append(len(table));table+=name.encode()+b'\0'
    raw[512:512+len(table)]=table
    tags=[(5,512),(10,len(table))]+[(1,x) for x in offsets]
    if rpath:tags.append((29,0))
    if duplicate:tags.append((1,offsets[0]))
    tags.append((0,0))
    for i,row in enumerate(tags):struct.pack_into('<qQ',raw,384+i*16,*row)
    struct.pack_into('<IIQQQQQQ',raw,64,1,4,0,0,0,len(raw),len(raw),1)
    struct.pack_into('<IIQQQQQQ',raw,120,2,4,384,384,0,len(tags)*16,len(tags)*16,8)
    struct.pack_into('<IIQQQQQQ',raw,176,3,4,256,256,0,len(interp),len(interp),1)
    return bytes(raw)

def elf_cases():
    reader,projection=g.elf_reader(s,('libc.so.6','ld-linux-x86-64.so.2'))
    g.need(reader(elf_fixture())=={'needed':['libc.so.6'],'interpreter':'/lib64/ld-linux-x86-64.so.2'},'original ELF projection')
    rejects(lambda:reader(elf_fixture(('unapproved.so',))),'fixed dependency soname')
    rejects(lambda:reader(elf_fixture(rpath=True)),'no RPATH')
    rejects(lambda:reader(elf_fixture(duplicate=True)),'unique needed')
    rejects(lambda:reader(b'not ELF'),'ELF64')
check('exact_existing_ELF_reader_and_negative_metadata',elf_cases)

class Fixture:
    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT);self.work=Path(self.temp.name);self.work.chmod(0o700)
        (self.work/'packages').mkdir(mode=0o700)
        self.s=g.load_sources(REPO)
        lines=[b'fixture\n']*171
        for n in (118,145,159,171):lines[n-1]=self.s['stager'].CFG_OLD
        cfg=b''.join(lines)
        self.s['stager'].CFG_BYTES=len(cfg);self.s['stager'].CFG_SHA=g.pin(cfg)['sha256']
        self.data={self.s['stager'].CFG_PATH:cfg}
        for tool in g.FIVE:self.data['usr/bin/'+tool]=('SYNTHETIC '+tool+' NEVER EXECUTED\n').encode()
        for n,name in enumerate(x for x in self.s['selected'] if '+' in x):self.data[name]=('SYNTHETIC_PLUS_'+str(n)).encode()
        for n in range(67-len(self.data)):self.data['fixture/data'+str(n)]=('SYNTHETIC'+str(n)).encode()
        self.s['selected']={n:g.pin(b) for n,b in self.data.items()}
        self.s['pins']=copy.deepcopy(self.s['pins']);self.s['pins']['packages']=[]
        artifacts=[];rows=[];total=0
        for n,item in enumerate(self.s['plan']['artifacts']):
            raw=('SYNTHETIC_PACKAGE_'+str(n)).encode();name=item['relative_destination'];f=self.work/'packages'/name;f.write_bytes(raw);f.chmod(0o600)
            self.s['pins']['packages'].append({'deb_filename':name,'deb_bytes':len(raw),'deb_sha256':g.pin(raw)['sha256'],'package':str(n)})
            url='https://synthetic.invalid/'+name;total+=len(raw)
            artifacts.append({'relative_destination':name,'url':url,'known_size_bytes':len(raw),'sha256':g.pin(raw)['sha256']})
            rows.append({'relative_destination':name,'origin_url':url,'transport':'https-no-redirect','size_bytes':len(raw),'sha256':g.pin(raw)['sha256']})
        self.s['plan']={'group':'synthetic-five','transport':'https-no-redirect','artifacts':artifacts}
        self.s['gate'].PINNED_TOTAL=total
        self.receipt={'status':'VERIFIED_OPAQUE_BYTES_ONLY','group':'synthetic-five','fixed_plan_sha256':g.SOURCE_FILES[g.PLAN]['sha256'],
                      'terminal_success':False,'extracted':False,'executed':False,'installed':False,'host_compilation_or_rtl_evidence':False,
                      'artifacts':rows,'received_bytes':total,'review_probe_marker':'a'}
        raw=json.dumps(self.receipt,sort_keys=True).encode();f=self.work/'packages/ACQUISITION.json';f.write_bytes(raw);f.chmod(0o600);self.receipt_pin=g.pin(raw)
        self.s['stager'].validate_package=lambda raw,p: (dict(self.data) if p['package']=='0' else {},{'ignored_links':[{}]*6 if p['package']=='0' else []})
        self.b={'schema':'LOCAL_FIXED_DEPENDENCY_BINDING_V1','work_root':str(self.work),'system_programs':{n:{} for n in g.SYSTEM},'native_profile':None}
        self.braw=json.dumps(self.b).encode();self.bpin=g.pin(self.braw);self.phase={'name':'local_dependencies_acquire','record':{'exit_code':0,'cleanup_confirmed':True}}
        self.patch1=mock.patch.object(g,'load_sources',return_value=self.s);self.patch1.start()
        self.patch2=mock.patch.object(g,'SELECTED_BYTES',sum(map(len,self.data.values())));self.patch2.start()
        return self
    def stage(self):return g.stage_data(REPO,self.braw,self.bpin,self.phase,self.receipt_pin)
    def __exit__(self,*a):self.patch2.stop();self.patch1.stop();self.temp.cleanup()

def stage_success():
    with Fixture() as f:
        result=f.stage();expected=g.verify_stage(f.s,f.b,result,f.bpin)
        g.need(result['files']==69 and len(expected)==68 and result['terminal_success'] is False,'data-only stage result')
        cfg=(f.work/'stage/relocation/autom4te.cfg').read_bytes()
        g.need(cfg.count(str(f.work/'stage/usr/share/autoconf').encode())==4,'exact four local path replacements')
        g.need(all((f.work/'stage'/n).stat().st_mode&0o777==0o600 for n in expected),'all data0600')
        g.need(not (f.work/'tools').exists(),'no native copy')
check('synthetic_five_packages_67_data_four_line_relocation',stage_success)

def original_phase_failures():
    for change in ({'exit_code':1,'cleanup_confirmed':True},{'exit_code':0,'cleanup_confirmed':False},{'exit_code':False,'cleanup_confirmed':True}):
        with Fixture() as f:
            f.phase['record']=change;rejects(f.stage,'exit0');g.need(not (f.work/'stage').exists(),'no stage on phase failure')
    with Fixture() as f:
        f.phase['name']='historical_success';rejects(f.stage,'exact dependency phase');g.need(not (f.work/'stage').exists(),'no stage')
check('fresh_exit0_cleanup_and_phase_name_required',original_phase_failures)

def package_failures():
    with Fixture() as f:
        (f.work/'packages'/f.s['pins']['packages'][0]['deb_filename']).write_bytes(b'bad');rejects(f.stage,'artifact exact size');g.need(not (f.work/'stage').exists(),'bad package before output')
    with Fixture() as f:
        f.s['stager'].validate_package=lambda *a: ({}, {'ignored_links':[]});rejects(f.stage,'fixed 67');g.need(not (f.work/'stage').exists(),'bad aggregate before output')
    with Fixture() as f:
        f.data[f.s['stager'].CFG_PATH]+=b'foreign';rejects(f.stage,'fixed 67');g.need(not (f.work/'stage').exists(),'cfg drift before output')
check('package_hash_aggregate_and_cfg_drift_fail_before_output',package_failures)

def stage_failures():
    with Fixture() as f:
        result=f.stage();rejects(f.stage,'fresh stage')
        rejects(lambda:g.verify_stage(f.s,f.b,result,{'bytes':1,'sha256':'0'*64}),'same local stage binding')
        (f.work/'stage/extra').write_bytes(b'x');rejects(lambda:g.verify_stage(f.s,f.b,result,f.bpin),'regular-file cap')
    with Fixture() as f:
        result=f.stage();(f.work/'stage/usr/bin/m4').write_bytes(b'drift');rejects(lambda:g.verify_stage(f.s,f.b,result,f.bpin),'regular exact')
check('existing_stage_wrong_binding_extra_file_and_byte_drift',stage_failures)

def unbound_native():
    with Fixture() as f:
        result=f.stage();rejects(lambda:g.prepare_tools(REPO,f.braw,f.bpin,result),'native profile UNBOUND')
        g.need(not (f.work/'tools').exists(),'native unbound rejects before executable output')
check('unbound_ELF_library_profile_blocks_executable_copy',unbound_native)

def copy_success():
    with Fixture() as f:
        result=f.stage();fake={'system_programs':{n:{'path':n,'synthetic':True} for n in g.SYSTEM},'status':'SYNTHETIC_STATIC_ONLY'}
        with mock.patch.object(g,'native_preflight',return_value=fake):
            output=g.prepare_tools(REPO,f.braw,f.bpin,result)
        private={str(f.work/'tools/usr/bin'/n) for n in g.FIVE}
        g.need(private<=set(output['host_programs']) and not {'/usr/bin/'+n for n in g.FIVE}&set(output['host_programs']),'truthful invocation keys')
        g.need(output['terminal_success'] is False and output['native_qualification']=='NOT_RUN','no native acceptance')
        for name in f.s['selected']:
            expected=0o700 if name in {'usr/bin/'+n for n in g.FIVE} else 0o600
            g.need((f.work/'tools'/name).stat().st_mode&0o777==expected,'only five executable copies')
check('synthetic_private_copy_real_invocation_keys_not_usr_bin_aliases',copy_success)


def fixed_leaf_cases():
    fixed=['g++','x86_64-linux-gnu-g++-14','libstdc++.so.6.0.33']
    fixed += [a['relative_destination'] for a in s['plan']['artifacts'] if '+' in a['relative_destination']]
    fixed += [Path(n).name for n in s['selected'] if '+' in n]
    g.need(len(fixed)==8,'all eight reviewer paths')
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        root=Path(t)
        for name in fixed:
            p=root/name;p.write_bytes(b'fixed');p.chmod(0o600)
            rejects(lambda:g.checked(p,g.pin(b'fixed')),'absolute make-safe')
            g.need(g.checked(p,g.pin(b'fixed'),fixed_leaf=name)==b'fixed','explicit catalog leaf accepted')
            rejects(lambda:g.checked(p,g.pin(b'fixed'),fixed_leaf='different'),'exact fixed file leaf')
        for name in ('bad name','bad\nname','bad;name'):
            rejects(lambda:g.checked(root/name,g.pin(b''),fixed_leaf=name),'exact fixed file leaf')
        rejects(lambda:g.checked(root/'private+root'/'g++',g.pin(b''),fixed_leaf='g++'),'absolute make-safe')
        rejects(lambda:g.clean(str(root/'private+root')),'absolute make-safe')
check('F01_eight_fixed_plus_leaves_and_private_root_refusals',fixed_leaf_cases)


def system_plus_cases():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        root=Path(t);rows={};resolutions={}
        for invoked in g.SYSTEM:
            leaf='x86_64-linux-gnu-g++-14' if invoked=='/usr/bin/g++' else Path(invoked).name
            p=root/leaf;p.write_bytes(b'SYNTHETIC_SYSTEM');p.chmod(0o700)
            rows[invoked]={'path':str(p),**g.pin(p.read_bytes()),'mode':'0o700'};resolutions[invoked]=str(p)
        with mock.patch.object(g.os.path,'realpath',side_effect=lambda p:resolutions[str(p)]):
            g.need(g.system_identities(s,{'system_programs':rows})==rows,'system g++ actual path leaf')
check('F01_bound_system_gxx_real_checked_buffer',system_plus_cases)


def receipt_cases():
    with Fixture() as f:
        result=g.verify_acquisition(f.s,f.b,f.phase,f.receipt_pin)
        g.need(result==f.receipt,'original postflight positive control')
        path=f.work/'packages/ACQUISITION.json';original=path.read_bytes()
        mutated=original.replace(b'"review_probe_marker": "a"',b'"review_probe_marker": "b"')
        g.need(len(mutated)==len(original) and original!=mutated,'same length mutation')
        real_checked=g.checked;real_postflight=g.receipt_postflight;consumed=[];reads=[]
        def mutate_after_check(p,*args,**kwargs):
            raw=real_checked(p,*args,**kwargs)
            if Path(p)==path:reads.append(raw);path.write_bytes(mutated)
            return raw
        def observe_consumption(*args):
            receipt,projection=real_postflight(*args);consumed.append(receipt['review_probe_marker']);return receipt,projection
        with mock.patch.object(g,'checked',side_effect=mutate_after_check),mock.patch.object(g,'receipt_postflight',side_effect=observe_consumption):
            rejects(lambda:g.verify_acquisition(f.s,f.b,f.phase,f.receipt_pin),'stable exact bytes')
        g.need(consumed==['a'] and reads==[original] and path.read_bytes()==mutated,'pinned A consumed; persistent B rejected')
        path.write_bytes(original);consumed.clear()
        def restore_after_consumption(*args):
            receipt,projection=observe_consumption(*args);path.write_bytes(original);return receipt,projection
        with mock.patch.object(g,'checked',side_effect=mutate_after_check),mock.patch.object(g,'receipt_postflight',side_effect=restore_after_consumption):
            result=g.verify_acquisition(f.s,f.b,f.phase,f.receipt_pin)
        g.need(result['review_probe_marker']=='a' and consumed==['a'],'ABA cannot substitute parsed receipt')
check('F02_original_postflight_positive_A_to_B_reject_and_ABA_same_buffer',receipt_cases)


def postflight_projection_cases():
    with Fixture() as f:
        raw=(f.work/'packages/ACQUISITION.json').read_bytes()
        receipt,projection=g.receipt_postflight(f.s,f.work/'packages',raw)
        gate=f.s['raw'][g.ACQUIRE_GATE];lines=gate.splitlines(keepends=True)
        node=[n for n in ast.parse(gate).body if isinstance(n,ast.FunctionDef) and n.name=='postflight'][0]
        original=b''.join(lines[node.lineno-1:node.end_lineno])+b'\n'
        old=b'receipt=json.loads(receipt_path.read_bytes())';new=b'receipt=json.loads(VERIFIED_RECEIPT_RAW)'
        g.need(original.count(old)==1 and projection=={'original':g.pin(original),'projected':g.pin(original.replace(old,new))},'single reversible anchor pins')
        g.need('VERIFIED_RECEIPT_RAW' not in f.s['gate'].__dict__,'no shared gate global mutation')
        for change,text in (({'executed':True},'unearned package execution'),({'received_bytes':1},'exact received total'),({'fixed_plan_sha256':'0'*64},'fixed plan/nonterminal')):
            bad=dict(f.receipt,**change);rejects(lambda:g.receipt_postflight(f.s,f.work/'packages',json.dumps(bad).encode()),text)
        f.s['raw'][g.ACQUIRE_GATE]=gate.replace(old,new)
        rejects(lambda:g.receipt_postflight(f.s,f.work/'packages',raw),'single receipt buffer anchor')
check('F02_original_predicates_one_anchor_inverse_and_private_namespace',postflight_projection_cases)


def library_plus_cases():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        work=Path(t);stage=work/'stage';(stage/'usr/bin').mkdir(parents=True)
        profile={'package_elf':{},'script_interpreters':{},'libraries':{}};expected={};local_files={};resolutions={}
        interp='/lib64/ld-linux-x86-64.so.2'
        for name in ('ld-linux-x86-64.so.2','libstdc++.so.6'):
            invoked=interp if name.startswith('ld-') else '/usr/lib/x86_64-linux-gnu/'+name
            path='/usr/lib/x86_64-linux-gnu/'+(name if name.startswith('ld-') else 'libstdc++.so.6.0.33')
            raw=elf_fixture(());local=work/Path(path).name;local.write_bytes(raw);local.chmod(0o600);local_files[path]=local;resolutions[invoked]=path
            profile['libraries'][name]={'invoked':invoked,'path':path,**g.pin(raw),'mode':'0o600','needed':[],'interpreter':interp}
        for tool in ('m4','flex','bison'):
            name='usr/bin/'+tool;raw=elf_fixture(('libstdc++.so.6',));(stage/name).write_bytes(raw);expected[name]=g.pin(raw)
            profile['package_elf'][tool]={'needed':['libstdc++.so.6'],'interpreter':interp}
        for tool,invoked in (('autoconf','/bin/sh'),('autom4te','/usr/bin/perl')):
            name='usr/bin/'+tool;first='#!'+invoked;raw=(first+'\nSYNTHETIC_NOT_EXECUTED\n').encode();(stage/name).write_bytes(raw);expected[name]=g.pin(raw)
            profile['script_interpreters'][tool]={'first_line':first,'invoked':invoked}
        real_checked=g.checked;real_stat=Path.stat;real_realpath=os.path.realpath;seen=[]
        def library_read(path,pin,*args,**kwargs):
            if str(path) in local_files:
                g.need(kwargs.get('fixed_leaf')==Path(path).name,'bound library fixed leaf forwarded');seen.append(Path(path).name)
                return real_checked(local_files[str(path)],pin,*args,**kwargs)
            return real_checked(path,pin,*args,**kwargs)
        def protected_stat(path,*args,**kwargs):
            if str(path) in local_files:return types.SimpleNamespace(st_uid=0,st_mode=0o100600)
            return real_stat(path,*args,**kwargs)
        b={'work_root':str(work),'native_profile':profile}
        with mock.patch.object(g,'system_identities',return_value={}),mock.patch.object(g,'checked',side_effect=library_read),mock.patch.object(Path,'stat',protected_stat),mock.patch.object(os.path,'realpath',side_effect=lambda path,*a,**k:resolutions[str(path)] if str(path) in resolutions else real_realpath(path,*a,**k)):
            result=g.native_preflight(s,b,expected)
        g.need('libstdc++.so.6.0.33' in seen and result['libraries']==profile['libraries'] and result['symbol_version_compatibility_proved'] is False,'bound plus library accepted without native qualification')
check('F01_supported_library_plus_path_same_buffer_static_mock',library_plus_cases)

print(json.dumps({'status':'PASS_LOCAL_BOOTSTRAP_SOURCE_AND_SYNTHETIC_ONLY','checks':checks,'tests':len(checks),'optimized':sys.flags.optimize,
 'network_started':False,'native_child_started':False,'real_package_acquired_or_read':False,'installed':False,'real_tools_copied_or_executed':False,'host_executed':False,'binding':'UNBOUND'},sort_keys=True))
