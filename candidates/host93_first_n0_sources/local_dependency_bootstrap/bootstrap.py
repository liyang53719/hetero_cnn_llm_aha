"""Fixed five-package local SOURCE adapter. No CLI or process-launch API.

Acquisition is an argv handed to the original bounded supervisor. Staging is
only data parsing/writing, intended for its separately supervised 60-second
child. All real bindings are absent from the published template. Native tool
invocation belongs to a later reviewed caller; this module never invokes one.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loading')
if __name__ == '__main__':
    raise SystemExit('load exact pinned bytes through source_entry.py')
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import types

MIB=1024**2
GIB=1024**3
FIVE=('autoconf','autom4te','m4','flex','bison')
SYSTEM=('/usr/bin/gcc','/usr/bin/g++','/usr/bin/make','/usr/bin/ar','/usr/bin/perl','/usr/bin/python3','/bin/sh')
PREFIX='development_snapshots/'
STAGER=PREFIX+'canonical_host93_dependency_source_20261018/worker/stage_dependencies.py'
PACKAGE_PINS=PREFIX+'canonical_host93_dependency_source_20261018/worker/PINS.json'
ACQUIRER=PREFIX+'canonical_verilator_dependencies_source_20261018/worker/acquire_dependencies.py'
PUBLISHED=PREFIX+'canonical_verilator_dependencies_source_20261018/worker/published_acquire.py'
PLAN=PREFIX+'canonical_verilator_dependencies_source_20261018/worker/DEPENDENCY_PLAN.json'
ACQUIRE_GATE=PREFIX+'canonical_verilator_dependencies_source_20261018/run_gate.py'
FILESYSTEM=PREFIX+'canonical_host93_fixed_core_build_source_20261018/run_build_gate.py'
ELF_SOURCE='candidates/host93_micro_diagnostics/run.py'
SOURCE_FILES={'development_snapshots/canonical_host93_dependency_source_20261018/worker/stage_dependencies.py': {'bytes': 20634, 'sha256': '3f56c0b6ce0f41f245abf8d37ff55fa5257d71ead395f49410a2746924682a79'}, 'development_snapshots/canonical_host93_dependency_source_20261018/worker/PINS.json': {'bytes': 205675, 'sha256': 'abc9e5f55b045b6402cc5c13e4d4c4263eb6a7403e84b01a165a12b5d5d20cd0'}, 'development_snapshots/canonical_verilator_dependencies_source_20261018/worker/acquire_dependencies.py': {'bytes': 9150, 'sha256': 'f43ee638df95dfa23955aaaa53581655efbc8eba330bf98ef4d02448fab00009'}, 'development_snapshots/canonical_verilator_dependencies_source_20261018/worker/published_acquire.py': {'bytes': 19263, 'sha256': '4807fc702edfeb98d7eab9b86e727fe6d0d116ae7230200be7babb5a2c5b9b69'}, 'development_snapshots/canonical_verilator_dependencies_source_20261018/worker/DEPENDENCY_PLAN.json': {'bytes': 2594, 'sha256': '80fcca670bc897602db187f8f8db7b0ff7e8c3ee496a5cbef24266a03085be7e'}, 'development_snapshots/canonical_verilator_dependencies_source_20261018/run_gate.py': {'bytes': 12174, 'sha256': '4d58ac5b632a62a8d0506d03ecd6fdb8b7d621b80c552128dd0f6bc8c4858d5f'}, 'development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py': {'bytes': 28551, 'sha256': '8f1560c5f0a8e78a991f98c30031cbd18df220e3eb82cf2c78de4ec0438bdafb'}, 'candidates/host93_micro_diagnostics/run.py': {'bytes': 53278, 'sha256': '235a619fc7d304578ff78a958c173a33cb50d1a860dbf56fe2051fd4396ba3b8'}}
SELECTED_COUNT=67
SELECTED_BYTES=3598623
PACKAGE_BYTES=2466616
ACQUIRE_LIMITS={'total_seconds':180,'work_seconds':160,'cpu_seconds':160,'as_bytes':512*MIB,'fsize_bytes':4*MIB,'tree_bytes':8*MIB,'log_bytes':65536,'sample_rows':182,'file_count':16,'entry_count':32}
STAGE_LIMITS={'total_seconds':60,'work_seconds':40,'cpu_seconds':40,'as_bytes':512*MIB,'fsize_bytes':4*MIB,'tree_bytes':8*MIB,'log_bytes':65536,'sample_rows':62,'file_count':80,'entry_count':256}
UNCHANGED_RESOURCES={'shared_job_wall_seconds':6600,'cpu_affinity_count':1,'host_memory_floor_bytes':8*GIB,'host_disk_floor_bytes':3*GIB,'make_jobs':1,'make_as_bytes':4*GIB,'host_as_bytes':6*GIB}
TRANSPORT=('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE')


def need(ok,reason):
    if not ok:raise ValueError(reason)


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def decode(raw):
    def pairs(rows):
        result={}
        for k,v in rows:
            need(k not in result,'duplicate JSON key');result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=pairs)


def clean(value):
    p=Path(value)
    need(p.is_absolute() and '..' not in p.parts and str(p)==str(value) and
         re.fullmatch(r'/[A-Za-z0-9_/.-]+',str(p)) is not None,'absolute make-safe path')
    return p


def checked(path,expected,cap=4*MIB,*,fixed_leaf=None):
    """Same-buffer read; only catalog/bound file leaves may contain plus."""
    if fixed_leaf is None:path=clean(path)
    else:
        original=path;path=Path(path);clean(path.parent)
        need(str(path)==str(original) and type(fixed_leaf) is str and path.name==fixed_leaf and
             fixed_leaf not in ('.','..') and re.fullmatch(r'[A-Za-z0-9_.+-]+',fixed_leaf) is not None,
             'exact fixed file leaf')
    need(type(expected) is dict and set(expected)=={'bytes','sha256'} and type(expected['bytes']) is int and
         0<=expected['bytes']<=cap and re.fullmatch('[0-9a-f]{64}',expected['sha256']) is not None,'bounded fixed identity')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=nxt
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:
            before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_size==expected['bytes'],'regular exact size')
            chunks=[];count=0
            while count<=expected['bytes']:
                chunk=os.read(fd,min(65536,expected['bytes']+1-count))
                if not chunk:break
                chunks.append(chunk);count+=len(chunk)
            raw=b''.join(chunks)
            stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(pin(raw)==expected and stamp(before)==stamp(os.fstat(fd))==stamp(os.stat(path.name,dir_fd=parent,follow_symlinks=False)),'stable exact bytes')
            return raw
        finally:os.close(fd)
    finally:os.close(parent)


def module(raw,path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__)
    return m


def load_sources(repo):
    repo=clean(repo)
    raw={name:checked(repo/name,p) for name,p in SOURCE_FILES.items()}
    plan=decode(raw[PLAN]);pins=decode(raw[PACKAGE_PINS])
    need(plan['group']=='debian-build-dependencies5' and len(plan['artifacts'])==plan['artifact_count']==5,'fixed five-package group')
    need(plan['transport']=='https-no-redirect' and plan['limits']=={'elapsed_check_seconds':160,'socket_timeout_seconds':30,'total_transfer_bytes':4194304},'original acquisition limits')
    need(sum(x['known_size_bytes'] for x in plan['artifacts'])==PACKAGE_BYTES,'fixed package total')
    need(pins['selected_count']==SELECTED_COUNT and pins['selected_bytes']==SELECTED_BYTES and len(pins['packages'])==5,'fixed selected data totals')
    need(pins['actual_identity_review'] is None and pins['derived_cfg']=={'bytes':None,'sha256':None},'unbound published staging is not actual acceptance')
    selected={}
    for p,a in zip(pins['packages'],plan['artifacts']):
        need((p['package'],p['deb_filename'],p['deb_bytes'],p['deb_sha256'])==(a['package'],a['relative_destination'],a['known_size_bytes'],a['sha256']),'same fixed package plan and full parser pins')
        for row in p['selected']:
            need(row['path'] not in selected,'selected duplicate');selected[row['path']]={k:row[k] for k in ('bytes','sha256')}
    need(len(selected)==SELECTED_COUNT and sum(x['bytes'] for x in selected.values())==SELECTED_BYTES,'exact selected aggregate')
    return {'repo':repo,'raw':raw,'plan':plan,'pins':pins,'selected':selected,
            'stager':module(raw[STAGER],repo/STAGER,'fixed_local_staging_parser'),
            'acquirer':module(raw[ACQUIRER],repo/ACQUIRER,'fixed_local_acquisition_source'),
            'gate':module(raw[ACQUIRE_GATE],repo/ACQUIRE_GATE,'fixed_local_acquisition_postflight'),
            'fs':module(raw[FILESYSTEM],repo/FILESYSTEM,'fixed_local_filesystem_support')}


def source_check(repo):
    s=load_sources(repo)
    return {'status':'SOURCE_ONLY_UNBOUND_NO_ACQUISITION_OR_NATIVE','source_files':SOURCE_FILES,'packages':5,
            'package_bytes':PACKAGE_BYTES,'selected_files':SELECTED_COUNT,'selected_bytes':SELECTED_BYTES,
            'unchanged_resources':UNCHANGED_RESOURCES,'native_qualification':'NOT_RUN'}


def binding(raw,expected,repo):
    need(type(raw) is bytes and pin(raw)==expected and len(raw)<=65536,'same-buffer local binding')
    b=decode(raw)
    need(set(b)=={'schema','work_root','system_programs','native_profile'} and b['schema']=='LOCAL_FIXED_DEPENDENCY_BINDING_V1','binding shape')
    need(b['work_root'] is not None,'local work root UNBOUND')
    work=clean(b['work_root']);repo=clean(repo)
    need(not work.is_relative_to(repo) and not repo.is_relative_to(work),'work outside repository')
    need(type(b['system_programs']) is dict and set(b['system_programs'])==set(SYSTEM),'system identities UNBOUND')
    return b


def paths(b):
    work=clean(b['work_root'])
    return {'work':work,'packages':work/'packages','stage':work/'stage','tools':work/'tools','home':work/'home','tmp':work/'tmp'}


def private_work(p):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in p.parts[1:]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
        info=os.fstat(fd)
        need(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,'private owned work root0700')
    finally:os.close(fd)


def system_identities(s,b):
    result={}
    for invoked in SYSTEM:
        row=b['system_programs'][invoked]
        need(type(row) is dict and set(row)=={'path','bytes','sha256','mode'},'bound system identity shape')
        resolved=Path(os.path.realpath(invoked));need(str(resolved)==row['path'],'system invocation resolution changed')
        checked(resolved,{k:row[k] for k in ('bytes','sha256')},64*MIB,fixed_leaf=Path(row['path']).name)
        need(s['fs'].identity(resolved,64*MIB)=={k:row[k] for k in ('bytes','sha256','mode')} and int(row['mode'],8)&0o111,'system identity or execute mode changed')
        result[invoked]=dict(row)
    return result


def acquisition_argv(s,b,started,work_stop):
    """Construct only. Actual call must use original 180/160 supervisor limits."""
    need(all(type(x) in (int,float) and math.isfinite(x) for x in (started,work_stop)) and started>=0 and started<work_stop<=started+170,'shared acquisition timestamps')
    p=paths(b)
    code=('import sys\nif not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode): raise SystemExit(1)\n'
          'import types,time,json\nfrom pathlib import Path\n'
          'm=types.ModuleType("fixed_local_five_package_acquisition")\nm.__file__='+repr(str(s['repo']/ACQUIRER))+'\n'
          'exec(compile('+repr(s['raw'][ACQUIRER])+',m.__file__,"exec",dont_inherit=True),m.__dict__)\n'
          'stop=m.absolute_deadline('+repr(started)+','+repr(work_stop)+',time.monotonic())\n'
          'e,_=m.namespace('+repr(s['raw'][PUBLISHED])+',stop)\n'
          'plan=json.loads('+repr(s['raw'][PLAN])+')\ne["validate_plan"](plan)\n'
          'root=e["checked_output_root"](Path('+repr(str(p['packages']))+'),Path('+repr(str(s['repo']))+'),must_be_new=True)\n'
          'e["acquire"](plan,root)\n')
    need(len(code.encode())<=64*1024,'bounded acquisition argv')
    return ['/usr/bin/python3','-I','-S','-B','-c',code]


def child_environment(b,acquisition=False):
    p=paths(b)
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C','TZ':'UTC','HOME':str(p['home']),'TMPDIR':str(p['tmp']),
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
    if acquisition:
        for key in TRANSPORT:
            if key in os.environ:env[key]=os.environ[key]
    return env


def receipt_postflight(s,root,verified_raw):
    """Original postflight with exactly its receipt read bound to verified bytes."""
    need(type(verified_raw) is bytes and len(verified_raw)<=65536,'verified receipt buffer')
    raw=s['raw'][ACQUIRE_GATE];lines=raw.splitlines(keepends=True)
    nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='postflight']
    need(len(nodes)==1,'single published receipt postflight')
    n=nodes[0];original=b''.join(lines[n.lineno-1:n.end_lineno])+b'\n'
    old=b'receipt=json.loads(receipt_path.read_bytes())'
    new=b'receipt=json.loads(VERIFIED_RECEIPT_RAW)'
    need(original.count(old)==1 and new not in original,'single receipt buffer anchor')
    projected=original.replace(old,new)
    need(projected.replace(new,old)==original,'reversible receipt buffer projection')
    ns=dict(s['gate'].__dict__);ns['VERIFIED_RECEIPT_RAW']=verified_raw
    exec(compile(projected,'fixed_same_buffer_receipt_postflight','exec',dont_inherit=True),ns)
    return ns['postflight'](root,s['plan'],SOURCE_FILES[PLAN]),{'original':pin(original),'projected':pin(projected)}


def verify_acquisition(s,b,phase,receipt_pin):
    """New same-run evidence only; no historical review or CLI binding."""
    need(type(phase) is dict and set(phase)=={'name','record'} and phase['name']=='local_dependencies_acquire','exact dependency phase')
    need(type(phase['record']['exit_code']) is int and phase['record']['exit_code']==0 and phase['record']['cleanup_confirmed'] is True,'original acquire exit0 and cleanup required')
    p=paths(b);private_work(p['work'])
    receipt_path=p['packages']/'ACQUISITION.json'
    verified_raw=checked(receipt_path,receipt_pin,65536)
    receipt,_=receipt_postflight(s,p['packages'],verified_raw)
    # The original receipt alone cannot confer terminal or native acceptance.
    need(receipt['terminal_success'] is False and receipt['executed'] is False and receipt['installed'] is False,'data-only nonterminal acquisition')
    for package in s['pins']['packages']:
        f=p['packages']/package['deb_filename'];info=f.lstat()
        need(info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'single-link package data')
        checked(f,{'bytes':package['deb_bytes'],'sha256':package['deb_sha256']},fixed_leaf=package['deb_filename'])
    need(checked(receipt_path,receipt_pin,65536)==verified_raw,'receipt changed after postflight')
    return receipt


def relocation(stager,raw,stage):
    """Only bind original function globals; preserve exact original logic."""
    need(pin(raw)=={'bytes':stager.CFG_BYTES,'sha256':stager.CFG_SHA},'fixed cfg source')
    old=stager.CFG_OLD
    new=("args: --prepend-include '"+str(stage)+"/usr/share/autoconf'\n").encode('ascii')
    need(raw.count(old)==4,'four relocation anchors')
    derived=raw.replace(old,new)
    stager.OUTPUT_ROOT=str(stage);stager.CFG_NEW=new
    stager.CFG_DERIVED_BYTES=len(derived);stager.CFG_DERIVED_SHA=pin(derived)['sha256']
    result,report=stager.relocate_cfg(raw)
    need(result==derived and result.replace(new,old)==raw,'exact original relocation function')
    return result,report


def stage_data(repo,binding_raw,binding_pin,phase,acquisition_receipt_pin):
    """For original bounded 60-second Python stage child; no native execution."""
    b=binding(binding_raw,binding_pin,repo);s=load_sources(repo);p=paths(b)
    verify_acquisition(s,b,phase,acquisition_receipt_pin)
    need(not os.path.lexists(p['stage']),'fresh stage only')
    selected={};reports=[]
    for package in s['pins']['packages']:
        raw=checked(p['packages']/package['deb_filename'],{'bytes':package['deb_bytes'],'sha256':package['deb_sha256']},fixed_leaf=package['deb_filename'])
        entries,report=s['stager'].validate_package(raw,package)
        need(not set(selected)&set(entries),'cross-package collision');selected.update(entries);reports.append(report)
    need(len(selected)==SELECTED_COUNT and sum(map(len,selected.values()))==SELECTED_BYTES and
         sum(len(x['ignored_links']) for x in reports)==6,'fixed 67 data and six ignored links')
    cfg,rel=relocation(s['stager'],selected[s['stager'].CFG_PATH],p['stage'])
    writer=s['stager'].FreshWriter(str(p['stage']))
    try:
        for name,raw in sorted(selected.items()):writer.write(name,raw)
        writer.write('relocation/autom4te.cfg',cfg)
        report={'schema':'LOCAL_FIXED_DEPENDENCY_STAGE_V1','status':'DATA_ONLY_PENDING_OUTER_EXIT0_AND_REVIEW',
                'terminal_success':False,'binding':binding_pin,'source_files':SOURCE_FILES,
                'acquisition_receipt':acquisition_receipt_pin,'files':dict(writer.files),
                'selected_count':SELECTED_COUNT,'selected_bytes':SELECTED_BYTES,'relocation':rel,
                'package_tools_executed':False,'installed':False,'native_qualification':'NOT_RUN'}
        raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();need(len(raw)<=512*1024,'bounded stage report')
        writer.write('STAGING_REPORT.json',raw)
    finally:writer.close()
    verify_acquisition(s,b,phase,acquisition_receipt_pin)
    for name,expected in SOURCE_FILES.items():checked(Path(repo)/name,expected)
    return {'stage_report':pin(raw),'relocated_cfg':pin(cfg),'files':69,'native_qualification':'NOT_RUN','terminal_success':False}


def verify_stage(s,b,stage_result,binding_pin):
    p=paths(b);private_work(p['work'])
    report=decode(checked(p['stage']/'STAGING_REPORT.json',stage_result['stage_report'],512*1024))
    need(stage_result['files']==69 and stage_result['terminal_success'] is False and stage_result['native_qualification']=='NOT_RUN','stage result scope')
    need(report['binding']==binding_pin and report['source_files']==SOURCE_FILES and report['selected_count']==SELECTED_COUNT and report['selected_bytes']==SELECTED_BYTES and report['native_qualification']=='NOT_RUN','same local stage binding/source scope')
    need(report['schema']=='LOCAL_FIXED_DEPENDENCY_STAGE_V1' and report['terminal_success'] is False and
         report['installed'] is False and report['package_tools_executed'] is False,'stage data-only scope')
    expected=dict(s['selected']);expected['relocation/autom4te.cfg']=stage_result['relocated_cfg']
    need(report['files']=={name:{**row,'mode':'0o600'} for name,row in expected.items()},'exact staged68 receipt')
    tree=s['fs'].tree_inventory(p['stage'],8*MIB,69,256,4*MIB)
    actual={n:v for n,v in tree['entries'].items() if v['kind']=='regular'}
    need(set(actual)==set(expected)|{'STAGING_REPORT.json'},'exact stage69 inventory')
    for name,row in expected.items():
        checked(p['stage']/name,row,fixed_leaf=Path(name).name)
        info=(p['stage']/name).lstat();need(info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'single-link stage0600')
    original=checked(p['stage']/s['stager'].CFG_PATH,s['selected'][s['stager'].CFG_PATH])
    cfg,_=relocation(s['stager'],original,p['stage']);need(pin(cfg)==stage_result['relocated_cfg'],'path-bound relocated cfg')
    return expected


def elf_reader(s,allowed):
    """Exact one-function projection; no new ELF/archive parser."""
    raw=s['raw'][ELF_SOURCE];lines=raw.splitlines(keepends=True)
    nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='elf_dependencies']
    need(len(nodes)==1,'single published ELF reader')
    n=nodes[0];projected=b''.join(lines[n.lineno-1:n.end_lineno])+b'\n'
    ns={'require':need,'struct':struct,'MIB':MIB,'INTERPRETER':'/lib64/ld-linux-x86-64.so.2','LIBRARIES':tuple(allowed)}
    exec(compile(projected,'exact_published_elf_dependencies','exec',dont_inherit=True),ns)
    return ns['elf_dependencies'],pin(projected)


def native_preflight(s,b,expected):
    """Read-only system/ELF boundary. Unbound profile always stops before copy."""
    profile=b['native_profile']
    need(type(profile) is dict and set(profile)=={'package_elf','script_interpreters','libraries'},'native profile UNBOUND')
    need(set(profile['package_elf'])=={'m4','flex','bison'} and set(profile['script_interpreters'])=={'autoconf','autom4te'},'fixed package ELF/script set')
    libraries=profile['libraries'];need(type(libraries) is dict and 1<=len(libraries)<=16 and 'ld-linux-x86-64.so.2' in libraries,'finite bound library closure')
    need(all(re.fullmatch(r'[A-Za-z0-9_.+-]+',n) for n in libraries),'literal bound sonames')
    reader,projection=elf_reader(s,libraries);p=paths(b);programs=system_identities(s,b)
    observed={}
    for name,row in libraries.items():
        need(type(row) is dict and set(row)=={'invoked','path','bytes','sha256','mode','needed','interpreter'},'library binding shape')
        invoked=Path(row['invoked']);resolved=Path(os.path.realpath(invoked))
        need(row['invoked']==('/lib64/ld-linux-x86-64.so.2' if name=='ld-linux-x86-64.so.2' else '/usr/lib/x86_64-linux-gnu/'+name) and
             resolved==Path(row['path']) and str(resolved).startswith('/usr/lib/x86_64-linux-gnu/'),'fixed system library resolution')
        before=resolved.stat();need(before.st_uid==0 and stat.S_ISREG(before.st_mode) and not before.st_mode&0o022,'protected system library')
        raw=checked(resolved,{k:row[k] for k in ('bytes','sha256')},32*MIB,fixed_leaf=Path(row['path']).name);meta=reader(raw)
        need(meta=={k:row[k] for k in ('needed','interpreter')} and set(meta['needed'])<=set(libraries),'exact transitive library metadata')
        need(oct(stat.S_IMODE(resolved.stat().st_mode))==row['mode'] and Path(os.path.realpath(invoked))==resolved,'library identity mode/resolution')
        observed[name]=dict(row)
    for tool in ('m4','flex','bison'):
        raw=checked(p['stage']/('usr/bin/'+tool),expected['usr/bin/'+tool]);meta=reader(raw)
        need(meta==profile['package_elf'][tool] and meta['interpreter']=='/lib64/ld-linux-x86-64.so.2','exact package ELF preflight')
    for tool in ('autoconf','autom4te'):
        row=profile['script_interpreters'][tool]
        need(type(row) is dict and set(row)=={'first_line','invoked'} and row['invoked'] in ('/bin/sh','/usr/bin/perl'),'fixed script interpreter binding')
        raw=checked(p['stage']/('usr/bin/'+tool),expected['usr/bin/'+tool])
        first=raw.split(b'\n',1)[0].decode('ascii')
        need(first==row['first_line'] and first.startswith('#!') and first[2:].strip()==row['invoked'],'exact direct script interpreter')
    return {'system_programs':programs,'libraries':observed,'elf_projection':projection,
            'status':'STATIC_IDENTITIES_ONLY_NATIVE_QUALIFICATION_NOT_RUN','symbol_version_compatibility_proved':False}


def prepare_tools(repo,binding_raw,binding_pin,stage_result):
    """Future supervised data copy after explicit native profile; never run tools."""
    b=binding(binding_raw,binding_pin,repo);s=load_sources(repo);p=paths(b)
    expected=verify_stage(s,b,stage_result,binding_pin);preflight=native_preflight(s,b,expected)
    need(not os.path.lexists(p['tools']),'fresh private tool copy only')
    s['fs'].fresh_directory(p['tools'])
    for name,row in sorted(expected.items()):
        s['fs'].copy_member(p['stage']/name,p['tools'],name,row,0o700 if name in {'usr/bin/'+n for n in FIVE} else 0o600)
    tree=s['fs'].tree_inventory(p['tools'],8*MIB,68,256,4*MIB)
    need({n for n,v in tree['entries'].items() if v['kind']=='regular'}==set(expected),'exact tool-copy68 inventory')
    for name,row in expected.items():
        actual=tree['entries'][name];mode='0o700' if name in {'usr/bin/'+n for n in FIVE} else '0o600'
        need({k:actual[k] for k in ('bytes','sha256','mode')}=={**row,'mode':mode},'tool copy identity/mode drift')
    programs=dict(preflight['system_programs'])
    for tool in FIVE:
        invoked=str(p['tools']/'usr/bin'/tool)
        programs[invoked]={'path':invoked,**s['fs'].identity(invoked,4*MIB)}
        need(programs[invoked]['mode']=='0o700','private executable copy mode')
    verify_stage(s,b,stage_result,binding_pin);need(native_preflight(s,b,expected)==preflight,'native identities changed during copy')
    for name,row in SOURCE_FILES.items():checked(Path(repo)/name,row)
    return {'host_programs':programs,'tool_root':str(p['tools']),'stage_root':str(p['stage']),
            'native_preflight':preflight,'native_qualification':'NOT_RUN','terminal_success':False,
            'environment':tool_environment(b)}


def tool_environment(b):
    p=paths(b);binpath=p['tools']/'usr/bin';share=p['stage']/'usr/share'
    env=child_environment(b)
    env.update(PATH=str(binpath)+':/usr/bin:/bin',SHELL='/bin/sh',CONFIG_SHELL='/bin/sh',CONFIG_SITE='/dev/null',
               AUTOM4TE=str(binpath/'autom4te'),M4=str(binpath/'m4'),LEX=str(binpath/'flex'),YACC=str(binpath/'bison'),
               autom4te_perllibdir=str(share/'autoconf'),AC_MACRODIR=str(share/'autoconf'),
               trailer_m4=str(share/'autoconf/autoconf/trailer.m4'),AUTOM4TE_CFG=str(p['stage']/'relocation/autom4te.cfg'),
               BISON_PKGDATADIR=str(share/'bison'),MAKE='/usr/bin/make',CC='/usr/bin/gcc',CXX='/usr/bin/g++',
               AR='/usr/bin/ar',PERL='/usr/bin/perl',PYTHON3='/usr/bin/python3',OBJCACHE='',ac_cv_prog_OBJCACHE='')
    return env
