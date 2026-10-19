"""Read-only fixed local binding construction; no tool/network/process API."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before source loading')
if __name__=='__main__':raise SystemExit('use pinned observer_entry.py')
import json
import os
from pathlib import Path
import stat
import types

# Existing published ELF reader's finite soname vocabulary; no host lib search.
LIBRARIES=('libbz2.so.1.0','libc.so.6','libgcc_s.so.1','libm.so.6','libreadline.so.8','libstdc++.so.6','libz.so.1','libtinfo.so.6','ld-linux-x86-64.so.2')
LOADER='/lib64/ld-linux-x86-64.so.2'


def canonical(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def known_identity(g,s,path,cap):
    """Observe identity, then consume only its stable exact checked buffer."""
    path=Path(path);row=s['fs'].identity(path,cap)
    raw=g.checked(path,{k:row[k] for k in ('bytes','sha256')},cap,fixed_leaf=path.name)
    g.need(s['fs'].identity(path,cap)==row,'identity changed after observed buffer')
    return raw,row


def system_programs(g,s):
    result={}
    for invoked in g.SYSTEM:
        resolved=Path(os.path.realpath(invoked));g.clean(resolved.parent)
        raw,row=known_identity(g,s,resolved,64*g.MIB)
        g.need(int(row['mode'],8)&0o111,'bound system execute mode')
        g.need(Path(os.path.realpath(invoked))==resolved,'system resolution changed during observation')
        result[invoked]={'path':str(resolved),**row}
    g.need(g.system_identities(s,{'system_programs':result})==result,'bootstrap system identity recheck')
    return result


def package_members(g,s,package_root):
    package_root=g.clean(package_root)
    selected={};reports=[]
    for package in s['pins']['packages']:
        raw=g.checked(package_root/package['deb_filename'],{'bytes':package['deb_bytes'],'sha256':package['deb_sha256']},fixed_leaf=package['deb_filename'])
        data,report=s['stager'].validate_package(raw,package)
        g.need(not set(selected)&set(data),'cross-package selected collision')
        selected.update(data);reports.append(report)
    g.need(len(selected)==g.SELECTED_COUNT and sum(map(len,selected.values()))==g.SELECTED_BYTES and
           sum(len(r['ignored_links']) for r in reports)==6,'fixed package/member aggregate')
    g.need({n:g.pin(b) for n,b in selected.items()}==s['selected'],'fixed selected identities')
    for package in s['pins']['packages']:
        g.checked(package_root/package['deb_filename'],{'bytes':package['deb_bytes'],'sha256':package['deb_sha256']},fixed_leaf=package['deb_filename'])
    return selected


def library_row(g,s,reader,name):
    g.need(name in LIBRARIES,'fixed local soname vocabulary')
    invoked=LOADER if name=='ld-linux-x86-64.so.2' else '/usr/lib/x86_64-linux-gnu/'+name
    resolved=Path(os.path.realpath(invoked))
    g.need(str(resolved).startswith('/usr/lib/x86_64-linux-gnu/'),'fixed system library resolution')
    before=resolved.stat()
    g.need(stat.S_ISREG(before.st_mode) and not before.st_mode&0o022,'protected system library mode')
    raw,row=known_identity(g,s,resolved,32*g.MIB);meta=reader(raw)
    after=resolved.stat()
    g.need((before.st_uid,before.st_gid,before.st_mode,before.st_dev,before.st_ino)==
           (after.st_uid,after.st_gid,after.st_mode,after.st_dev,after.st_ino) and
           Path(os.path.realpath(invoked))==resolved,'library owner/mode/resolution changed')
    return {'invoked':invoked,'path':str(resolved),**row,**meta},{'uid':after.st_uid,'gid':after.st_gid,'writable_by_current_process':os.access(resolved,os.W_OK)}


def native_profile(g,s,selected):
    reader,projection=g.elf_reader(s,LIBRARIES)
    profile={'package_elf':{},'script_interpreters':{},'libraries':{}}
    needed={'ld-linux-x86-64.so.2'}
    for tool in ('m4','flex','bison'):
        meta=reader(selected['usr/bin/'+tool]);g.need(meta['interpreter']==LOADER,'fixed package interpreter')
        profile['package_elf'][tool]=meta;needed.update(meta['needed'])
    for tool in ('autoconf','autom4te'):
        first=selected['usr/bin/'+tool].split(b'\n',1)[0].decode('ascii')
        g.need(first.startswith('#!') and first[2:].strip() in ('/bin/sh','/usr/bin/perl'),'fixed direct script interpreter')
        profile['script_interpreters'][tool]={'first_line':first,'invoked':first[2:].strip()}
    owners={}
    while needed-set(profile['libraries']):
        name=sorted(needed-set(profile['libraries']))[0]
        row,owner=library_row(g,s,reader,name);profile['libraries'][name]=row;owners[name]=owner
        needed.update(row['needed']);g.need(needed<=set(LIBRARIES),'fixed transitive closure')
    for name,row in profile['libraries'].items():
        after,owner=library_row(g,s,reader,name)
        g.need(after==row and owner==owners[name],'library closure changed during observation')
    return profile,owners,projection


def kernel_bytes(path,cap):
    """Only fixed proc metadata, bounded read, never a command or proc scan."""
    if path not in ('/proc/self/uid_map','/proc/self/gid_map','/proc/self/mountinfo','/proc/sys/kernel/overflowuid'):
        raise ValueError('fixed kernel metadata path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        chunks=[];count=0
        while count<=cap:
            raw=os.read(fd,min(65536,cap+1-count))
            if not raw:break
            chunks.append(raw);count+=len(raw)
        if count>cap:raise ValueError('kernel metadata cap')
        return b''.join(chunks)
    finally:os.close(fd)


def userns_evidence(g,paths):
    """Evidence for separate trust-profile review; never substitutes UID0."""
    uid=kernel_bytes('/proc/self/uid_map',4096);gid=kernel_bytes('/proc/self/gid_map',4096)
    overflow=kernel_bytes('/proc/sys/kernel/overflowuid',64)
    mounts=kernel_bytes('/proc/self/mountinfo',256*1024)
    rows=[]
    for line in mounts.decode('ascii').splitlines():
        left,right=line.split(' - ',1);fields=left.split();fs=right.split()
        if len(fields)<6 or len(fs)<3:raise ValueError('mount metadata shape')
        rows.append({'mount_id':fields[0],'parent_id':fields[1],'device':fields[2],'root':fields[3],
                     'mountpoint':fields[4],'options':fields[5].split(','),'filesystem':fs[0]})
    observed={}
    for value in sorted(set(paths)):
        path=g.clean(Path(value).parent)/Path(value).name
        g.need(str(path).startswith('/usr/'),'local trust evidence restricted to usr')
        candidates=[r for r in rows if str(path)==r['mountpoint'] or str(path).startswith(r['mountpoint'].rstrip('/')+'/')]
        g.need(bool(candidates),'covering mount metadata')
        cover=max(candidates,key=lambda r:len(r['mountpoint']))
        chain={}
        for p in (path,)+tuple(p for p in path.parents if str(p).startswith('/usr')):
            info=p.stat();chain[str(p)]={'uid':info.st_uid,'gid':info.st_gid,'mode':oct(stat.S_IMODE(info.st_mode)),
                                      'writable_by_current_process':os.access(p,os.W_OK)}
        observed[str(path)]={'covering_mount':cover,'chain':chain}
    return {'schema':'LOCAL_USERNS_RO_EVIDENCE_V1','euid':os.geteuid(),'egid':os.getegid(),'groups':os.getgroups(),
            'uid_map':uid.decode('ascii'),'gid_map':gid.decode('ascii'),'overflowuid':overflow.decode('ascii').strip(),
            'kernel_pins':{'uid_map':g.pin(uid),'gid_map':g.pin(gid),'mountinfo':g.pin(mounts),'overflowuid':g.pin(overflow)},
            'observed':observed,'official_file_provenance_proved':False,'trust_profile_accepted':False,
            'original_bootstrap_uid0_predicate_changed':False}


def observe(g,s,work_root,package_root,local_adapter=None):
    """Construct original binding schema or explicit incomplete result; read-only."""
    work=g.clean(work_root);packages=g.clean(package_root);repo=g.clean(s['repo'])
    g.need(not any(work.is_relative_to(p) or p.is_relative_to(work) for p in (repo,packages)),'work separate from source inputs')
    if os.path.lexists(work):
        g.private_work(work);g.need(not any(work.iterdir()),'explicit work root must be empty and private')
    base={'schema':'LOCAL_FIXED_DEPENDENCY_BINDING_V1','work_root':str(work),'system_programs':None,'native_profile':None}
    blockers=[];owners={};projection=None
    def blocked(boundary,error):
        blockers.append({'boundary':boundary,'exception':type(error).__name__,'reason':str(error)})
    try:base['system_programs']=system_programs(g,s)
    except (ValueError,OSError) as e:blocked('SYSTEM_PROGRAM_IDENTITIES',e)
    selected=None
    # List every missing fixed input instead of stopping at only the first.
    missing=[p['deb_filename'] for p in s['pins']['packages'] if not os.path.lexists(packages/p['deb_filename'])]
    if missing:blockers.append({'boundary':'FIXED_FIVE_PACKAGE_INPUTS','reason':'missing fixed official package bytes','missing':missing})
    else:
        try:selected=package_members(g,s,packages)
        except (ValueError,OSError) as e:blocked('FIXED_PACKAGE_PARSER',e)
    if selected is not None:
        try:base['native_profile'],owners,projection=native_profile(g,s,selected)
        except (ValueError,OSError,UnicodeError) as e:blocked('FIXED_NATIVE_METADATA',e)
    local_profile=None;local_projection=None;static_result=None
    if owners and local_adapter is not None:
        try:
            observer=types.SimpleNamespace(userns_evidence=userns_evidence,canonical=canonical)
            local_profile=local_adapter.construct(g,observer,base)
            checker,local_projection=local_adapter.native_checker(g,observer,base,local_profile,selected)
            static_result=checker(s,base,s['selected'])
        except (ValueError,OSError,UnicodeError) as e:blocked('EXPLICIT_LOCAL_READONLY_PROFILE',e)
    if owners and local_adapter is None:
        bad={n:row['uid'] for n,row in owners.items() if row['uid']!=0}
        if bad:blockers.append({'boundary':'ORIGINAL_NATIVE_LIBRARY_UID0','reason':'original native_preflight requires root-owned libraries','observed_uids':bad})
    observed_paths=[row['path'] for row in (base['system_programs'] or {}).values()]
    observed_paths += [row['path'] for row in (base['native_profile'] or {}).get('libraries',{}).values()]
    # Loader can be observed even if package bodies are absent; this is not inferred package metadata.
    observed_paths.append(os.path.realpath(LOADER))
    try:evidence=userns_evidence(g,observed_paths)
    except (ValueError,OSError,UnicodeError) as e:evidence=None;blocked('USERNS_EVIDENCE',e)
    raw=canonical(base);shape_valid=False
    if base['system_programs'] is not None:
        g.need(g.binding(raw,g.pin(raw),repo)==base,'canonical original binding roundtrip');shape_valid=True
    for name,expected in g.SOURCE_FILES.items():g.checked(repo/name,expected)
    return {'schema':'LOCAL_BINDING_OBSERVATION_V1','status':'COMPLETE_STATIC_BINDING_UNQUALIFIED' if not blockers else 'INCOMPLETE_EXPLICIT_REJECTION',
            'binding':base if not blockers else None,'binding_pin':g.pin(raw) if not blockers else None,
            'partial_binding':base if blockers else None,'original_binding_shape_verified':shape_valid,
            'blockers':blockers,'local_readonly_profile':local_profile,'local_profile_pin':g.pin(canonical(local_profile)) if local_profile is not None else None,
            'local_projection':local_projection,'static_native_preflight':static_result,'library_owners':owners,'elf_projection':projection,'userns_evidence':evidence,
            'work_root_created':False,'package_data_written':False,'native_qualification':'NOT_RUN','symbol_version_compatibility_proved':False,
            'actual_authorization':False,'native_started':False,'network_started':False}
