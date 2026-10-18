"""Fixed 67-member data staging, in one bounded Python process; no native child."""
import argparse,hashlib,json,os,resource,signal,stat,sys,time,types
from pathlib import Path
WORKER={'bytes': 20634, 'sha256': '3f56c0b6ce0f41f245abf8d37ff55fa5257d71ead395f49410a2746924682a79'}
PINS={'bytes': 205675, 'sha256': 'abc9e5f55b045b6402cc5c13e4d4c4263eb6a7403e84b01a165a12b5d5d20cd0'}
SOURCE_NAMES={'stage_dependencies.py':WORKER,'PINS.json':PINS}


def require(ok,why):
    if not ok:raise ValueError(why)


def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def clean(path):
    p=Path(path).absolute();require('..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'safe normalized nonsymlink path');return p


def checked(path,expected):
    path=clean(path);require(path.is_file() and path.stat().st_size==expected['bytes']<=4*1024*1024,'fixed source/data size')
    with path.open('rb') as f:raw=f.read(expected['bytes']+1)
    require(pin(raw)==expected,'fixed source/data SHA');return raw


def load(raw,path):
    require(pin(raw)==WORKER,'worker same-buffer pin')
    m=types.ModuleType('fixed_dependency_staging');m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m


def preflight(directory):
    directory=clean(directory);raw={n:checked(directory/n,p) for n,p in SOURCE_NAMES.items()}
    m=load(raw['stage_dependencies.py'],directory/'stage_dependencies.py');p=m.load_pins();m.require_actual_review(p)
    require(p['selected_count']==67 and p['selected_bytes']==3598623,'fixed selected source contract')
    return raw,m,p


def save(path,raw):
    require(len(raw)<=512*1024,'bounded evidence/source write')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:require(f.write(raw)==len(raw),'complete write')


def save_json(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();save(path,raw);return pin(raw)


def postflight(m,p,summary):
    root=clean(m.OUTPUT_ROOT)
    require(root.is_dir() and stat.S_IMODE(root.stat().st_mode)==0o700,'stage root0700')
    expected={x['path']:{'bytes':x['bytes'],'sha256':x['sha256']} for pkg in p['packages'] for x in pkg['selected']}
    require(len(expected)==67 and sum(x['bytes'] for x in expected.values())==3598623,'67expected data identity')
    expected['relocation/autom4te.cfg']=p['derived_cfg']
    expected['STAGING_REPORT.json']={'bytes':summary['report_bytes'],'sha256':summary['report_sha256']}
    dirs=set();files=set();total=0
    for name in expected:dirs.update(str(x) for x in Path(name).parents if str(x)!='.')
    actual_dirs=set()
    for parent,subdirs,names in os.walk(root,followlinks=False):
        require(len(files)+len(names)<=69 and len(actual_dirs)+len(subdirs)<=256,'finite stage inventory')
        for name in subdirs:
            f=Path(parent)/name;info=f.lstat();require(stat.S_ISDIR(info.st_mode) and not f.is_symlink() and stat.S_IMODE(info.st_mode)==0o700,'stage directory0700')
            actual_dirs.add(f.relative_to(root).as_posix())
        for name in names:
            f=Path(parent)/name;relative=f.relative_to(root).as_posix();info=f.lstat()
            require(stat.S_ISREG(info.st_mode) and not f.is_symlink() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'stage file0600 single link')
            require(relative in expected,'no unexpected staged file');checked(f,expected[relative]);total+=info.st_size;files.add(relative)
    require(files==set(expected) and actual_dirs==dirs,'exact staged files/directories')
    require(total==summary['output_bytes']<=8*1024*1024 and summary['output_files']==69,'actual staged bytes/count')
    report=json.loads(checked(root/'STAGING_REPORT.json',expected['STAGING_REPORT.json']))
    require(report['status']=='STAGING_EVIDENCE_PENDING_PARENT_ACCEPTANCE' and report['package_tools_executed'] is False and report['qualification']=='NOT_RUN','staging-only report scope')
    require(report['selected_count']==67 and report['selected_bytes']==3598623 and report['all_original_input_stats_and_hashes_unchanged'] is True,'worker staging scope/count')
    require(report['files']=={name:{**expected[name],'mode':'0o600'} for name in expected if name!='STAGING_REPORT.json'},'exact report68 data rows')
    require(report['relocation']['replacements']==4 and report['relocation']['source_sha256']==m.CFG_SHA and report['relocation']['derived_sha256']==p['derived_cfg']['sha256'],'cfg four-change identity')
    for pkg in p['packages']:checked(Path(m.INPUT_ROOT)/pkg['deb_filename'],{'bytes':pkg['deb_bytes'],'sha256':pkg['deb_sha256']})
    m.require_actual_review(p)
    return {'files':len(files),'bytes':total,'report':expected['STAGING_REPORT.json'],'derived_cfg':p['derived_cfg']}


def expired(_signal,_frame):raise TimeoutError('dependency staging60s absolute deadline')


def process_limits():
    allowed=os.sched_getaffinity(0);require(bool(allowed),'allowed CPU');os.sched_setaffinity(0,{min(allowed)})
    for kind,value in [(resource.RLIMIT_AS,512*1024*1024),(resource.RLIMIT_CPU,40),(resource.RLIMIT_FSIZE,4*1024*1024),(resource.RLIMIT_CORE,0)]:resource.setrlimit(kind,(value,value))


def execute(directory,output,entry):
    stop=entry+60;created=False
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'inherited alarm block')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'inherited timer')
    signal.signal(signal.SIGALRM,expired);require(time.monotonic()<stop,'initial deadline');signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic());process_limits()
    try:
        raw,m,p=preflight(directory);directory=clean(directory);output=clean(output);stage=clean(m.OUTPUT_ROOT)
        require(output.parent.is_dir() and stage.parent.is_dir() and not output.exists() and not stage.exists(),'fresh stage and outer evidence roots')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (directory,stage,clean(m.INPUT_ROOT),Path(__file__).resolve().parent)),'disjoint outer evidence')
        output.mkdir(mode=0o700);created=True;snapshot=output/'source';snapshot.mkdir(mode=0o700)
        for name,data in raw.items():save(snapshot/name,data)
        m=load(raw['stage_dependencies.py'],snapshot/'stage_dependencies.py')
        summary=m.stage_fixed();require(time.monotonic()<stop,'staging work deadline')
        verified=postflight(m,p,summary)
        for name,expected in SOURCE_NAMES.items():checked(directory/name,expected);checked(snapshot/name,expected)
        require(verified['bytes']+sum(len(x) for x in raw.values())+512*1024<=8*1024*1024,'stage plus outer evidence aggregate bound')
        result={'status':'STAGED_DEPENDENCY_DATA_PENDING_OUTER_EXIT0_AND_REVIEW','terminal_success':False,'staged':verified,'selected_count':67,'selected_bytes':3598623,'source_snapshot_originals_unchanged':True,'packages_unchanged':True,'all_staged_modes':'0600','native_child_started':False,'package_tools_executed':False,'elapsed_seconds':time.monotonic()-entry,'acceptance_requires':'original outer exit0 within60 and independent actual staging review; no startup/build qualification'}
        save_json(output/'RESULT.json',result);require(time.monotonic()<stop,'final receipt within same60')
        print(json.dumps(result,sort_keys=True))
    except BaseException as error:
        if created and time.monotonic()<stop:
            try:save_json(output/'FAILURE.json',{'status':'INCOMPLETE_STAGING_PRESERVED','terminal_success':False,'error_type':type(error).__name__,'package_tools_executed':False})
            except BaseException as failure:error.add_note('failure evidence write '+type(failure).__name__)
        raise
    # Disposable process; real timer remains armed through interpreter exit.


def main():
    entry=time.monotonic();p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker-source',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--execute-reviewed-staging',action='store_true');a=p.parse_args()
    if a.execute_reviewed_staging:
        require(a.output is not None,'fresh outer evidence output required');execute(a.worker_source,a.output,entry)
    else:
        require(a.output is None,'SOURCE-only creates no output');_,_,pins=preflight(a.worker_source);print(json.dumps({'status':'SOURCE_ONLY_NO_PACKAGE_READ_OR_STAGING','selected_count':pins['selected_count'],'package_tools_executed':False},sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use -I -S -B');main()
