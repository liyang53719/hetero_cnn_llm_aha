"""One finite local backend/tiny/Host/single-RAM N0 continuation. No default action."""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import json,math,os,resource,signal,time
from pathlib import Path
MIB=1024**2
GIB=1024**3
CI='candidates/host93_ci_recovery/'
FIRST='candidates/host93_first_n0_sources/'
PHASES=('local_flex_header_cached','flex_header_compile','fresh_autoconf','fresh_configure','fresh_make','derived_tiny_version','derived_tiny_generate','derived_tiny_compile','derived_tiny_run','idma319_extract','retained13_assemble','host93_configuration','host93_cpp_generate','host93_cpp_compile','host93_first_n0','host93_n0_compare')
FIFO_PINS={'summary.json':{'bytes':4655,'sha256':'e6c674054b935d798b6c7401cd16569d2602272c3a8a99cb62153f7f1b2140c9'},'source_hashes.json':{'bytes':5939,'sha256':'acf9114348882cc60ec5cfef3b24a1a94be741e4e495baab745864faa507bb4f'},'stage_exits.json':{'bytes':28538,'sha256':'e3b113e0ff4bbb2e6e2f853cdfa4f5b4a59c019c0060f8cc7a294b2799d9b4b6'}}
FIFO_REVIEW={'bytes':11813,'sha256':'120ffd07a662deb267be143b1c890c87d787637e2ac8d50da91c79a8963edbb3'}
FIFO_SOURCE_NAMES=(CI+'fifo_preflight/fifo_preflight.py',CI+'fifo_preflight/fifo_ready_split_miter.sv',CI+'idma319/extract_idma.py','candidates/host93_micro_diagnostics/fixtures/fifo_valid_split_cases.sv','candidates/host93_micro_diagnostics/icarus_stage.py')
ASSETS={'fir':{'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'},'sv':{'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'},'idma_zip':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}}
def need(ok,message):
    if not ok:raise ValueError(message)
def budget(started,stop):
    need(all(type(x) in (int,float) and math.isfinite(x) for x in (started,stop)) and abs(stop-started-6600)<0.000001,'single exact 6600-second outer budget')
    return {'total_stop':stop,'work_stop':stop-120,'pre_stop':stop-3720,'numeric_seconds':3600,'tail_seconds':120}
def admit_phase(name,bound,records,started,stop,now):
    times=budget(started,stop)
    need([r['name'] for r in records]==list(PHASES[:len(records)]) and len(records)<len(PHASES) and name==PHASES[len(records)],'finite exact continuation phase order')
    need(all(r['status']=='EXIT0_CLEANED' for r in records),'first failure stops all successor phases')
    deadline=times['work_stop'] if name in PHASES[-2:] else times['pre_stop']
    need(type(now) in (float,int) and math.isfinite(now) and now>=started and now<deadline-15,'INCOMPLETE phase reserve exhausted')
    if name=='host93_first_n0':need(now<=times['pre_stop'],'INCOMPLETE full N0 window unavailable')
    need(type(bound) is dict and type(bound.get('total_seconds')) is int and type(bound.get('work_seconds')) is int and 0<bound['work_seconds']<bound['total_seconds'],'finite phase bounds')
    return deadline

def inherited_fifo(g,repo,root,review_path,pins):
    documents={n:g.decode(g.checked(root/n,p,65536)) for n,p in FIFO_PINS.items()}
    review=g.decode(g.checked(review_path,FIFO_REVIEW,65536))
    need(review['run_id']==39232100796 and review['verdict']=='PASS_ACTUAL_CLUSTER_HOST_COMPILE_AND_BOUNDED_RESET_LAUNCH_ONLY','exact reviewed historical FIFO source job')
    observed=documents['summary.json']['fifo_observation']
    need(observed['state']=='AVAILABLE' and observed['cases']==4 and observed['comparisons']==5180,'inherited finite FIFO observation')
    source={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in documents['source_hashes.json']['project_sources']}
    for name in FIFO_SOURCE_NAMES:
        need(source[name]==pins[name],'same historical dual-split/miter/cases source')
        g.checked(repo/name,source[name],65536)
    rows=[r for r in documents['stage_exits.json']['stages'] if r['name'] in ('icarus_acquire','fifo_compile','fifo_run')]
    need([r['name'] for r in rows]==['icarus_acquire','fifo_compile','fifo_run'],'three exact historical FIFO phases')
    for r in rows:
        need(r['status']=='EXIT0_CLEANED' and type(r['exit_code']) is int and r['exit_code']==r['waitid_status']==0 and r['waitid_code']==1 and r['cleanup_confirmed'] is True and r['receipt_timed_out'] is False and r['final_reap_signal'] is None,'historical FIFO natural exit cleanup')
    return {'scope':'EXACT_SAME_SOURCE_HISTORICAL_FIFO_PRECONDITION','run_id':39232100796,'cases':4,'comparisons':5180,'local_fifo_execution':'NOT_RUN','actual_evidence':FIFO_PINS,'review':FIFO_REVIEW,'source_pins':{n:source[n] for n in FIFO_SOURCE_NAMES}}

