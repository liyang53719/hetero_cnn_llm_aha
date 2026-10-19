"""Explicit LOCAL_READONLY_MOUNT_PROFILE; original CI UID0 branch unchanged."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B')
if __name__=='__main__':raise SystemExit('use pinned observer_entry.py')
import ast
import os
from pathlib import Path
import stat


def fixed_files(g,b):
    g.need(type(b['native_profile']) is dict,'complete native profile required')
    rows={}
    for row in list(b['system_programs'].values())+list(b['native_profile']['libraries'].values()):
        path=row['path'];g.need(path.startswith('/usr/'),'fixed profile usr path')
        identity={k:row[k] for k in ('bytes','sha256','mode')}
        g.need(path not in rows or rows[path]==identity,'single fixed path identity');rows[path]=identity
    g.need(7<=len(rows)<=23,'bounded fixed profile file set')
    return rows


def descriptor_snapshot(g,path,expected):
    path=Path(path);g.clean(path.parent)
    # checked handles the explicit file leaf, stable exact buffer, no symlinks.
    verified=g.checked(path,{k:expected[k] for k in ('bytes','sha256')},64*g.MIB,fixed_leaf=path.name)
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:
            before=os.fstat(fd);vfs=os.fstatvfs(fd)
            g.need(stat.S_ISREG(before.st_mode) and before.st_size==expected['bytes'] and not before.st_mode&0o022,'protected fixed profile file')
            g.need(vfs.f_flag&os.ST_RDONLY,'same-fd filesystem must be readonly')
            data=[];count=0
            while count<=expected['bytes']:
                part=os.read(fd,min(65536,expected['bytes']+1-count))
                if not part:break
                data.append(part);count+=len(part)
            raw=b''.join(data)
            stamp=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            g.need(raw==verified and stamp(before)==stamp(os.fstat(fd))==stamp(os.stat(path.name,dir_fd=parent,follow_symlinks=False)),'same-fd profile bytes/identity drift')
            g.need(os.fstatvfs(fd).f_flag&os.ST_RDONLY,'same-fd readonly changed')
            g.need(oct(stat.S_IMODE(before.st_mode))==expected['mode'],'fixed profile mode')
            return {**expected,'uid':before.st_uid,'gid':before.st_gid,'device':before.st_dev,'inode':before.st_ino,'readonly_same_fd':True}
        finally:os.close(fd)
    finally:os.close(parent)


def snapshot(g,observer,b):
    rows=fixed_files(g,b);evidence=observer.userns_evidence(g,rows)
    g.need(evidence['euid']==1000 and evidence['egid']==1000 and evidence['groups']==[],'fixed local identity')
    g.need(evidence['uid_map'].split()==['1000','0','1'] and evidence['gid_map'].split()==['1000','0','1'],'fixed local user namespace maps')
    observations={}
    for path,expected in rows.items():
        item=evidence['observed'][path];mount=item['covering_mount']
        g.need({'ro','nosuid','nodev'}<=set(mount['options']),'longest covering mount must be ro,nosuid,nodev')
        for row in item['chain'].values():
            g.need(not int(row['mode'],8)&0o022 and row['writable_by_current_process'] is False,'protected local path ancestors')
        observations[path]={'file':descriptor_snapshot(g,path,expected),'covering_mount':mount,'chain':item['chain']}
    return {'schema':'LOCAL_READONLY_MOUNT_PROFILE_V1','binding_pin':g.pin(observer.canonical(b)),'euid':1000,'egid':1000,'groups':[],
            'uid_map':evidence['uid_map'],'gid_map':evidence['gid_map'],'kernel_pins':{k:evidence['kernel_pins'][k] for k in ('uid_map','gid_map','overflowuid')},
            'files':observations,'trust_basis':'EXPLICIT_FIXED_FILES_IN_READONLY_USER_NAMESPACE',
            'host_uid0_inferred':False,'official_file_provenance_proved':False}


def construct(g,observer,b):
    first=snapshot(g,observer,b);g.need(snapshot(g,observer,b)==first,'local trust profile changed during construction')
    return first


def validate(g,observer,b,profile):
    g.need(type(profile) is dict and profile.get('schema')=='LOCAL_READONLY_MOUNT_PROFILE_V1','explicit local trust profile required')
    g.need(snapshot(g,observer,b)==profile,'local trust profile drift')
    return True


def native_checker(g,observer,b,profile,selected=None):
    """Single owner-predicate projection; optional five exact in-memory inputs."""
    validate(g,observer,b,profile)
    raw=g.checked(Path(g.__file__),{'bytes':25509,'sha256':'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'})
    lines=raw.splitlines(keepends=True);nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='native_preflight']
    g.need(len(nodes)==1,'single original native preflight')
    n=nodes[0];original=b''.join(lines[n.lineno-1:n.end_lineno])+b'\n'
    old=b'before.st_uid==0';new=b'local_owner(before,resolved)'
    g.need(original.count(old)==1 and new not in original,'single explicit local owner anchor')
    projected=original.replace(old,new);g.need(projected.replace(new,old)==original,'reversible local owner projection')
    def owner(before,path):
        expected=profile['files'].get(str(path));g.need(expected is not None,'library absent from explicit local profile')
        g.need(descriptor_snapshot(g,path,{k:expected['file'][k] for k in ('bytes','sha256','mode')})==expected['file'],'local library identity changed')
        g.need((before.st_uid,before.st_gid,before.st_dev,before.st_ino)==tuple(expected['file'][k] for k in ('uid','gid','device','inode')),'owner predicate same observed file')
        return True
    ns=dict(g.__dict__);ns['local_owner']=owner
    if selected is not None:
        # No stage tree is fabricated. Only these five exact original package
        # buffers stand in for stage reads during this read-only observation.
        expected_paths={str(g.paths(b)['stage']/('usr/bin/'+tool)):'usr/bin/'+tool for tool in g.FIVE}
        def read(path,expected,*args,**kwargs):
            if str(path) in expected_paths:
                data=selected[expected_paths[str(path)]];g.need(g.pin(data)==expected,'exact package buffer for native preflight');return data
            return g.checked(path,expected,*args,**kwargs)
        ns['checked']=read
    exec(compile(projected,'explicit_local_owner_native_preflight','exec',dont_inherit=True),ns)
    def checked(s,bound,expected):
        g.need(bound==b,'same explicit profile binding');validate(g,observer,b,profile)
        result=ns['native_preflight'](s,bound,expected)
        validate(g,observer,b,profile)
        return result
    return checked,{'original':g.pin(original),'projected':g.pin(projected),'owner_substitutions':1,'inverse_exact':True,
                   'stage_input_mode':'FIVE_EXACT_PACKAGE_BUFFERS' if selected is not None else 'ORIGINAL_STAGE_READS'}
