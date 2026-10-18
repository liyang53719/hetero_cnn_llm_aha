"""Reviewed derived-source incremental rebuild. No actual work without exact review binding."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B before any project source is loaded.')
if __name__ == '__main__':
    raise SystemExit('Use the separately pinned same-buffer loader.')
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import time
import types

HERE = Path(__file__).absolute().parent
PLAN_BYTES = 14930
PLAN_SHA = 'dd6a89e327105be61837538cf68bdbdb854ba4239de84ff9aace806e9898c6b8'
SUPPORT_PIN = {'path': '/UNBOUND/repo/development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py', 'bytes': 28551, 'sha256': '8f1560c5f0a8e78a991f98c30031cbd18df220e3eb82cf2c78de4ec0438bdafb'}
ORIGINAL = '/UNBOUND/original_build'
FRESH = '/UNBOUND/derived_build'
EVIDENCE = '/UNBOUND/derived_evidence'
PATCH_MEMBER = 'verilator/src/V3ProtectLib.cpp'
SKIP = ('verilator/src/obj_opt/V3ProtectLib.o', 'verilator/src/obj_opt/V3ProtectLib.d', 'verilator/bin/verilator_bin')
DEADLINE_PHASE = 'unarmed'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def initial_read(pin):
    path = Path(pin['path'])
    size = pin['bytes']
    require(path.is_absolute() and '..' not in path.parts and type(size) is int and 0 <= size <= 4*1024**2, 'bounded absolute bootstrap input')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = newer
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'bootstrap regular size')
            pieces = []
            count = 0
            while count <= size:
                part = os.read(fd, min(65536, size + 1 - count))
                if not part:
                    break
                pieces.append(part)
                count += len(part)
            raw = b''.join(pieces)
            key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(len(raw) == size and digest(raw) == pin['sha256'] and key(before) == key(os.fstat(fd)) == key(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'bootstrap raw identity')
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def support_module():
    raw = initial_read(SUPPORT_PIN)
    module = types.ModuleType('fixed_build_support_for_seqnum')
    module.__file__ = SUPPORT_PIN['path']
    exec(compile(raw, SUPPORT_PIN['path'], 'exec', dont_inherit=True), module.__dict__)
    return module


def load_plan():
    return json.loads(initial_read({'path': str(HERE/'PLAN.json'), 'bytes': PLAN_BYTES, 'sha256': PLAN_SHA}))


def validate_contract(plan):
    require(plan['parent_only_actual'] is True and plan['base_root'] == ORIGINAL and plan['build_root'] == FRESH, 'fixed roots and parent')
    require(tuple(plan['skip_copy']) == SKIP and plan['patch_member'] == PATCH_MEMBER, 'exact skip3 and patch member')
    require(plan['support_pin'] == SUPPORT_PIN and plan['review_required'] is True, 'fixed support and source review')
    c = plan['phases']['derived_incremental']
    expected = {'argv': ['/usr/bin/make', '-C', FRESH+'/verilator/src', '-j1', 'opt', 'SHELL=/bin/sh', 'MAKE=/usr/bin/make', 'BEAR=', 'BEAR_OBJ_OPT=', 'OBJCACHE=', 'VERILATOR_NO_OPT_BUILD=0', 'VL_NOOPT=0', 'VL_DEBUG=', 'VL_VLCOV='], 'cwd': FRESH+'/verilator', 'evidence_root': EVIDENCE, 'total_seconds': 900, 'preflight_seconds': 180, 'work_max_seconds': 600, 'work_latest_offset_seconds': 780, 'cleanup_seconds': 5, 'postflight_reserved_seconds': 115, 'cpu_seconds': 600, 'as_bytes': 4*1024**3, 'fsize_bytes': 1024**3, 'tree_bytes': 768*1024**2, 'log_bytes': 1024**2, 'sample_rows': 902, 'file_count': 1024, 'entry_count': 2048}
    require(c == expected, 'fixed single incremental phase contract')
    require(plan['environment'] == plan['original_environment'] | {'HOME': FRESH+'/home', 'TMPDIR': FRESH+'/tmp', 'VERILATOR_ROOT': FRESH+'/verilator'}, 'only fresh writable environment roots')


def pending_gate(plan, acceptance):
    validate_contract(plan)
    require(type(acceptance) is dict, 'source review acceptance PENDING')
    require(set(acceptance) == {'path', 'bytes', 'sha256'}, 'fixed external acceptance pin shape')
    return verify_source_review(acceptance)


def verify_source_review(acceptance):
    binding = json.loads(initial_read(acceptance))
    require(type(binding) is dict and set(binding) == {'manifest', 'summary', 'summary_claims'}, 'source review binding shape')
    claims = binding['summary_claims']
    require(type(claims) is dict and claims.get('verdict') == 'SOURCE_GO_DERIVED_SEQNUM_INCREMENTAL_ONLY', 'exact source-only review verdict')
    review_manifest = json.loads(initial_read(binding['manifest']))
    summary = json.loads(initial_read(binding['summary']))
    names = review_manifest.get('files')
    if type(names) is dict:
        row = names.get('SUMMARY.json')
    elif type(names) is list:
        found = [r for r in names if r.get('path') == 'SUMMARY.json']
        require(len(found) == 1, 'unique reviewed summary')
        row = found[0]
    else:
        raise ValueError('review manifest member shape')
    require(type(row) is dict and row.get('bytes') == binding['summary']['bytes'] and row.get('sha256') == binding['summary']['sha256'], 'review summary manifest binding')
    require(all(summary.get(k) == v for k,v in claims.items()), 'exact source review claims')
    candidate = summary.get('candidate_manifest')
    require(type(candidate) is dict and candidate.get('path') == str(HERE/'MANIFEST.json'), 'source review exact candidate manifest path')
    manifest = json.loads(initial_read(candidate))
    rows = manifest['files']
    require({x['path'] for x in rows} == {'PLAN.json', 'PATCH.json', 'ORIGINAL_V3ProtectLib.cpp', 'DERIVED_V3ProtectLib.cpp', 'run_seqnum_rebuild.py', 'load_seqnum_rebuild.py', 'test_seqnum_rebuild_cold.py', 'README.md'}, 'reviewed exact source file set')
    require(len(rows) == 8, 'unique manifest members')
    for row in rows:
        initial_read({'path': str(HERE/row['path']), 'bytes': row['bytes'], 'sha256': row['sha256']})
    return binding


def checked_patch(support, plan):
    original = support.fixed(plan['original_source'])
    derived = support.fixed(plan['derived_source'])
    patch = json.loads(support.fixed(plan['patch_record']))
    old = patch['old_exact_utf8'].encode()
    new = patch['new_exact_utf8'].encode()
    require(original.count(old) == 1 and derived == original.replace(old, new, 1), 'unique one-line derived patch')
    require(derived.count(new) == 1 and derived.replace(new, old, 1) == original, 'exact patch reverse')
    require(patch['official_original'] == {k: plan['original_source'][k] for k in ('bytes','sha256')} and patch['derived'] == {k: plan['derived_source'][k] for k in ('bytes','sha256')}, 'paired patch identities')
    return original, derived


def verify_inputs(support, plan, acceptance):
    initial_read({'path': str(HERE/'PLAN.json'), 'bytes': PLAN_BYTES, 'sha256': PLAN_SHA})
    initial_read(SUPPORT_PIN)
    support.fixed(globals()['__verified_runner_pin__'])
    review = verify_source_review(acceptance)
    base = support.verify_review(plan['base_build_review'])
    require(base['verdict'] == 'PASS_ACTUAL_FIXED_OPTIMIZED_BACKEND_BUILD_ONLY' and base['outer_exit'] == 0 and base['cleanup_confirmed'] is True, 'accepted original build')
    require(base['build_tree_inventory_sha256'] == plan['base_tree']['sha256'], 'original reviewed inventory')
    tree = json.loads(support.fixed(plan['base_tree']))
    require(tree['root'] == ORIGINAL and tree['files'] == 929 and tree['bytes'] == 494646584, 'original929 tree scope')
    require(support.tree_inventory(ORIGINAL, 768*1024**2, 1024, 2048, 1024**3) == tree, 'original complete tree drift')
    require(tree['entries'][PATCH_MEMBER] == dict(kind='regular', mode='0o600', **{k:plan['original_source'][k] for k in ('bytes','sha256')}), 'original patch member identity')
    checked_patch(support, plan)
    for invoked, pin in plan['host_programs'].items():
        require(os.path.realpath(invoked) == pin['path'], 'host program resolution changed')
        require(support.identity(pin['path'], 64*1024**2) == {k:pin[k] for k in ('bytes','sha256','mode')}, 'host program identity drift')
    source_plan = json.loads(support.fixed(plan['original_build_plan']))
    for row in source_plan['dependency_members']:
        require(support.identity(row['source'], row['bytes']) == {'bytes':row['bytes'],'sha256':row['sha256'],'mode':'0o600'}, 'read-only original dependency stage drift')
    support.fixed(source_plan['stage_report'])
    for pin in plan['published_sources'].values():
        support.fixed(pin)
    support.verify_review(plan['observed_failure_review'])
    support.fixed(plan['observed_generated_wrapper'])
    return tree, review


def copy_preserved_member(support, source, target, row):
    require(row['kind'] == 'regular' and row['mode'] in ('0o600','0o700'), 'copy regular expected mode')
    parent, fd, before = support.regular_fd(source)
    out_parent = support.directory_fd(Path(target).parent)
    out = None
    try:
        require(before.st_size == row['bytes'] and oct(stat.S_IMODE(before.st_mode)) == row['mode'], 'copy source size/mode')
        out = os.open(Path(target).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=out_parent)
        dest_before = os.fstat(out)
        require((dest_before.st_dev,dest_before.st_ino) != (before.st_dev,before.st_ino) and dest_before.st_nlink == 1, 'independent destination inode')
        h = hashlib.sha256()
        count = 0
        while count <= row['bytes']:
            raw = os.read(fd, min(1024**2, row['bytes'] + 1 - count))
            if not raw:
                break
            count += len(raw)
            require(count <= row['bytes'], 'copy source grew')
            h.update(raw)
            offset = 0
            while offset < len(raw):
                wrote = os.write(out, raw[offset:])
                require(wrote > 0, 'short copy write')
                offset += wrote
        require(count == row['bytes'] and h.hexdigest() == row['sha256'], 'copy exact source bytes/SHA')
        require(support.stamp(before) == support.stamp(os.fstat(fd)) == support.stamp(os.stat(Path(source).name, dir_fd=parent, follow_symlinks=False)), 'copy source changed')
        os.fchmod(out, int(row['mode'],8))
        os.utime(out, ns=(before.st_atime_ns, before.st_mtime_ns))
        require(os.fstat(out).st_mtime_ns == before.st_mtime_ns and os.fstat(out).st_nlink == 1, 'preserved mtime and independent inode')
    finally:
        if out is not None:
            os.close(out)
        os.close(out_parent)
        os.close(fd)
        os.close(parent)
    require(support.identity(target, row['bytes']) == {k:row[k] for k in ('bytes','sha256','mode')}, 'copy destination readback')
    return {'bytes':row['bytes'], 'sha256':row['sha256'], 'mode':row['mode'], 'preserved_mtime_ns':before.st_mtime_ns, 'independent_inode':True}


def materialize(support, plan, tree):
    root = Path(plan['build_root'])
    require(not os.path.lexists(root), 'fresh destination required')
    support.fresh_directory(root)
    for name,row in sorted(tree['entries'].items(), key=lambda kv:(len(kv[0].split('/')),kv[0])):
        support.relative_name(name)
        if row['kind'] == 'directory':
            require(row['mode'] == '0o700', 'original directory mode')
            support.fresh_directory(root/name)
    copied = {}
    for name,row in tree['entries'].items():
        if row['kind'] == 'regular' and name not in SKIP:
            copied[name] = copy_preserved_member(support, Path(tree['root'])/name, root/name, row)
    require(len(copied) == tree['files']-3 and all(not os.path.lexists(root/x) for x in SKIP), 'exact skip3 copy')
    original, derived = checked_patch(support, plan)
    target = root/PATCH_MEMBER
    require(support.fixed({'path':str(target),'bytes':len(original),'sha256':digest(original)}) == original, 'fresh original patch readback')
    parent, fd, before = support.regular_fd(target)
    os.close(fd)
    try:
        require(before.st_nlink == 1, 'fresh patch file single-link')
        fd = os.open(target.name, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=parent)
        try:
            require(os.fstat(fd).st_ino == before.st_ino, 'patch same fresh inode')
            done = 0
            while done < len(derived):
                written = os.write(fd, derived[done:])
                require(written > 0, 'patch write')
                done += written
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    require(support.identity(target,len(derived)) == {'bytes':len(derived),'sha256':digest(derived),'mode':'0o600'}, 'derived patch readback')
    # Never synthesize a source timestamp: only normal write mtime on the patch.
    return {'copied_files':copied, 'skipped':list(SKIP), 'patch':{'bytes':len(derived),'sha256':digest(derived),'mtime_policy':'normal write; no utime on derived source'}, 'hardlinks_created':False}


def expected_copied_tree(plan, original):
    entries = {k:v.copy() for k,v in original['entries'].items() if k not in SKIP}
    entries[PATCH_MEMBER] = dict(kind='regular', mode='0o600', **{k:plan['derived_source'][k] for k in ('bytes','sha256')})
    return {'root':plan['build_root'],'files':sum(v['kind']=='regular' for v in entries.values()),'bytes':sum(v.get('bytes',0) for v in entries.values()),'entries':dict(sorted(entries.items()))}


def projected_runner(support, plan, evidence):
    sup, obs = support.projected_sources(plan, 'derived_incremental')
    for name,raw in (('supervisor',sup),('observation',obs)):
        pin = plan['projection_pins'][name]
        require(len(raw) == pin['bytes'] and digest(raw) == pin['sha256'], 'projected fixed buffer before compile')
    namespace = {'__builtins__':__builtins__,'os':os,'resource':resource,'signal':signal,'subprocess':subprocess,'time':time,'json':json,'require':require,'AS_LIMIT':plan['phases']['derived_incremental']['as_bytes'],'BUILD_ENV':dict(plan['environment'])}
    exec(compile(obs,'fixed_four_derived_observers','exec',dont_inherit=True),namespace)
    sampler = namespace['sample_leader']
    state = {'path':evidence/'leader_samples.jsonl','identity':None,'count':0,'next':None,'start':None}
    namespace['sample_leader'] = lambda child:sampler(child,state)
    exec(compile(sup,'fixed_five_derived_WNOWAIT','exec',dont_inherit=True),namespace)
    return namespace


def compilation_report(raw):
    text = raw.decode('utf-8')
    lines = text.splitlines()
    compiles = [line for line in lines if re.search(r'(?:g\+\+|gcc|clang\+\+|clang)\s',line) and re.search(r'(?:^|\s)-c(?:\s|$)',line)]
    links = [line for line in lines if re.search(r'(?:g\+\+|gcc|clang\+\+|clang)\s',line) and re.search(r'(?:^|\s)-o\s+\S*verilator_bin(?:\s|$)',line) and not re.search(r'(?:^|\s)-c(?:\s|$)',line)]
    intended = len(compiles)==1 and re.search(r'(?:^|\s)\S*V3ProtectLib\.cpp(?:\s|$)',compiles[0]) is not None and len(links)==1
    return {'compile_commands':compiles,'link_commands':links,'only_V3ProtectLib_compile_and_one_link':intended,'scope':'Saved command log, not a complete descendant syscall trace.'}


def final_delta(plan, original, current):
    changed = [k for k in sorted(set(original['entries']) | set(current['entries'])) if original['entries'].get(k) != current['entries'].get(k)]
    unexpected = [k for k in changed if k not in set(SKIP) | {PATCH_MEMBER}]
    missing = [k for k in SKIP if current['entries'].get(k,{}).get('kind') != 'regular' or current['entries'][k].get('bytes',0)<=0]
    return {'changed_paths':changed,'unexpected_changed_paths':unexpected,'missing_regenerated':missing,'base_regular_files':original['files'],'new_regular_files':current['files'],'original_objects_reused':True}


def arm(deadline,label):
    global DEADLINE_PHASE
    DEADLINE_PHASE = label
    remaining = deadline-time.monotonic()
    require(remaining>0,'absolute deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_sig,_frame):
    raise TimeoutError(DEADLINE_PHASE+' deadline')


def execute(plan,entry,acceptance):
    pending_gate(plan,acceptance)  # Before support load, enumeration, copy, output or subprocess.
    require(sys.platform=='linux','Linux WNOWAIT and KiB rusage required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]) and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'fresh unblocked phase timer')
    c=plan['phases']['derived_incremental'];stop=entry+c['total_seconds'];pre_stop=entry+c['preflight_seconds']
    old_handler=signal.signal(signal.SIGALRM,expired);old_umask=os.umask(0o077)
    runner=None;created=False;evidence=Path(c['evidence_root'])
    try:
        arm(pre_stop,'preflight')
        support=support_module()
        original,review=verify_inputs(support,plan,acceptance)
        runner=projected_runner(support,plan,evidence)
        before=runner['usage']()
        require(before['user_cpu_seconds']==before['system_cpu_seconds']==before['maxrss_kib']==0,'dedicated process has prior child usage')
        require(not os.path.lexists(evidence) and not os.path.lexists(FRESH),'fresh evidence and build roots')
        support.fresh_directory(evidence);created=True
        runner['save'](evidence/'INPUTS.json',{'status':'PREPARED_NOT_EXECUTED','phase':'derived_incremental','plan_sha256':PLAN_SHA,'argv':c['argv'],'cwd':c['cwd'],'environment':plan['environment'],'limits':c,'source_review':review,'base_tree':plan['base_tree'],'patch_record':plan['patch_record'],'scope':'new derived-source incremental build reusing accepted objects, not historical recovery'})
        receipt=materialize(support,plan,original)
        runner['save'](evidence/'COPY_RECEIPT.json',receipt)
        require(support.tree_inventory(FRESH,c['tree_bytes'],c['file_count'],c['entry_count'],c['fsize_bytes'])==expected_copied_tree(plan,original),'exact fresh copied+patched tree')
        require(support.tree_inventory(ORIGINAL,c['tree_bytes'],c['file_count'],c['entry_count'],c['fsize_bytes'])==original,'original tree changed during copy')
        require(time.monotonic()<pre_stop,'copy preflight exhausted; no late spawn')
        work_stop=min(entry+c['work_latest_offset_seconds'],time.monotonic()+c['work_max_seconds'])
        arm(work_stop,'work')
        failure=None;record=None;raw=None
        try:
            record,raw=runner['bounded']('native',c['argv'],Path(c['cwd']),evidence,work_stop-time.monotonic(),c['cpu_seconds'])
        except BaseException as error:
            failure=error
        after=runner['usage']();arm(stop,'postflight')
        runner['save'](evidence/'CHILD_USAGE.json',{'before':before,'after':after,'failure_type':None if failure is None else type(failure).__name__,'maxrss_cumulative_peak_not_difference':True,'linux_maxrss_unit':'KiB','leader_scope':'one original PID/starttime; no compiler subtree peak claim','cleanup_receipt':'native.json'})
        if failure is not None:
            raise failure
        require(record['cleanup_confirmed'] is True,'owned process group cleaned')
        require(len(raw)<=c['log_bytes'],'aggregate log cap')
        compilation=compilation_report(raw);runner['save'](evidence/'COMPILATION.json',compilation)
        tree=support.tree_inventory(FRESH,c['tree_bytes'],c['file_count'],c['entry_count'],c['fsize_bytes'])
        runner['save'](evidence/'BUILD_TREE.json',tree)
        delta=final_delta(plan,original,tree);runner['save'](evidence/'DELTA.json',delta)
        require(not delta['unexpected_changed_paths'] and not delta['missing_regenerated'],'unexpected incremental tree delta')
        require(compilation['only_V3ProtectLib_compile_and_one_link'],'unexpected compilation units or missing intended link; actual log preserved')
        require(tree['entries'][PATCH_MEMBER]==expected_copied_tree(plan,original)['entries'][PATCH_MEMBER],'patch changed during build')
        require(tree['entries']['verilator/bin/verilator_bin']['mode']=='0o700','new derived backend executable mode')
        require(all(tree['entries'][name]['sha256'] != original['entries'][name]['sha256'] for name in ('verilator/src/obj_opt/V3ProtectLib.o','verilator/bin/verilator_bin')), 'derived object/backend must differ from original')
        verified,_=verify_inputs(support,plan,acceptance);require(verified==original,'original sources changed after make')
        samples=support.identity(evidence/'leader_samples.jsonl',c['sample_rows']*2048);require(samples['bytes']>0,'leader samples required')
        inv=support.identity(evidence/'BUILD_TREE.json',4*1024**2)
        result={'status':'DERIVED_INCREMENTAL_EVIDENCE_PENDING_INDEPENDENT_ACCEPTANCE','terminal_success':False,'phase':'derived_incremental','native_exit':record['exit_code'],'cleanup_confirmed':True,'build_tree_inventory_sha256':inv['sha256'],'backend_binary':{'path':FRESH+'/verilator/bin/verilator_bin',**{k:tree['entries']['verilator/bin/verilator_bin'][k] for k in ('bytes','sha256','mode')}},'compilation':compilation,'original_build_preserved':True,'only_source_patch':PATCH_MEMBER,'derived_patch_identity':{'original_source':{'path':ORIGINAL+'/'+PATCH_MEMBER,**{k:plan['original_source'][k] for k in ('bytes','sha256')}},'derived_source':{'path':FRESH+'/'+PATCH_MEMBER,**{k:plan['derived_source'][k] for k in ('bytes','sha256')}},'patch_record':plan['patch_record']},'backend_executed':False,'micro_generated_compiled_or_run':False,'host93_qualified':False,'entry_to_postflight_seconds':time.monotonic()-entry,'acceptance_requires':'Independent exact-source/actual review and separate observed outer exit0 plus total wall<=900s.'}
        runner['save'](evidence/'RESULT.json',result)
        require({p.name for p in evidence.iterdir()}=={'INPUTS.json','COPY_RECEIPT.json','native.json','native.log','leader_samples.jsonl','CHILD_USAGE.json','COMPILATION.json','BUILD_TREE.json','DELTA.json','RESULT.json'},'exact success evidence set')
        require(time.monotonic()<stop,'final total deadline')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop,'failure_record')
                runner['save'](evidence/'FAILURE.json',{'status':'FAILED_DERIVED_INCREMENTAL','phase':'derived_incremental','terminal_success':False,'error_type':type(error).__name__,'message':str(error)})
            except BaseException:
                pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler);os.umask(old_umask)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-reviewed',action='store_true')
    parser.add_argument('--acceptance-path')
    parser.add_argument('--acceptance-bytes',type=int)
    parser.add_argument('--acceptance-sha')
    args=parser.parse_args();plan=load_plan();validate_contract(plan)
    acceptance=None
    if any(x is not None for x in (args.acceptance_path,args.acceptance_bytes,args.acceptance_sha)):
        require(all(x is not None for x in (args.acceptance_path,args.acceptance_bytes,args.acceptance_sha)),'complete external acceptance pin required')
        acceptance={'path':args.acceptance_path,'bytes':args.acceptance_bytes,'sha256':args.acceptance_sha}
    if args.execute_reviewed:
        result=execute(plan,globals()['__entry_monotonic__'],acceptance)
    else:
        support=support_module();checked_patch(support,plan)
        sup,obs=support.projected_sources(plan,'derived_incremental')
        require({n:{'bytes':len(b),'sha256':digest(b)} for n,b in (('supervisor',sup),('observation',obs))}==plan['projection_pins'],'source projection pins')
        result={'status':'SOURCE_ONLY_NO_NATIVE_NO_COPY','source_review_acceptance':'PENDING','patch':plan['derived_source'],'projection_pins':plan['projection_pins']}
    print(json.dumps(result,sort_keys=True))
