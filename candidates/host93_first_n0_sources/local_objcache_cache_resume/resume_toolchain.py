"""Finite Autoconf 2.72 witness and verified original473 cached-data continuation."""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import hashlib,json,os
from pathlib import Path
RECEIPT_PIN={'bytes':144253,'sha256':'fb7274905c053a102f0d4652fb87b57bc1cd00fb63524f085f5b81225c36366f'}
BLOCK272=b'if test ${ac_cv_prog_OBJCACHE+y}\nthen :\n  printf %s "(cached) " >&6\nelse case e in #(\n  e) if test -n "$OBJCACHE"; then\n  ac_cv_prog_OBJCACHE="$OBJCACHE" # Let the user override the test.\nelse\nas_save_IFS=$IFS; IFS=$PATH_SEPARATOR\nfor as_dir in $PATH\ndo\n  IFS=$as_save_IFS\n  case $as_dir in #(((\n    \'\') as_dir=./ ;;\n    */) ;;\n    *) as_dir=$as_dir/ ;;\n  esac\n    for ac_exec_ext in \'\' $ac_executable_extensions; do\n  if as_fn_executable_p "$as_dir$ac_word$ac_exec_ext"; then\n    ac_cv_prog_OBJCACHE="ccache"\n    printf "%s\\n" "$as_me:${as_lineno-$LINENO}: found $as_dir$ac_word$ac_exec_ext" >&5\n    break 2\n  fi\ndone\n  done\nIFS=$as_save_IFS\n\nfi ;;\nesac\nfi\nOBJCACHE=$ac_cv_prog_OBJCACHE\n'
OLD_BLOCK=BLOCK272.replace(b'else case e in #(\n  e) ',b'else $as_nop\n').replace(b'\nfi ;;\nesac\nfi\nOBJCACHE=',b'\nfi\nfi\nOBJCACHE=')
def need(ok,message):
    if not ok:raise ValueError(message)
def objcache_witness(original,raw):
    """Only one exact official 688-byte case-e rendering is added.

    The then-test and cached printf are unchanged. With the original explicitly
    set-empty cache variable the then arm is taken, so neither else rendering
    runs. Both end at the same empty assignment; the original nonempty version
    guard is still mandatory. This is a finite byte projection, no shell parser.
    """
    need(type(raw) is bytes,'fixed configure bytes')
    if BLOCK272 not in raw:return original(raw)
    need(raw.count(BLOCK272)==1 and OLD_BLOCK not in raw,'finite OBJCACHE cache branch')
    projected=raw.replace(BLOCK272,OLD_BLOCK)
    need(projected.replace(OLD_BLOCK,BLOCK272)==raw,'bounded sole OBJCACHE cache block')
    proof=original(projected)
    proof.update(generated_branch_bytes=len(BLOCK272),generated_branch_sha256=hashlib.sha256(BLOCK272).hexdigest(),rendering='EXACT_OFFICIAL_AUTOCONF_2_72_CASE_E',normalization_inverse_exact=True)
    return proof