def stage_inputs(P,repo,pins,providers,metadata,destination):
    """One bounded parent data stage; no provider conversion, links or native run."""
    spec=P.decode(P.read(repo/(FIRST+'inputs/CONVERSION_SPEC.json'),pins[FIRST+'inputs/CONVERSION_SPEC.json']['bytes'],pins[FIRST+'inputs/CONVERSION_SPEC.json']))
    rows=[(providers/(r['name']+'.bin'),'providers/'+r['name']+'.bin',{'bytes':r['output_bytes'],'sha256':r['expected_output_sha256']}) for r in spec['providers']]
    rows += [(metadata/'host_commands.bin','metadata/host_commands.bin',{'bytes':384,'sha256':'618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'}),(metadata/'host_descriptors.bin','metadata/host_descriptors.bin',{'bytes':3456,'sha256':'1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'})]
    need(len(rows)==16 and sum(r[2]['bytes'] for r in rows)==94920448 and not os.path.lexists(destination),'exact fresh canonical16 data stage')
    destination.mkdir(mode=0o700)
    for name in ('providers','metadata'):(destination/name).mkdir(mode=0o700)
    for source,name,pin in rows:
        raw=P.read(source,pin['bytes'],pin)
        fd=os.open(destination/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:need(os.write(fd,raw)==len(raw),'complete unchanged canonical bytes copy')
        finally:os.close(fd)
        need(P.read(source,pin['bytes'],pin)==raw,'source unchanged during canonical copy')
        P.verify_file(destination/name,pin)
    P.canonical_inputs(repo,pins,destination)
    return {'stage':'local_canonical16_copy','kind':'PARENT_DATA_ONLY','files':16,'bytes':94920448,'numeric_conversion':False,'native_started':False,'frontdoor_claim':False}

def run(cfg,started,stop,mods,source_check):
    """Called only by pinned source_entry with explicit actual flag and deadline."""
    times=budget(started,stop);need(time.monotonic()>=started and time.monotonic()<times['pre_stop'],'outer start before all source/asset preflight')
    g,o,l,adapter,accepted,header,consumer=(mods[n] for n in ('bootstrap','observer','profile','adapter','accepted','header','consumer'))
    need(type(cfg) is dict and set(cfg)=={'schema','repo','work','tool_binding','local_profile','qualification_result','qualification_review','fifo_evidence_root','fifo_review','fir','sv','idma_zip','provider_root','metadata_root','source_cache','runtime_root','reference_file','reference_receipt'} and cfg['schema']=='LOCAL_BACKEND_HOST_N0_BINDING_V1' and type(cfg['source_cache']) is str,'finite current binding; explicit fixed473 source cache')
    pathnames=('repo','work','qualification_result','qualification_review','fifo_evidence_root','fifo_review','fir','sv','idma_zip','provider_root','metadata_root','runtime_root','reference_file','reference_receipt','source_cache')
    p={k:g.clean(cfg[k]) for k in pathnames};repo,work=p['repo'],p['work']
    for key in ('tool_binding','local_profile'):
        need(type(cfg[key]) is dict and set(cfg[key])=={'path','bytes','sha256'},'exact existing binding pin')
    bpin={k:cfg['tool_binding'][k] for k in ('bytes','sha256')};ppin={k:cfg['local_profile'][k] for k in ('bytes','sha256')}
    braw=g.checked(g.clean(cfg['tool_binding']['path']),bpin,256*1024);praw=g.checked(g.clean(cfg['local_profile']['path']),ppin,256*1024)
    binding=g.binding(braw,bpin,repo);dep=g.paths(binding)['work']
    for root in (repo,dep,*p.values()):
        if root!=work:need(not work.is_relative_to(root) and not root.is_relative_to(work),'disjoint existing inputs and fresh output')
    need(work.parent.is_dir() and not os.path.lexists(work),'fresh on-disk workroot')
    C=mods['coordinator'];supervisor=mods['supervisor'];C.memory_disk_gate(work.parent,8*GIB,3*GIB)
    pins,buffers=C.project_pin_map(repo)
    for name,pin in consumer.SOURCE_PINS.items():
        need(name not in pins or pins[name]==pin,'same original source pin collision');pins[name]=pin
    P=C.module_from(repo,pins,CI+'first_n0/pipeline.py','local_original_n0_observer')
    for key,pin in ASSETS.items():P.verify_file(p[key],pin)
    fifo=inherited_fifo(g,repo,p['fifo_evidence_root'],p['fifo_review'],pins)
    component,tool_proof=accepted.bind(g,o,l,adapter,header,repo,braw,bpin,praw,ppin,p['qualification_result'],p['qualification_review'],mods['header_raw'])
    resume=mods['resume']
    cache_proof=resume.bind(g,adapter,component,repo,work/'cached-official473')
    fs,base,support_pins=supervisor.fixed_support(repo)
    need(len(os.sched_getaffinity(0))==1,'single inherited CPU')
    stages=[];completed=[];parent_stages=[];observation=P.empty_observation();generation=None;failure=None;matched=None;preflight=None;tools=None;execution=None
    def expired(*args):raise TimeoutError('bounded local continuation deadline exhausted')
    old_alarm=signal.signal(signal.SIGALRM,expired);old_term=signal.signal(signal.SIGTERM,expired);old_mask=os.umask(0o077)
    signal.setitimer(signal.ITIMER_REAL,max(0.001,times['pre_stop']-time.monotonic()))
    def check_sources():
        source_check()
        for name,pin in pins.items():C.exact(repo/name,pin['bytes'],pin['sha256'])
        component.host_identities(fs)
    def callback(name,argv,cwd,env,bound):
        deadline=admit_phase(name,bound,stages,started,stop,time.monotonic())
        C.phase_limits('flex_header_acquire' if name=='local_flex_header_cached' else name,bound)
        if name=='local_flex_header_cached':need(bound['total_seconds']<=60 and bound['work_seconds']<=40 and bound['cpu_seconds']<=40,'tight cached header limits')
        if name in ('host93_cpp_generate','host93_cpp_compile','host93_first_n0'):C.memory_disk_gate(work,8*GIB,3*GIB)
        check_sources();need(time.monotonic()<deadline-15,'source recheck within phase reserve')
        signal.setitimer(signal.ITIMER_REAL,max(0.001,deadline-time.monotonic()))
        owner={'handler':expired,'deadline':deadline};diagnostics={};began=time.monotonic()
        row={'name':name,'status':'FAILED','seconds':0.0,**supervisor.diagnostic_defaults()};stages.append(row)
        print(json.dumps({'phase':name,'status':'START'},sort_keys=True),flush=True)
        try:
            record,raw,usage=supervisor.run_phase(fs,base,name,argv,cwd,work/'phases'/name,env,bound,deadline,owner,diagnostics=diagnostics)
            need(type(record['exit_code']) is int and record['exit_code']==0 and record['cleanup_confirmed'] is True,'natural exit0 cleanup required')
            check_sources();row.update(status='EXIT0_CLEANED',exit_code=0,cleanup_confirmed=True,usage=usage)
            return {'record':record,'raw_log':raw,'usage':usage,'evidence_root':str(work/'phases'/name)}
        finally:
            row.update(diagnostics);row['seconds']=time.monotonic()-began
            print(json.dumps({'phase':name,'status':row['status'],'seconds':row['seconds']},sort_keys=True),flush=True)
    try:
        fs.fresh_directory(work)
        for name in ('home','tmp','phases','private'):fs.fresh_directory(work/name)
        data_stop=min(times['pre_stop'],time.monotonic()+60)
        signal.setitimer(signal.ITIMER_REAL,max(0.001,data_stop-time.monotonic()))
        parent_stages.append(stage_inputs(P,repo,pins,p['provider_root'],p['metadata_root'],work/'canonical16'))
        need(time.monotonic()<data_stop,'canonical16 data stage sixty-second bound')
        signal.setitimer(signal.ITIMER_REAL,max(0.001,times['pre_stop']-time.monotonic()))
        run_numeric,front,preflight=consumer.prepare(repo,work/'canonical16',pins,stop,runtime_root=p['runtime_root'],reference_file=p['reference_file'],reference_receipt=p['reference_receipt'])
        cache_stop=min(times['pre_stop'],time.monotonic()+60)
        signal.setitimer(signal.ITIMER_REAL,max(0.001,cache_stop-time.monotonic()))
        parent_stages.append(resume.stage_cache(g,component,repo,p['source_cache'],work/'cached-official473'))
        need(time.monotonic()<cache_stop,'cached473 data stage sixty-second bound')
        signal.setitimer(signal.ITIMER_REAL,max(0.001,times['pre_stop']-time.monotonic()))
        tools=component.run(repo,work/'toolchain',callback)
        completed.append('fresh_backend_and_tiny')
        host={key:{'path':str(p[key]),**ASSETS[key]} for key in ('fir','sv')}
        host['origin']='EXISTING_PINNED_ARTIFACTS_REVALIDATED_NOT_NEW_EMISSION'
        env=P.native_environment(work)
        idma=work/'idma319';entry=C.decode(buffers[CI+'idma319/ENTRY.json'])
        command=[sys.executable,'-I','-S','-B','-c',entry['bootstrap'],str(repo/(CI+'idma319/extract_idma.py')),'--archive',str(p['idma_zip']),'--out',str(idma),'--fifo-valid-split']
        callback('idma319_extract',command,work,env,C.limits(60,45,40,512*MIB,4*MIB))
        retained=work/'retained13'
        # The original retained runner is itself a fixed same-buffer loader.
        callback('retained13_assemble',[sys.executable,'-I','-S','-B',str(repo/(CI+'retained13/run_retained13.py')),'--repo',str(repo),'--out',str(retained)],work,env,C.limits(60,45,40,512*MIB,4*MIB))
        config=work/'configuration';entry=C.decode(buffers[CI+'configuration/ENTRY.json'])
        command=[sys.executable,'-I','-S','-B','-c',entry['argv_prefix'][5],str(repo/(CI+'configuration/generate_4vlt.py')),'--repo',str(repo),'--sv',host['sv']['path'],'--idma-root',str(idma/'sources'),'--out',str(config),'--cluster-boundary']
        callback('host93_configuration',command,work,env,C.limits(60,45,45,768*MIB,4*MIB))
        executor=C.module_from(repo,pins,CI+'execution/host_execution.py','local_fixed_host_execution')
        census=C.module_from(repo,pins,CI+'execution/generation_diagnostics.py','local_fixed_host_census')
        sanitizer=C.module_from(repo,pins,CI+'safe_build_diagnostics.py','local_fixed_host_sanitizer')
        def diagnostics(folder,mapping):
            nonlocal generation
            generation=census.collect(work/'phases/host93_cpp_generate/native.log',folder,mapping,sanitizer);census.validate_report(generation);return generation
        execution=executor.run(repo,work/'host_execution',callback,tools,host,idma,retained,config,cluster_boundary=True,first_n0=True,diagnostic_callback=diagnostics)
        executor.validate_cluster_census(generation)
        need(execution['status']=='COMPILED_FIRST_N0_FIXTURE_ONLY','fixed real first N0 executable required')
        completed.append('host_compilation')
        # Recheck original reference/runtime and full-window gate immediately
        # before numeric work. Its child deadline stays below the one total stop.
        run_numeric,front,preflight=consumer.prepare(repo,work/'canonical16',pins,stop,runtime_root=p['runtime_root'],reference_file=p['reference_file'],reference_receipt=p['reference_receipt'])
        numeric_stop=consumer.require_numeric_window(stop)
        signal.setitimer(signal.ITIMER_REAL,max(0.001,times['work_stop']-time.monotonic()))
        matched=run_numeric(repo,work/'n0_numeric',pins,callback,numeric_stop,front,execution,observation,completed,stages)
        check_sources();need(time.monotonic()<times['work_stop'],'native and checks finish before tail')
        need(len(stages)==16,'all exact finite native stages')
    except BaseException as e:
        failure=e
    finally:
        try:
            report_stop=min(stop,time.monotonic()+120)
            signal.setitimer(signal.ITIMER_REAL,max(0.001,report_stop-time.monotonic()))
            if work.is_dir():
                result={'schema':'LOCAL_BACKEND_HOST_SINGLE_N0_RESULT_V1','status':'PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY' if failure is None and matched is True else 'N0_LIMITED_TOLERANCE_FAIL' if failure is None and matched is False else 'INCOMPLETE','failure_type':None if failure is None else type(failure).__name__,**resume.safe_contract(component,failure),'cache_continuation':cache_proof,'completed':completed,'stages':stages,'parent_data_stages':parent_stages,'n0_observation':observation,'generation_diagnostics':generation,'existing_reference_preflight':preflight,'inherited_fifo':fifo,'accepted_tools':tool_proof,'existing_sv_origin':'REVALIDATED_FIXED_BYTES_NOT_NEW_EMISSION','full_block_pass':False,'baseline_adopted':False,'clock':{'started':started,**times,'finished':time.monotonic(),'report_stop':report_stop},'seconds':time.monotonic()-started}
                component.save_private(work/'RESULT.json',result)
            need(time.monotonic()<report_stop,'120-second evidence tail exhausted')
        except BaseException as report_error:
            # Evidence failure never replaces the first native/contract error.
            if failure is None:failure=report_error
        finally:
            # Attempt every fixed restoration without masking an earlier error.
            for restore,args in ((signal.setitimer,(signal.ITIMER_REAL,0)),(signal.signal,(signal.SIGALRM,old_alarm)),(signal.signal,(signal.SIGTERM,old_term)),(os.umask,(old_mask,))):
                try:restore(*args)
                except BaseException as restore_error:
                    if failure is None:failure=restore_error
    if failure is not None:raise failure
    return result
