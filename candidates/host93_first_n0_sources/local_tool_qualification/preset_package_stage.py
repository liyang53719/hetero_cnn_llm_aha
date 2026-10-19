"""Fixed preset-package admission. No acquisition/native/process API."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B')
if __name__=='__main__':raise SystemExit('same-buffer reviewed caller required')
from pathlib import Path
import os
import stat

PHASE='local_dependencies_accept_cached'
BOOTSTRAP_PIN={'bytes':25509,'sha256':'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'}


def verify_preset(g,s,root,receipt_pin):
    root=g.clean(root);path=root/'ACQUISITION.json';raw=g.checked(path,receipt_pin,65536)
    receipt,_=g.receipt_postflight(s,root,raw)
    for package in s['pins']['packages']:
        file=root/package['deb_filename'];info=file.lstat()
        g.need(info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'single-link preset package0600')
        g.checked(file,{'bytes':package['deb_bytes'],'sha256':package['deb_sha256']},fixed_leaf=package['deb_filename'])
    g.need(g.checked(path,receipt_pin,65536)==raw,'preset source receipt changed')
    return receipt


def accept(g,repo,binding_raw,binding_pin,source_root,receipt_pin):
    """For one original bounded Python child, with fresh exit/cleanup later."""
    g.checked(Path(g.__file__),BOOTSTRAP_PIN)
    b=g.binding(binding_raw,binding_pin,repo);s=g.load_sources(repo);p=g.paths(b);source=g.clean(source_root)
    g.need(not source.is_relative_to(p['work']) and not p['work'].is_relative_to(source),'preset source disjoint from new work')
    g.need(not os.path.lexists(p['work']),'fresh preset acceptance work only')
    verify_preset(g,s,source,receipt_pin)
    identities={item['deb_filename']:{'bytes':item['deb_bytes'],'sha256':item['deb_sha256']} for item in s['pins']['packages']}
    identities['ACQUISITION.json']=receipt_pin
    s['fs'].fresh_directory(p['work']);s['fs'].fresh_directory(p['packages'])
    for name,pin in identities.items():s['fs'].copy_member(source/name,p['packages'],name,pin,0o600)
    verify_preset(g,s,source,receipt_pin);verify_preset(g,s,p['packages'],receipt_pin)
    for name,pin in g.SOURCE_FILES.items():g.checked(Path(repo)/name,pin)
    return {'schema':'LOCAL_PRESET_FIVE_BYTE_ACCEPTANCE_V1','binding':binding_pin,'phase':PHASE,'receipt':receipt_pin,
            'files':identities,'package_count':5,'output_file_count':6,'network_acquisition_claimed':False,
            'native_qualification':'NOT_RUN','terminal_success':False,'outer_exit_cleanup_pending':True}


def stage(g,adapter,repo,binding_raw,binding_pin,phase,receipt_pin,acceptance_raw,acceptance_pin):
    """Original stage_data; only accepted phase-name differs from acquisition."""
    g.need(type(acceptance_raw) is bytes and len(acceptance_raw)<=65536 and g.pin(acceptance_raw)==acceptance_pin,'same-buffer preset acceptance evidence')
    evidence=g.decode(acceptance_raw)
    g.need(evidence['schema']=='LOCAL_PRESET_FIVE_BYTE_ACCEPTANCE_V1' and evidence['binding']==binding_pin and
           evidence['phase']==PHASE and evidence['receipt']==receipt_pin and evidence['network_acquisition_claimed'] is False and
           evidence['native_qualification']=='NOT_RUN' and evidence['terminal_success'] is False and
           evidence['outer_exit_cleanup_pending'] is True and evidence['package_count']==5 and evidence['output_file_count']==6,'exact preset acceptance scope')
    g.need(type(phase) is dict and set(phase)=={'name','record'} and phase['name']==PHASE and
           type(phase['record']['exit_code']) is int and phase['record']['exit_code']==0 and phase['record']['cleanup_confirmed'] is True,'new preset phase exit0 and cleanup required')
    sources=g.load_sources(repo)
    expected={item['deb_filename']:{'bytes':item['deb_bytes'],'sha256':item['deb_sha256']} for item in sources['pins']['packages']}
    expected['ACQUISITION.json']=receipt_pin;g.need(evidence['files']==expected,'exact preset acceptance six identities')
    raw=g.checked(Path(g.__file__),BOOTSTRAP_PIN);ns=dict(g.__dict__)
    _,proof=adapter.exact_function(g,raw,'verify_acquisition',ns,((b"'local_dependencies_acquire'",b"'local_dependencies_accept_cached'"),))
    function,stage_proof=adapter.exact_function(g,raw,'stage_data',ns)
    result=function(repo,binding_raw,binding_pin,phase,receipt_pin)
    return result,{'preset_phase_projection':proof,'stage_data':stage_proof,'original_download_cleanup_claimed':False}