def stage_cache(g,component,repo,cache,destination):
    """One parent data stage. Fixed receipt plus all473 original Git blobs.

    copy_member is the original checked_read/same-buffer write/readback helper.
    The old archive/build output is neither copied nor claimed as new work.
    """
    cache,destination=g.clean(cache),g.clean(destination)
    need(cache!=destination and not destination.is_relative_to(cache) and not cache.is_relative_to(destination) and not os.path.lexists(destination),'separate fresh cached473 destination')
    support,_,buffers=component.load_sources(repo)
    receipt=g.checked(cache/'SOURCE.json',RECEIPT_PIN,1024**2)
    document=g.decode(receipt)
    need(document['commit']==component.COMMIT and document['archive_complete'] is True and document['selected_bytes']==11747893 and len(document['verified_members'])==473 and document['cleanup_errors']==[] and not os.path.lexists(cache/'FAILED.json'),'complete fixed original acquisition receipt')
    table,original=component.verify_official473(support,cache/'verilator',buffers)
    support.fresh_directory(destination);support.fresh_directory(destination/'verilator')
    for row in table['members']:
        name=row['path'];support.copy_member(cache/'verilator'/name,destination/'verilator',name,original['entries'][name],0o600)
    # The fixed receipt is itself copied from the already verified buffer.
    fd=os.open(destination/'SOURCE.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(receipt):
            count=os.write(fd,receipt[offset:]);need(count>0,'complete fixed receipt write');offset+=count
    finally:os.close(fd)
    need(g.checked(destination/'SOURCE.json',RECEIPT_PIN,1024**2)==receipt and g.checked(cache/'SOURCE.json',RECEIPT_PIN,1024**2)==receipt,'same fixed receipt before and after copy')
    _,copied=component.verify_official473(support,destination/'verilator',buffers)
    _,after=component.verify_official473(support,cache/'verilator',buffers)
    need(after==original and all(copied[k]==original[k] for k in ('entries','files','bytes')),'same original473 before copy and both postflights')
    return {'stage':'local_fixed473_copy','kind':'PARENT_DATA_ONLY','files':473,'source_bytes':11747893,'receipt_pin':RECEIPT_PIN,'native_started':False,'network_started':False,'prior_phase_cleanup_inherited':False,'archive_copied':False}

def safe_contract(component,error):
    result={'safe_contract_boundary':None,'safe_contract_code':None}
    if type(error) is component.ContractFailure:
        boundary=getattr(error,'safe_contract_boundary',None);code=getattr(error,'safe_contract_code',None)
        if type(boundary) is str and boundary in component.CONTRACT_BOUNDARIES and type(code) is str and code in component.CONTRACT_CODES:
            result.update(safe_contract_boundary=boundary,safe_contract_code=code)
    return result

def bind(g,adapter,component,repo,cached_copy):
    """Project only known original run anchors; old file and run stay immutable."""
    raw=g.checked(repo/adapter.CI,adapter.CI_PIN)
    original_witness=component.objcache_configure_witness
    component.objcache_configure_witness=lambda raw:objcache_witness(original_witness,raw)
    cached_copy=g.clean(cached_copy)
    component.__dict__['LOCAL_SOURCE_COPY']=cached_copy
    acquisition=(b"        acquired, _ = checked_phase(call_phase, support, tools, 'official_source473',\n"
                 b"            acquisition_argv(repo, work / 'acquired', buffers), work, env, SOURCE_LIMITS, work / 'acquired')\n"
                 b"        receipt_pin = support.identity(work / 'acquired/SOURCE.json', 1024**2)\n"
                 b"        receipt = json.loads(support.checked_read(work / 'acquired/SOURCE.json',\n"
                 b"                                                receipt_pin['bytes'], receipt_pin['sha256']))\n"
                 b"        require(not os.path.lexists(work / 'acquired/FAILED.json') and\n"
                 b"                receipt['commit'] == COMMIT and receipt['archive_complete'] is True and\n"
                 b"                receipt['selected_bytes'] == 11747893 and len(receipt['verified_members']) == 473 and\n"
                 b"                receipt['cleanup_errors'] == [], 'fresh complete official source receipt')\n"
                 b"        table, original = verify_official473(support, work / 'acquired/verilator', buffers)\n"
                 b"        root = work / 'verilator'\n"
                 b"        patch, derived = materialize_patched(support, work / 'acquired/verilator', root,\n"
                 b"                                            table, original, buffers)\n")
    replacement=acquisition[acquisition.index(b'        receipt_pin ='):]
    replacement=replacement.replace(b"work / 'acquired/SOURCE.json'",b"LOCAL_SOURCE_COPY / 'SOURCE.json'").replace(b"work / 'acquired/FAILED.json'",b"LOCAL_SOURCE_COPY / 'FAILED.json'").replace(b"work / 'acquired/verilator'",b"LOCAL_SOURCE_COPY / 'verilator'")
    replacement=b"        acquired = {'usage': {'kind': 'PARENT_DATA_ONLY', 'native_acquisition_rerun': False}}\n"+replacement
    replacements=((b"tools['/usr/bin/flex']",b"tools[LOCAL_TOOLS['flex']]"),(b'qualification = qualify_tools(support, tools, buffers, work, call_phase, env)',b'qualification = accepted_tools(support, tools, buffers, work, call_phase, env)'),(b"'historical_actual_or_review_inherited': False",b"'existing_local_tool_qualification_reused': True"),(acquisition,replacement),(b"'source_phase_usage': acquired['usage']",b"'cached_source_data_usage': acquired['usage']"))
    function,proof=adapter.exact_function(g,raw,'run',component.__dict__,replacements)
    def run(repo_arg,work,call_phase,stop_after_build=False):
        work=g.clean(work)
        need(Path(repo_arg)==repo and work.parent==cached_copy.parent and work!=cached_copy,'fixed sibling cached copy and fresh build')
        g.checked(cached_copy/'SOURCE.json',RECEIPT_PIN,1024**2)
        return function(repo_arg,work,call_phase,stop_after_build)
    component.run=run
    return {'run':proof,'cached_source':'REVALIDATED_ORIGINAL473_BYTES_ONLY','objcache_block':{'bytes':len(BLOCK272),'sha256':hashlib.sha256(BLOCK272).hexdigest()},'old_receipt_not_new_native_qualification':True}
