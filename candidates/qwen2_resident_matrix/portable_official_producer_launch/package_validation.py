"""Cold checks of exact wheel provenance and installed metadata; imports no math.

Report v1 fields follow https://pip.pypa.io/en/stable/reference/installation-report/.
Reports alone are not qualification: the parent owns the actual pip command and
also checks the resulting private interpreter's distribution inventory.
"""
import json
import re
from urllib.parse import urlsplit, unquote

TARGET=dict(python='3.12.15',implementation='CPython',os='Linux',machine='x86_64',minimum_glibc='2.28')


def need(value,reason):
    if not value: raise ValueError('fresh package closure: '+reason)


def normalized(name):
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',name) is not None,'distribution name')
    return re.sub(r'[-_.]+','-',name).lower()


def digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def validate_lock(value):
    need(type(value) is dict and value.get('schema')==1 and type(value['schema']) is int,'lock schema')
    need(value.get('target')==TARGET and value.get('status')=='METADATA_LOCK_COMPLETE_NOT_INSTALLED','lock target')
    packages=value.get('packages');need(type(packages) is list and len(packages)==26,'26 package closure')
    seen={}
    for p in packages:
        need(type(p) is dict,'package object')
        name=normalized(p.get('name'));need(name==p['name'] and name not in seen,'unique canonical package')
        need(type(p.get('version')) is str and re.fullmatch(r'[0-9A-Za-z.+!-]+',p['version']) is not None,'package version')
        need(p.get('role')==('provisioning-tool' if name=='pip' else 'runtime'),'package role')
        url=p.get('url');need(type(url) is str,'official URL')
        parts=urlsplit(url)
        need(parts.scheme=='https' and parts.hostname in ('files.pythonhosted.org','download-r2.pytorch.org') and
             parts.netloc==parts.hostname and not parts.query and not parts.fragment and
             unquote(parts.path.rsplit('/',1)[-1])==p.get('filename') and p['filename'].endswith('.whl'),'official wheel location')
        need(parts.hostname==('download-r2.pytorch.org' if name=='torch' else 'files.pythonhosted.org'),'package publisher')
        need(digest(p.get('sha256')) and type(p.get('size_bytes')) is int and 0<p['size_bytes']<268435456,'wheel identity')
        seen[name]=p
    need(seen['pip']['version']=='25.0.1' and seen['torch']['version']=='2.10.0+cpu' and
         seen['numpy']['version']=='2.3.5' and seen['transformers']['version']=='4.40.1','fixed package versions')
    need(value.get('runtime_package_count')==25 and type(value['runtime_package_count']) is int and
         value.get('provisioning_tool_count')==1 and type(value['provisioning_tool_count']) is int,'package counts')
    runtime=sum(p['size_bytes'] for p in packages if p['role']=='runtime')
    total=sum(p['size_bytes'] for p in packages)
    need(runtime==236621932==value.get('runtime_wheel_bytes') and total==238463458==value.get('total_wheel_bytes_with_pip') and
         total<=value.get('wheel_transfer_budget_bytes',0)==268435456,'compressed wheel budget')
    return value


def selected(lock,role):
    need(role in ('bootstrap','runtime'),'install role')
    return {p['name']:p for p in lock['packages'] if (p['role']=='provisioning-tool')==(role=='bootstrap')}


def validate_requirements(raw,lock,role):
    need(type(raw) is bytes and len(raw)<32768,'requirements bound')
    lines=[s.strip() for s in raw.decode('ascii').splitlines() if s.strip() and not s.lstrip().startswith('#')]
    expected=[p['name']+' @ '+p['url']+' --hash=sha256:'+p['sha256'] for p in selected(lock,role).values()]
    need(lines==expected,'exact direct-wheel hashed requirements')
    return True


def validate_report(value,lock,role):
    need(type(value) is dict and set(value)=={'version','pip_version','install','environment'} and value['version']=='1','report schema')
    need(type(value['pip_version']) is str and re.fullmatch(r'\d+(\.\d+){1,3}',value['pip_version']) is not None,'report pip version')
    if role=='runtime': need(value['pip_version']=='25.0.1','pinned active pip')
    expected=selected(lock,role)
    env=value['environment']
    need(type(env) is dict and all(type(k) is str and type(v) is str for k,v in env.items()),'report environment')
    for key,want in dict(implementation_name='cpython',implementation_version='3.12.15',os_name='posix',
        platform_machine='x86_64',platform_system='Linux',python_full_version='3.12.15',
        platform_python_implementation='CPython',python_version='3.12',sys_platform='linux').items():
        need(env.get(key)==want,'report environment '+key)
    installs=value['install'];need(type(installs) is list and len(installs)==len(expected),'installed count')
    seen=set()
    for item in installs:
        need(type(item) is dict and set(item) in (
            {'download_info','is_direct','is_yanked','requested','metadata'},
            {'download_info','is_direct','is_yanked','requested','metadata','requested_extras'}),'report item')
        need(item['is_direct'] is True and item['requested'] is True and item['is_yanked'] is False and
             item.get('requested_extras',[])==[],'direct non-yanked explicit wheel')
        meta=item['metadata'];need(type(meta) is dict,'package metadata')
        name=normalized(meta.get('name'));need(name in expected and name not in seen,'unexpected/duplicate package')
        pin=expected[name];seen.add(name)
        need(meta.get('version')==pin['version'],'installed version')
        info=item['download_info'];need(type(info) is dict and set(info)=={'url','archive_info'} and info['url']==pin['url'],'installed wheel URL')
        archive=info['archive_info']
        need(type(archive) is dict and set(archive) in ({'hashes'},{'hash','hashes'}) and
             archive.get('hashes')=={'sha256':pin['sha256']} and
             archive.get('hash','sha256='+pin['sha256'])=='sha256='+pin['sha256'],'installed wheel SHA256')
    need(seen==set(expected),'complete install report')
    return True


def validate_inventory(value,lock):
    need(type(value) is dict and set(value)=={'schema','python','private_venv','packages'} and
         type(value['schema']) is int and value['schema']==1 and value['python']=='3.12.15' and value['private_venv'] is True,'inventory identity')
    need(type(value['packages']) is list and len(value['packages'])==26,'inventory count')
    expected={p['name']:p for p in lock['packages']};seen=set()
    for item in value['packages']:
        need(type(item) is dict and set(item)=={'name','version','inside_venv'},'inventory fields')
        name=normalized(item['name']);need(name in expected and name not in seen and
            item['version']==expected[name]['version'] and item['inside_venv'] is True,'installed private package')
        seen.add(name)
    need(seen==set(expected),'complete installed package inventory')
    return True
