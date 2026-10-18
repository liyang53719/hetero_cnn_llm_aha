"""Pure source/mock and tiny-copy checks. No make/compiler/backend/subprocess execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Cold tests require -I -S -B before project load.')
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import types
from unittest import mock
os.umask(0o077)
HERE=Path(__file__).absolute().parent
RUNNER_BYTES=24603
RUNNER_SHA='a5df00c76cd5482dc758ed637c3dbb886e44b86de5ede5143c6e36f88a0478ef'

def require(ok,why):
    if not ok:raise ValueError(why)

def pinned(path,size,sha):
    require(path.is_absolute() and '..' not in path.parts and not any(x.is_symlink() for x in (path,*path.parents)),'cold safe absolute source')
    with path.open('rb') as f:
        before=os.fstat(f.fileno());require(stat.S_ISREG(before.st_mode) and before.st_size==size,'cold fixed source size')
        raw=f.read(size+1);after=os.fstat(f.fileno())
    key=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    require(len(raw)==size and hashlib.sha256(raw).hexdigest()==sha and key(before)==key(after)==key(path.stat()),'cold fixed same-buffer SHA')
    return raw

raw=pinned(HERE/'run_seqnum_rebuild.py',RUNNER_BYTES,RUNNER_SHA)
g=types.ModuleType('verified_seqnum_rebuild_cold');g.__file__=str(HERE/'run_seqnum_rebuild.py');g.__verified_runner_pin__={'path':g.__file__,'bytes':RUNNER_BYTES,'sha256':RUNNER_SHA}
exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo',required=True,help='Explicit absolute repository containing the pinned published support sources; cold-only.')
args=parser.parse_args();repo=Path(args.repo)
require(repo.is_absolute() and '..' not in repo.parts,'--repo explicit absolute without traversal')
PRODUCTION_PLAN=g.load_plan()
g.validate_contract(PRODUCTION_PLAN)
require(PRODUCTION_PLAN['base_build_review'] is None and PRODUCTION_PLAN['host_programs'] is None and PRODUCTION_PLAN['observed_failure_review'] is None,'production actuals must remain PENDING')
p=copy.deepcopy(PRODUCTION_PLAN)
# Cold-only source resolution; no actual root, argv, review or tool binding is supplied.
g.SUPPORT_PIN=dict(g.SUPPORT_PIN,path=str(repo/p['publication']['support_repo_relative']))
p['support_pin']=dict(g.SUPPORT_PIN)
for row in p['published_sources'].values():
    require(not row['repo_relative'].startswith('/') and '..' not in Path(row['repo_relative']).parts,'safe relative source dependency')
    row['path']=str(repo/row['repo_relative'])
for key,name in [('original_source','ORIGINAL_V3ProtectLib.cpp'),('derived_source','DERIVED_V3ProtectLib.cpp'),('patch_record','PATCH.json')]:
    p[key]=dict(p[key],path=str(HERE/name))
support=g.support_module()
sp=p['publication']['support_plan']
require(support.fixed({'path':str(repo/sp['repo_relative']),'bytes':sp['bytes'],'sha256':sp['sha256']}) is not None,'published support plan fixed identity')
for row in p['published_sources'].values():support.fixed(row)
count=0

def test(name,fn):
    global count
    fn();count+=1;print('PASS '+name)

def rejects(fn,part,errors=(ValueError,KeyError,TypeError,OSError)):
    try:fn()
    except errors as e:
        require(part in str(e),'wrong refusal '+str(e));return
    raise ValueError('missing rejection '+part)

def pin(path):
    b=path.read_bytes();return {'path':str(path),'bytes':len(b),'sha256':g.digest(b)}

def write(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o600);return pin(path)

test('fixed_contract',lambda:g.validate_contract(p))
def production_pending():
    old=g.SUPPORT_PIN
    try:
        g.SUPPORT_PIN=PRODUCTION_PLAN['support_pin']
        with mock.patch.object(g,'support_module',side_effect=RuntimeError('no support')) as load,mock.patch.object(g.subprocess,'Popen',side_effect=RuntimeError('no spawn')) as spawn,mock.patch.object(g.os,'mkdir',side_effect=RuntimeError('no output')) as mkdir:
            rejects(lambda:g.execute(PRODUCTION_PLAN,0,None),'PENDING')
            load.assert_not_called();spawn.assert_not_called();mkdir.assert_not_called()
    finally:g.SUPPORT_PIN=old
test('true_production_default_pending_before_cold_mapping',production_pending)
test('no_assert_or_importlib',lambda:require(not any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(raw))) and b'importlib' not in raw and b'shell=True' not in raw,'unsafe source'))
test('unique_patch_inverse',lambda:g.checked_patch(support,p))
test('derived_constructor_init_exact',lambda:require(support.fixed(p['derived_source']).count(b'(scopep__V), m_seqnum{0} {}\\n')==1,'derived constructor'))
test('skip_exactly_three',lambda:require(tuple(p['skip_copy'])==g.SKIP and len(g.SKIP)==3,'skip3'))

def missing_and_bad_acceptance():
    with mock.patch.object(g,'support_module',side_effect=RuntimeError('support forbidden')) as load, mock.patch.object(g.subprocess,'Popen',side_effect=RuntimeError('spawn forbidden')) as spawn, mock.patch.object(g.os,'mkdir',side_effect=RuntimeError('output forbidden')) as mkdir:
        rejects(lambda:g.execute(p,0,None),'PENDING')
        rejects(lambda:g.execute(p,0,{}),'acceptance pin shape')
        load.assert_not_called();spawn.assert_not_called();mkdir.assert_not_called()
test('real_default_pending_before_support_copy_spawn_output',missing_and_bad_acceptance)

def bootstrap_bad_size_sha():
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'source.py';good=write(path,b'raise RuntimeError("NEVER_COMPILE")\n')
        for item in (dict(good,bytes=good['bytes']+1),dict(good,sha256='0'*64)):
            with mock.patch('builtins.compile',side_effect=RuntimeError('compile forbidden')) as compile_mock:
                rejects(lambda:g.initial_read(item),'bootstrap');compile_mock.assert_not_called()
        require(g.initial_read(good)==path.read_bytes(),'same buffer')
test('corrupt_size_SHA_before_compile',bootstrap_bad_size_sha)

def corrupt_actual_review():
    with tempfile.TemporaryDirectory() as td:
        f=Path(td)/'acceptance.json';item=write(f,b'{}\n')
        with mock.patch.object(g,'support_module',side_effect=RuntimeError('support forbidden')) as load,mock.patch.object(g.subprocess,'Popen',side_effect=RuntimeError('spawn forbidden')) as pop:
            rejects(lambda:g.execute(p,0,dict(item,bytes=item['bytes']+1)),'bootstrap')
            rejects(lambda:g.execute(p,0,dict(item,sha256='0'*64)),'bootstrap')
            rejects(lambda:g.execute(p,0,item),'binding shape')
            load.assert_not_called();pop.assert_not_called()
test('corrupt_review_before_support_spawn',corrupt_actual_review)

def source_symlink_reject():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td);a=write(r/'real',b'x');(r/'link').symlink_to(r/'real')
        rejects(lambda:g.initial_read(dict(a,path=str(r/'link'))),'Too many levels')
test('nofollow_bootstrap_source',source_symlink_reject)

def tiny_copy():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td);r.chmod(0o700);src=r/'src';dst=r/'dst';src.mkdir(mode=0o700);dst.mkdir(mode=0o700)
        a=src/'a';write(a,b'x'*5000000);os.utime(a,ns=(1100000000000000000,1100000000000000123))
        row={'kind':'regular',**support.identity(a,6000000)}
        receipt=g.copy_preserved_member(support,a,dst/'a',row)
        require(receipt['preserved_mtime_ns']==a.stat().st_mtime_ns==(dst/'a').stat().st_mtime_ns,'copy mtime')
        require(a.stat().st_ino!=(dst/'a').stat().st_ino and (dst/'a').stat().st_nlink==1,'no hardlink')
        rejects(lambda:g.copy_preserved_member(support,a,dst/'a',row),'File exists')
        rejects(lambda:g.copy_preserved_member(support,a,dst/'bad',dict(row,sha256='0'*64)),'exact source bytes/SHA')
        rejects(lambda:g.copy_preserved_member(support,a,dst/'badsize',dict(row,bytes=row['bytes']+1)),'source size/mode')
test('bounded_stream_copy_preserves_mtime_nohardlink_badpins',tiny_copy)

def tiny_materialization():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td);r.chmod(0o700);src=r/'original';src.mkdir(mode=0o700)
        for n in ['verilator/src/obj_opt','verilator/bin','home','tmp']: (src/n).mkdir(mode=0o700,parents=True)
        write(src/g.PATCH_MEMBER,support.fixed(p['original_source']))
        for name in g.SKIP:write(src/name,b'old never copied\n')
        write(src/'verilator/src/obj_opt/Other.o',b'old object identity\n')
        os.utime(src/'verilator/src/obj_opt/Other.o',ns=(1100000000000000000,1100000000000000000))
        before=support.tree_inventory(src,1000000)
        q=copy.deepcopy(p);q['build_root']=str(r/'fresh')
        receipt=g.materialize(support,q,before)
        fresh=support.tree_inventory(q['build_root'],1000000)
        require(fresh==g.expected_copied_tree(q,before),'exact synthetic copied tree')
        require(support.tree_inventory(src,1000000)==before,'synthetic original unchanged')
        require(all(not (r/'fresh'/x).exists() for x in g.SKIP),'missing old outputs')
        require(receipt['hardlinks_created'] is False and len(receipt['copied_files'])==2,'exact copy receipt')
        require((r/'fresh'/g.PATCH_MEMBER).stat().st_mtime_ns>1100000000000000000,'natural current patched mtime')
        require((r/'fresh'/'verilator/src/obj_opt/Other.o').stat().st_mtime_ns==1100000000000000000,'retained original object mtime')
        rejects(lambda:g.materialize(support,q,before),'fresh destination')
test('synthetic_skip3_copy_patch_original_preserved',tiny_materialization)

def fixed_projection():
    sup,obs=support.projected_sources(p,'derived_incremental')
    require({k:{'bytes':len(b),'sha256':g.digest(b)} for k,b in [('supervisor',sup),('observation',obs)]}==p['projection_pins'],'exact projection')
    n=g.projected_runner(support,p,HERE/'NEVER_CREATED')
    require(all(k in n for k in ['bounded','group_state','observe_exit','sample_leader','usage']),'original functions')
    require(b'os.WNOWAIT' in sup and b'signal_sent_before_reap' in sup and b'cleanup_budget_seconds=5' in sup,'original lifecycle')
    require(b"state['count']<902" in obs,'fixed sampler rows')
    for label,wanted in [('supervisor',support.FUNCTIONS),('observation',support.OBSERVERS)]:
        original=support.project_functions(support.fixed(p['published_sources'][label]),p['published_sources'][label],wanted)
        require(tuple(original)==wanted,'original raw fragment pins')
test('same_original_lifecycle_observation_raw_pins',fixed_projection)

def bad_projection():
    q=copy.deepcopy(p);q['projection_pins']['supervisor']['sha256']='0'*64
    with mock.patch('builtins.compile',wraps=compile) as cp:
        rejects(lambda:g.projected_runner(support,q,HERE/'NEVER_CREATED'),'projected fixed buffer')
        require(not any(x.args[1]=='fixed_five_derived_WNOWAIT' for x in cp.call_args_list),'corrupt projection compiled')
test('bad_projection_precompile_reject',bad_projection)
GOOD=b'/usr/bin/g++ -O3 -c ../V3ProtectLib.cpp -o V3ProtectLib.o\n/usr/bin/g++ -o ../../bin/verilator_bin V3ProtectLib.o Other.o\n'
test('exact_one_unit_link_log',lambda:require(g.compilation_report(GOOD)['only_V3ProtectLib_compile_and_one_link'],'intended log'))
test('additional_compile_logged_and_rejected',lambda:require(not g.compilation_report(GOOD+b'g++ -c Other.cpp -o Other.o\n')['only_V3ProtectLib_compile_and_one_link'],'unexpected compile'))
test('missing_link_rejected',lambda:require(not g.compilation_report(GOOD.splitlines(keepends=True)[0])['only_V3ProtectLib_compile_and_one_link'],'missing link'))
test('wrong_unit_rejected',lambda:require(not g.compilation_report(GOOD.replace(b'V3ProtectLib.cpp',b'Other.cpp'))['only_V3ProtectLib_compile_and_one_link'],'wrong unit'))

def source_review_fake_only():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)
        summary={'verdict':'SOURCE_GO_DERIVED_SEQNUM_INCREMENTAL_ONLY','candidate_manifest':pin(HERE/'MANIFEST.json')}
        sp=write(r/'SUMMARY.json',(json.dumps(summary)+'\n').encode())
        mp=write(r/'MANIFEST.json',(json.dumps({'files':{'SUMMARY.json':{k:sp[k] for k in ('bytes','sha256')}}})+'\n').encode())
        binding={'manifest':mp,'summary':sp,'summary_claims':{'verdict':summary['verdict']}}
        bp=write(r/'binding.json',(json.dumps(binding)+'\n').encode())
        require(g.pending_gate(p,bp)==binding,'synthetic review binding shape')
        # No execute() call for this artificial accepted shape. Never native authorization.
        binding['summary_claims']['verdict']='PASS_ANYTHING'
        bp=write(r/'binding.json',(json.dumps(binding)+'\n').encode())
        rejects(lambda:g.pending_gate(p,bp),'exact source-only review verdict')
test('synthetic_source_review_exact_manifest_no_execute',source_review_fake_only)
print(json.dumps({'status':'PASS_SOURCE_MOCK_TINY_COPY_ONLY','tests':count,'native_executed':False,'actual_build_tree_copied':False,'actual_review':'PENDING','synthetic_review_is_not_authorization':True},sort_keys=True))
