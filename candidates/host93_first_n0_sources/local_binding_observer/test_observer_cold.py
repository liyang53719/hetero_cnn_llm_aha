"""Finite local-profile mock contracts; no native or network operations."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import copy,json,os,stat,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def check(name,fn):fn();checks.append(name)
def rejects(fn,text):
    try:fn()
    except (ValueError,OSError) as e:
        g.need(text in str(e),'wrong rejection '+str(e));return
    raise ValueError('missing rejection '+text)

# Small synthetic binding metadata, with exact fixed program keys.
base={'schema':'LOCAL_FIXED_DEPENDENCY_BINDING_V1','work_root':'/synthetic/future_work','system_programs':{},
      'native_profile':{'package_elf':{},'script_interpreters':{},'libraries':{}}}
for n in g.SYSTEM:base['system_programs'][n]={'path':'/usr/bin/'+Path(n).name,**g.pin(b'x'),'mode':'0o755'}
rows=l.fixed_files(g,base)
def evidence():
    return {'euid':1000,'egid':1000,'groups':[],'uid_map':'1000 0 1\n','gid_map':'1000 0 1\n',
            'kernel_pins':{n:g.pin(b'fixed') for n in ('uid_map','gid_map','mountinfo','overflowuid')},
            'observed':{p:{'covering_mount':{'mount_id':'1','mountpoint':'/usr','options':['ro','nosuid','nodev']},
                          'chain':{p:{'uid':65534,'gid':65534,'mode':'0o755','writable_by_current_process':False}}} for p in rows}}
def fd_snapshot(g,path,expected):return {**expected,'uid':65534,'gid':65534,'device':27,'inode':1,'readonly_same_fd':True}
def mocked_snapshot(e=None):
    stub=types.SimpleNamespace(userns_evidence=lambda *args:e if e is not None else evidence(),canonical=o.canonical)
    with mock.patch.object(l,'descriptor_snapshot',side_effect=fd_snapshot):return l.snapshot(g,stub,base)

def positive():
    p=mocked_snapshot();g.need(p['schema']=='LOCAL_READONLY_MOUNT_PROFILE_V1' and p['host_uid0_inferred'] is False,'explicit profile positive')
    g.need(p['binding_pin']==g.pin(o.canonical(base)) and set(p['files'])==set(rows),'exact binding/file scope')
check('explicit_profile_positive_fixed_binding_and_no_hostuid_inference',positive)

def identity_negatives():
    for key,value in [('euid',0),('egid',0),('groups',[1000]),('uid_map','0 0 1'),('gid_map','1000 1000 1')]:
        e=evidence();e[key]=value;rejects(lambda:mocked_snapshot(e),'fixed local')
check('wrong_euid_gid_groups_and_namespace_maps_rejected',identity_negatives)

def mount_negatives():
    for flags in (['rw','nosuid','nodev'],['ro','nodev'],['ro','nosuid'],[]):
        e=evidence();next(iter(e['observed'].values()))['covering_mount']['options']=flags
        rejects(lambda:mocked_snapshot(e),'longest covering mount')
    for key,value in [('mode','0o777'),('writable_by_current_process',True)]:
        e=evidence();next(iter(next(iter(e['observed'].values()))['chain'].values()))[key]=value
        rejects(lambda:mocked_snapshot(e),'protected local path ancestors')
check('writable_or_unknown_mount_flags_and_mutable_ancestors_rejected',mount_negatives)

def profile_drift():
    p=mocked_snapshot();stub=types.SimpleNamespace()
    with mock.patch.object(l,'snapshot',side_effect=[p,dict(p,euid=1)]):rejects(lambda:l.construct(g,stub,base),'changed during construction')
    with mock.patch.object(l,'snapshot',return_value=p):
        g.need(l.validate(g,stub,base,p),'exact profile validation')
        for key in ('uid_map','kernel_pins','files','binding_pin'):
            q=copy.deepcopy(p);q[key]=None;rejects(lambda:l.validate(g,stub,base,q),'profile drift')
        rejects(lambda:l.validate(g,stub,base,None),'explicit local trust')
check('profile_construction_drift_pin_file_mount_and_binding_rejected',profile_drift)

def descriptors():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        path=Path(t)/'g++';path.write_bytes(b'fixed');path.chmod(0o600);expected={**g.pin(b'fixed'),'mode':'0o600'}
        with mock.patch.object(l.os,'fstatvfs',return_value=types.SimpleNamespace(f_flag=0)):
            rejects(lambda:l.descriptor_snapshot(g,path,expected),'filesystem must be readonly')
        with mock.patch.object(l.os,'fstatvfs',side_effect=[types.SimpleNamespace(f_flag=os.ST_RDONLY),types.SimpleNamespace(f_flag=0)]):
            rejects(lambda:l.descriptor_snapshot(g,path,expected),'readonly changed')
        with mock.patch.object(l.os,'fstatvfs',return_value=types.SimpleNamespace(f_flag=os.ST_RDONLY)):
            found=l.descriptor_snapshot(g,path,expected);g.need(found['uid']==path.stat().st_uid and found['readonly_same_fd'],'same fd positive synthetic vfs')
            rejects(lambda:l.descriptor_snapshot(g,path,dict(expected,sha256='0'*64)),'stable exact bytes')
            rejects(lambda:l.descriptor_snapshot(g,path,dict(expected,mode='0o755')),'fixed profile mode')
            path.chmod(0o666);rejects(lambda:l.descriptor_snapshot(g,path,dict(expected,mode='0o666')),'protected fixed profile')
check('same_fd_vfs_both_sides_hash_mode_and_plus_leaf',descriptors)

def longest_mount():
    mount=b'1 0 0:1 / / ro,nosuid,nodev - tmpfs tmpfs rw\n2 1 0:2 /usr /usr ro,nosuid,nodev - overlay overlay rw\n3 2 0:3 / /usr/bin rw,nosuid,nodev - tmpfs tmpfs rw\n'
    values={'/proc/self/mountinfo':mount,'/proc/self/uid_map':b'1000 0 1\n','/proc/self/gid_map':b'1000 0 1\n','/proc/sys/kernel/overflowuid':b'65534\n'}
    with mock.patch.object(o,'kernel_bytes',side_effect=lambda p,cap:values[p]),mock.patch.object(Path,'stat',return_value=types.SimpleNamespace(st_uid=65534,st_gid=65534,st_mode=0o100755)),mock.patch.object(os,'access',return_value=False):
        e=o.userns_evidence(g,['/usr/bin/g++']);g.need(e['observed']['/usr/bin/g++']['covering_mount']['mount_id']=='3','nested writable mount wins')
    rejects(lambda:o.kernel_bytes('/etc/passwd',4096),'fixed kernel metadata')
check('longest_covering_nested_mount_and_fixed_proc_paths',longest_mount)

def missing_packages():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        root=Path(t);packages=root/'packages';packages.mkdir();work=root/'work'
        with mock.patch.object(o,'system_programs',return_value=base['system_programs']),mock.patch.object(o,'userns_evidence',return_value={}):
            result=o.observe(g,s,work,packages)
        g.need(result['binding'] is None and len(result['blockers'][0]['missing'])==5 and not work.exists(),'explicit five missing and no work writes')
        rejects(lambda:o.observe(g,s,packages,packages),'work separate')
check('all_five_missing_packages_reported_without_work_creation',missing_packages)

def parser_pin():
    with tempfile.TemporaryDirectory(dir=TEST_ROOT) as t:
        root=Path(t)
        for p in s['pins']['packages']:(root/p['deb_filename']).write_bytes(b'not original')
        with mock.patch.object(s['stager'],'validate_package',side_effect=AssertionError('unverified bytes parsed')):
            rejects(lambda:o.package_members(g,s,root),'regular exact size')
check('fixed_package_pin_rejects_before_original_parser',parser_pin)

def finite_libs():
    rejects(lambda:o.library_row(g,s,lambda x:None,'foreign.so'),'fixed local soname')
    b=copy.deepcopy(base);b['system_programs']['/usr/bin/gcc']['path']='/tmp/gcc'
    rejects(lambda:l.fixed_files(g,b),'fixed profile usr path')
check('unknown_soname_and_foreign_system_file_refused',finite_libs)

print(json.dumps({'status':'PASS_FINITE_BINDING_PROFILE_COLD','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,
                  'network_started':False,'native_started':False,'real_package_downloaded':False,'mock_vfs_not_actual_trust':True},sort_keys=True))
