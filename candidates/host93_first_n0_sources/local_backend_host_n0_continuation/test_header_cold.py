"""Temporary synthetic header data and callbacks exercise the exact projected probe."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import copy,hashlib,json,os,stat,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
def rejects(fn,why):
    try:fn()
    except (ValueError,KeyError,TypeError,OSError):return
    raise ValueError('missing rejection: '+why)
SYNTHETIC=b'/* cold-only synthetic FlexLexer bytes; never compiled */\n'
class FS:
    def fresh_directory(self,p):p.mkdir(mode=0o700)
    def identity(self,p,cap):
        p=Path(p);s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=cap,'finite regular synthetic fixture')
        return {**pin(p.read_bytes()),'mode':oct(stat.S_IMODE(s.st_mode))}
    def checked_read(self,p,size,sha):
        value=self.identity(p,size);need(value['bytes']==size and value['sha256']==sha,'synthetic read identity');return Path(p).read_bytes()
    def tree_inventory(self,p,*args):
        entries={};files=0
        for f in sorted(Path(p).rglob('*')):
            relative=str(f.relative_to(p));s=f.lstat();need(not stat.S_ISLNK(s.st_mode),'no synthetic tree symlink')
            if f.is_dir():entries[relative]={'kind':'directory','mode':oct(stat.S_IMODE(s.st_mode))}
            else:entries[relative]={'kind':'regular',**self.identity(f,4*1024**2)};files+=1
        return {'entries':entries,'files':files}
fs=FS()
with mock.patch.object(header,'SIZE',len(SYNTHETIC)),mock.patch.object(header,'SHA',hashlib.sha256(SYNTHETIC).hexdigest()):
    with tempfile.TemporaryDirectory(dir=ROOT) as t:
        root=Path(t);source=root/'source.h';source.write_bytes(SYNTHETIC);out=root/'new'
        header.stage(SYNTHETIC,source,out)
        need((out/'include/FlexLexer.h').read_bytes()==SYNTHETIC,'exact synthetic bytes')
        need(fs.identity(out/'include/FlexLexer.h',len(SYNTHETIC))['mode']=='0o600','fixed private header mode')
        receipt=json.loads((out/'RECEIPT.json').read_bytes());need(receipt==header.expected(source) and receipt['network_started'] is False and receipt['native_qualification_inherited'] is False,'truthful cached receipt')
        checks.append('synthetic_cached_stage_exact_private_bytes_and_truthful_receipt')
        for raw in (b'',SYNTHETIC[:-1],bytes([SYNTHETIC[0]^1])+SYNTHETIC[1:],bytearray(SYNTHETIC)):
            target=root/'bad';rejects(lambda:header.stage(raw,source,target),'bad header');need(not target.exists(),'bad header refused before output')
        for dest in (out,Path('relative-header'),root/'..'/'escape'):
            rejects(lambda:header.stage(SYNTHETIC,source,dest),'bad destination')
        link=root/'linked';link.symlink_to(out,target_is_directory=True);rejects(lambda:header.stage(SYNTHETIC,source,link),'symlink destination')
        checks.append('bad_bytes_relative_parent_collision_symlink_destinations_rejected')
        with mock.patch.object(header.os,'write',return_value=0):rejects(lambda:header.stage(SYNTHETIC,source,root/'short'),'incomplete write')
        checks.append('short_data_write_rejected')
    def probe_case(bad=None):
        with tempfile.TemporaryDirectory(dir=ROOT) as t:
            work=Path(t);source=work/'source.h';source.write_bytes(SYNTHETIC);source.chmod(0o600);c=make_ci();c.HEADER_SIZE=len(SYNTHETIC);c.HEADER_SHA=pin(SYNTHETIC)['sha256'];c.host_identities=lambda fs:{}
            def checked(path,expected,*args):
                if Path(path)==Path(c.__file__):need(expected==adapter.CI_PIN,'original ci fixed pin');return CI_RAW
                raw=Path(path).read_bytes();need(pin(raw)==expected,'helper self pin');return raw
            g=types.SimpleNamespace(checked=checked,pin=pin,need=need)
            raw=(ROOT/'cached_flex_header.py').read_bytes();proof=header.bind(g,adapter,c,source,raw)
            need(proof['inverse_exact'] is True and proof['substitutions']==3,'three inverse header anchors')
            calls=[]
            if bad=='source_drift':source.write_bytes(SYNTHETIC[:-1]+b'X')
            if bad=='source_symlink':source.unlink();source.symlink_to(work/'absent.h')
            def callback(name,argv,cwd,env,bound):
                calls.append(name)
                if name==header.PHASE:
                    need(argv[:5]==['/usr/bin/python3','-I','-S','-B','-c'] and 'data-only cached header' in argv[5],'data-only fixed child argv')
                    need(bound==c.LOCAL_HEADER_LIMITS and bound['total_seconds']==60 and bound['work_seconds']==40,'bounded cached phase')
                    header.stage(SYNTHETIC,source,work/'flex-header')
                    if bad=='receipt':(work/'flex-header/RECEIPT.json').write_text('{}')
                    if bad=='stage_extra':(work/'flex-header/extra').write_bytes(b'bad')
                else:
                    need(name=='flex_header_compile','no network header acquisition')
                    expected=['/usr/bin/g++','-std=c++17','-g0','-I'+str(work/'flex-header/include'),'-MMD','-MF','probe.d','-MT','probe.o','-c','probe.cpp','-o','probe.o']
                    need(argv==expected and bound==c.PROBE_LIMITS,'unchanged original g++ compile only contract')
                    c.write_fixture(cwd/'probe.o',b'' if bad=='empty_object' else b'SYNTHETIC OBJECT: never executed')
                    c.write_fixture(cwd/'probe.d',('probe.o: probe.cpp '+str(work/'flex-header/include/FlexLexer.h')+'\n').encode())
                    if bad=='object_mode':(cwd/'probe.o').chmod(0o700)
                    if bad=='dependency':(cwd/'probe.d').write_text('probe.o: probe.cpp /usr/include/FlexLexer.h\n')
                    if bad=='fixture':(cwd/'probe.cpp').write_bytes(b'changed fixture')
                    if bad=='compile_extra':(cwd/'extra').write_bytes(b'bad')
                    if bad=='header_after':(work/'flex-header/include/FlexLexer.h').write_bytes(b'drift')
                return {'record':{'exit_code':1 if bad=='phase_failure' else 0,'cleanup_confirmed':bad!='cleanup'},'raw_log':b'','usage':{'synthetic':True}}
            run=lambda:c.qualify_flex_header(fs,{}, {},REPO,work,callback,{})
            if bad:
                rejects(run,bad)
                if bad in ('source_drift','source_symlink'):need(calls==[],'header source fails before callback')
                if bad in ('receipt','stage_extra','phase_failure','cleanup'):need(calls==[header.PHASE],'bad cached stage stops before compile')
            else:
                result=run();need(calls==[header.PHASE,'flex_header_compile'],'fixed two phases')
                need(result['compiled_not_linked_or_executed'] is True and result['cached_stage_usage']=={'synthetic':True} and 'acquisition_usage' not in result,'truthful cached proof and unchanged compile validation')
    probe_case();checks.append('exact_projected_cached_header_then_original_gpp_depfile_positive')
    for bad in ('source_drift','source_symlink','receipt','stage_extra','phase_failure','cleanup','empty_object','object_mode','dependency','fixture','compile_extra','header_after'):
        probe_case(bad);checks.append(bad+'_rejected_without_later_callbacks')
print(json.dumps({'status':'PASS_CACHED_HEADER_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'real_header_copied':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_header_cold.py','tests':len(checks),'checks':checks})
