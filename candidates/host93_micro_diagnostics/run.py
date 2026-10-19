#!/usr/bin/env python3
"""Bounded FIFO/Host micro diagnostics only; import performs no native work."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')
import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import struct
import time
import types

HERE = Path(__file__).absolute().parent
PREFIX = 'candidates/host93_micro_diagnostics/'
BASE = 'candidates/host93_ci_recovery/'
PINS_SIZE, PINS_SHA = 6377, '78961148de42d4bb1d377a6433915e818fd0e84ad39f2ae5717ae5d08bb2bac1'
MIB = 1024**2
EVIDENCE = ('summary.json', 'source_hashes.json', 'stage_exits.json')
TOOL_STAGES = ('official_source473',) + tuple('host_'+x+'-'+y for y in ('version','micro') for x in ('autoconf','autom4te','m4','flex','bison')) + ('flex_header_acquire','flex_header_compile','fresh_autoconf','fresh_configure','fresh_make') + tuple('derived_tiny_'+x for x in ('version','generate','compile','run'))
STAGES = ('icarus_acquire','fifo_compile','fifo_run') + TOOL_STAGES + ('host_transparent','host_opaque')
FIXTURES = ('fifo_valid_split_miter.sv','fifo_valid_split_cases.sv','host_handshake_micro.sv','leaf_transparent.sv','leaf_opaque_model.sv')
CATEGORIES = ('NONE','TIMEOUT','INPUT_OR_CONTRACT','SYSTEM','INTERRUPTED','UNEXPECTED')
FAILURES = ('NONE','UNKNOWN','RECEIPT_UNAVAILABLE','RECEIPT_INVALID','RECEIPT_PARTIAL','SAMPLER_CONTRACT','SUPERVISOR_TIMEOUT_CLASSIFICATION','LOG_LIMIT','CHILD_SIGNAL','CHILD_EXIT_NONZERO','CLEANUP_UNCONFIRMED','PHASE_POSTFLIGHT')
OBS_KEYS = ('exit_code','final_reap_signal','receipt_timed_out','cleanup_confirmed','waitid_code','waitid_status','kill_attempted','kill_result','native_record_status','failure_code','failure_boundary','child_user_cpu_seconds','child_system_cpu_seconds','child_maxrss_kib_cumulative')
MESSAGES = {'syntax_error_reported':'Compiler reported a syntax error.','undeclared_name_reported':'Compiler reported an undeclared name.','unknown_type_reported':'Compiler reported an unknown type.','header_unavailable_reported':'Compiler reported an unavailable header.','compiler_termination_reported':'Compiler reported signal termination; cause is unestablished.'}
PUBLIC_PATHS = frozenset(('src/V3ProtectLib.cpp',))
FIFO_LINES = frozenset(('CASE_PASS Depth=2 SameCycleRW=0 checks=1294','CASE_PASS Depth=2 SameCycleRW=1 checks=1294','CASE_PASS Depth=3 SameCycleRW=0 checks=1296','CASE_PASS Depth=3 SameCycleRW=1 checks=1296'))
FIFO_PASS = 'PASS fifo_valid_split local four-state matrix and stepped backpressure traces'
ICARUS_IDENTITIES = {'icarus':{'bytes':51640,'sha256':'a6071e4b4a68feafca0c8ee0e6aa275eee9a43a108c62801cfd1eca6eab6d8a3'},'vvp':{'bytes':1354376,'sha256':'a10bd7d4a0850308ac8c2c98115b6a3084f9be978307610f2a521190c28f4023'}}


# Fixed public labels only. No exception text is projected into evidence.
TOOL_CONTRACT_CODES = ('NONE', 'UNMAPPED_CONTRACT', 'MISSING_FIXED_FIELD',
    'HEADER_IDENTITY', 'INPUT_SIZE', 'INPUT_SHA', 'INPUT_CHANGED', 'INPUT_REGULAR',
    'INPUT_IDENTITY_CAP', 'INPUT_GREW', 'INPUT_IDENTITY_CHANGED', 'INPUT_ENCODING', 'INPUT_JSON', 'SOURCE_CHANGED',
    'BUILD_CONFIGURATION', 'HOME_CONFIGURATION', 'CCACHE_BINDING', 'TOOL_IDENTITY',
    'PHASE_RESULT', 'PHASE_LOG_BOUND', 'TREE_ROOT_MODE', 'TREE_ENTRY_CAP',
    'TREE_SYMLINK', 'TREE_DIRECTORY_MODE', 'TREE_SPECIAL_FILE', 'TREE_FILE_CAP',
    'TREE_BYTE_CAP', 'BUILD_OUTPUT_MISSING', 'CPPFLAGS_TEMPLATE', 'CPPFLAGS_VALUE',
    'OBJCACHE_BRANCH', 'OBJCACHE_BLOCK', 'OBJCACHE_GUARD', 'OBJCACHE_OFFICIAL',
    'OBJCACHE_TEMPLATE', 'OBJCACHE_OUTPUT', 'OBJCACHE_WITNESS', 'RECEIPT_CAP',
    'RECEIPT_WRITE', 'HEADER_PACKAGE_COUNT', 'HEADER_ARGUMENT_BOUND', 'HEADER_OUTPUT_SET',
    'HEADER_RECEIPT', 'HEADER_PROBE_OUTPUT_SET', 'HEADER_PROBE_SOURCE',
    'HEADER_PROBE_OBJECT', 'HEADER_PROBE_DEPENDENCY')
TOOL_CONTRACT_BOUNDARIES = ('NONE', 'UNREPORTED', 'HEADER_QUALIFICATION') + tuple(
    'BUILD_' + phase + '_' + check
    for phase in ('AUTOCONF', 'CONFIGURE', 'MAKE')
    for check in ('HEADER_BEFORE', 'SOURCE_BEFORE', 'CONFIGURATION_BEFORE',
                  'HOME_BEFORE', 'CCACHE_BINDING_BEFORE', 'OBJCACHE_BEFORE',
                  'PHASE_AND_TREE', 'HEADER_AFTER', 'SOURCE_AFTER', 'OUTPUTS_AFTER',
                  'CPPFLAGS_AFTER', 'OBJCACHE_AFTER', 'RECEIPT_AFTER'))


PARENT_CONTRACTS = {'PHASE_ORDER': 'PHASE_ORDER',
 'PHASE_BUDGET': 'PHASE_BUDGET',
 'PHASE_LOG_POSTFLIGHT': 'PHASE_LOG_BOUND',
 'OPAQUE_CONTEXT': 'OPAQUE_CONTEXT',
 'OPAQUE_LOG_READ': 'LOG_READ',
 'OPAQUE_OBSERVATION': 'OPAQUE_OBSERVATION',
 'OPAQUE_BUDGET': 'PHASE_BUDGET',
 'ICARUS_CONTRACT_LOAD': 'SOURCE_LOAD',
 'ICARUS_RECEIPT_READ': 'RECEIPT_READ',
 'ICARUS_RECEIPT_DECODE': 'INPUT_JSON',
 'ICARUS_STAGE_VERIFY': 'PACKAGE_STAGE',
 'ICARUS_PACKAGE_ELF': 'PACKAGE_ELF',
 'ICARUS_LIBRARY_IDENTITIES': 'LIBRARY_IDENTITIES',
 'ICARUS_LIBRARY_RECEIPT': 'RECEIPT_WRITE',
 'ICARUS_TOOL_IDENTITIES': 'TOOL_IDENTITY',
 'FIFO_WORKROOT': 'WORKROOT',
 'FIFO_COMPILED_IDENTITY': 'COMPILED_IDENTITY',
 'FIFO_COMPILED_NONEMPTY': 'COMPILED_EMPTY',
 'FIFO_COMPILED_READ': 'COMPILED_READ',
 'FIFO_COMPILED_MODULES': 'VVP_MODULES',
 'FIFO_MODULE_RECEIPT': 'RECEIPT_WRITE',
 'FIFO_RUN_SAME_COMPILED': 'COMPILED_CHANGED',
 'FIFO_RUN_OBSERVATION': 'FIFO_OBSERVATION',
 'TOOLCHAIN_STAGE_COUNT': 'TOOLCHAIN_STAGE_COUNT',
 'TOOLCHAIN_IDENTITIES': 'TOOL_IDENTITY',
 'HOST_RUNTIME_ROOT': 'RUNTIME_ROOT',
 'HOST_RUNTIME_READ': 'RUNTIME_READ',
 'HOST_RUNTIME_DECODE': 'INPUT_JSON',
 'HOST_WORKROOT': 'WORKROOT',
 'HOST_ENVIRONMENT': 'HOST_ENVIRONMENT',
 'HOST_TRANSPARENT_LOG': 'TRANSPARENT_DIAGNOSTIC',
 'HOST_OPAQUE_RESULT': 'OPAQUE_OBSERVATION',
 'FINAL_SOURCE_IDENTITIES': 'SOURCE_CHANGED',
 'FINAL_RUNNER_IDENTITIES': 'SOURCE_CHANGED',
 'FIFO_BEFORE_COMPILE_STAGE': 'PACKAGE_STAGE',
 'FIFO_BEFORE_COMPILE_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_BEFORE_COMPILE_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_COMPILE_STAGE': 'PACKAGE_STAGE',
 'FIFO_AFTER_COMPILE_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_AFTER_COMPILE_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_RUN_STAGE': 'PACKAGE_STAGE',
 'FIFO_AFTER_RUN_FIXTURES': 'FIXTURE_CHANGED',
 'FIFO_AFTER_RUN_LIBRARIES': 'LIBRARY_CHANGED',
 'FIFO_AFTER_COMPILE_TREE': 'TREE_INVENTORY',
 'FIFO_AFTER_RUN_TREE': 'TREE_INVENTORY',
 'HOST_TRANSPARENT_TREE': 'TREE_INVENTORY',
 'HOST_OPAQUE_TREE': 'TREE_INVENTORY',
 'HOST_TRANSPARENT_BEFORE_FIXTURES': 'FIXTURE_CHANGED',
 'HOST_TRANSPARENT_BEFORE_TOOLS': 'TOOL_IDENTITY',
 'HOST_TRANSPARENT_BEFORE_RUNTIME': 'RUNTIME_CHANGED',
 'HOST_TRANSPARENT_BEFORE_BACKEND': 'BACKEND_CHANGED',
 'HOST_TRANSPARENT_AFTER_FIXTURES': 'FIXTURE_CHANGED',
 'HOST_TRANSPARENT_AFTER_TOOLS': 'TOOL_IDENTITY',
 'HOST_TRANSPARENT_AFTER_RUNTIME': 'RUNTIME_CHANGED',
 'HOST_TRANSPARENT_AFTER_BACKEND': 'BACKEND_CHANGED',
 'HOST_OPAQUE_BEFORE_FIXTURES': 'FIXTURE_CHANGED',
 'HOST_OPAQUE_BEFORE_TOOLS': 'TOOL_IDENTITY',
 'HOST_OPAQUE_BEFORE_RUNTIME': 'RUNTIME_CHANGED',
 'HOST_OPAQUE_BEFORE_BACKEND': 'BACKEND_CHANGED',
 'HOST_OPAQUE_AFTER_FIXTURES': 'FIXTURE_CHANGED',
 'HOST_OPAQUE_AFTER_TOOLS': 'TOOL_IDENTITY',
 'HOST_OPAQUE_AFTER_RUNTIME': 'RUNTIME_CHANGED',
 'HOST_OPAQUE_AFTER_BACKEND': 'BACKEND_CHANGED',
 'LIBRARY_BZ2_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_BZ2_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_BZ2_READ': 'LIBRARY_READ',
 'LIBRARY_BZ2_ELF': 'LIBRARY_ELF',
 'LIBRARY_BZ2_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_C_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_C_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_C_READ': 'LIBRARY_READ',
 'LIBRARY_C_ELF': 'LIBRARY_ELF',
 'LIBRARY_C_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_GCC_S_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_GCC_S_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_GCC_S_READ': 'LIBRARY_READ',
 'LIBRARY_GCC_S_ELF': 'LIBRARY_ELF',
 'LIBRARY_GCC_S_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_M_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_M_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_M_READ': 'LIBRARY_READ',
 'LIBRARY_M_ELF': 'LIBRARY_ELF',
 'LIBRARY_M_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_READLINE_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_READLINE_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_READLINE_READ': 'LIBRARY_READ',
 'LIBRARY_READLINE_ELF': 'LIBRARY_ELF',
 'LIBRARY_READLINE_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_STDCXX_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_STDCXX_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_STDCXX_READ': 'LIBRARY_READ',
 'LIBRARY_STDCXX_ELF': 'LIBRARY_ELF',
 'LIBRARY_STDCXX_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_Z_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_Z_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_Z_READ': 'LIBRARY_READ',
 'LIBRARY_Z_ELF': 'LIBRARY_ELF',
 'LIBRARY_Z_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_TINFO_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_TINFO_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_TINFO_READ': 'LIBRARY_READ',
 'LIBRARY_TINFO_ELF': 'LIBRARY_ELF',
 'LIBRARY_TINFO_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_LOADER_RESOLVE': 'LIBRARY_PATH',
 'LIBRARY_LOADER_OWNERSHIP': 'LIBRARY_OWNERSHIP',
 'LIBRARY_LOADER_READ': 'LIBRARY_READ',
 'LIBRARY_LOADER_ELF': 'LIBRARY_ELF',
 'LIBRARY_LOADER_STABLE': 'LIBRARY_STABLE',
 'LIBRARY_READLINE_TRANSITIVE': 'LIBRARY_TRANSITIVE'}
REQUIRE_CODES = {'fixed system library directory': 'LIBRARY_PATH',
 'protected root-owned host library': 'LIBRARY_OWNERSHIP',
 'stable library resolution': 'LIBRARY_STABLE',
 'target readline transitive dependency': 'LIBRARY_TRANSITIVE',
 'ELF64 little endian': 'ELF_ENCODING',
 'fixed x86-64 ELF header': 'ELF_HEADER',
 'ELF program-header bound': 'ELF_PROGRAM_HEADERS',
 'ELF segment bound': 'ELF_SEGMENT',
 'ELF dynamic bound': 'ELF_DYNAMIC_BOUND',
 'fixed dynamic interpreter': 'ELF_INTERPRETER',
 'one dynamic table': 'ELF_DYNAMIC_COUNT',
 'no RPATH and exact string table': 'ELF_DYNAMIC_TAGS',
 'mapped bounded string table': 'ELF_STRING_TABLE',
 'dynamic dependency offset': 'ELF_DEPENDENCY_OFFSET',
 'bounded soname': 'ELF_SONAME',
 'fixed dependency soname': 'ELF_DEPENDENCY_NAME',
 'unique needed sonames': 'ELF_DEPENDENCY_DUPLICATE',
 'absolute normalized ASCII path': 'INPUT_PATH_SYNTAX',
 'symlink refused': 'INPUT_SYMLINK',
 'bounded regular input': 'INPUT_REGULAR',
 'stable same-buffer input': 'INPUT_CHANGED',
 'fixed source identity': 'INPUT_SHA'}
FALLBACK_CODES = {'INPUT_OR_CONTRACT':'UNMAPPED_CONTRACT','TIMEOUT':'TIMEOUT_FAILURE','SYSTEM':'SYSTEM_FAILURE','INTERRUPTED':'INTERRUPTED_FAILURE','UNEXPECTED':'UNEXPECTED_FAILURE'}
CONTRACT_CODES = frozenset(TOOL_CONTRACT_CODES) | frozenset(PARENT_CONTRACTS.values()) | frozenset(REQUIRE_CODES.values()) | frozenset(FALLBACK_CODES.values())
CONTRACT_BOUNDARIES = frozenset(TOOL_CONTRACT_BOUNDARIES) | frozenset(PARENT_CONTRACTS)


class ContractFailure(ValueError):
    def __init__(self, boundary, code):
        if type(boundary) is not str or boundary not in CONTRACT_BOUNDARIES or type(code) is not str or code not in CONTRACT_CODES or boundary=='NONE' or code=='NONE':
            raise ValueError('invalid fixed contract label')
        self.safe_contract_boundary=boundary
        self.safe_contract_code=code
        super().__init__('fixed contract rejection')


def failure_category(error):
    return 'NONE' if error is None else 'TIMEOUT' if isinstance(error,TimeoutError) else 'INPUT_OR_CONTRACT' if isinstance(error,(ValueError,KeyError)) else 'SYSTEM' if isinstance(error,OSError) else 'INTERRUPTED' if isinstance(error,(SystemExit,KeyboardInterrupt)) else 'UNEXPECTED'


def safe_contract_pair(boundary,code):
    if type(boundary) is not str or type(code) is not str: return False
    if boundary in PARENT_CONTRACTS:
        return code==PARENT_CONTRACTS[boundary] or code in REQUIRE_CODES.values()
    return boundary not in ('NONE','UNREPORTED') and boundary in TOOL_CONTRACT_BOUNDARIES and code not in ('NONE',) and code in TOOL_CONTRACT_CODES


@contextlib.contextmanager
def contract_check(boundary):
    require(boundary in PARENT_CONTRACTS,'fixed parent contract boundary')
    try:
        yield
    except BaseException as error:
        try:
            old_boundary=getattr(error,'safe_contract_boundary',None)
            old_code=getattr(error,'safe_contract_code',None)
            if not safe_contract_pair(old_boundary,old_code):
                error.safe_contract_boundary=boundary
                error.safe_contract_code=old_code if type(old_code) is str and old_code in REQUIRE_CODES.values() else PARENT_CONTRACTS[boundary]
        except BaseException:
            pass  # Labels must never replace the original failure.
        raise


def contract_failure_observation(error):
    if error is None: return {'boundary':'NONE','code':'NONE'}
    try:
        boundary=getattr(error,'safe_contract_boundary',None)
        code=getattr(error,'safe_contract_code',None)
        if safe_contract_pair(boundary,code): return {'boundary':boundary,'code':code}
    except BaseException:
        pass
    return {'boundary':'UNREPORTED','code':FALLBACK_CODES[failure_category(error)]}


def require(ok, reason):
    if not ok:
        if reason in REQUIRE_CODES: raise ContractFailure('UNREPORTED',REQUIRE_CODES[reason])
        raise ValueError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def keys(value, expected):
    require(type(value) is dict and set(value)==set(expected), 'strict finite keys')


def finite(value, cap=6480):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=cap


def path(value):
    p=Path(value)
    require(p.is_absolute() and (re.fullmatch('[A-Za-z0-9_/.-]+',str(p)) or re.fullmatch(r'/usr/lib/x86_64-linux-gnu/libstdc\+\+\.so\.6(?:\.[0-9]{1,3}){0,2}',str(p))) and '..' not in p.parts, 'absolute normalized ASCII path')
    for q in (p,)+tuple(p.parents): require(not q.is_symlink(), 'symlink refused')
    return p


def read(pathname, cap):
    p=path(pathname)
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in p.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:
            a=os.fstat(fd)
            require(stat.S_ISREG(a.st_mode) and 0<=a.st_size<=cap,'bounded regular input')
            chunks=[]; count=0
            while count<=cap:
                block=os.read(fd,min(65536,cap+1-count))
                if not block: break
                chunks.append(block);count+=len(block)
            raw=b''.join(chunks)
            stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            require(len(raw)==a.st_size and stamp(a)==stamp(os.fstat(fd))==stamp(os.stat(p.name,dir_fd=parent,follow_symlinks=False)), 'stable same-buffer input')
            return raw
        finally: os.close(fd)
    finally: os.close(parent)


def log_tail(p):
    # Same bounded-tail semantics as the reviewed coordinator; full logs stay private.
    p=path(p)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=64*MIB,'bounded private merged log')
        truncated=before.st_size>MIB
        os.lseek(fd,max(0,before.st_size-MIB),os.SEEK_SET)
        chunks=[];count=0
        while count<=MIB:
            block=os.read(fd,min(65536,MIB+1-count))
            if not block: break
            chunks.append(block);count+=len(block)
        raw=b''.join(chunks)
        stamp=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        require(len(raw)==min(before.st_size,MIB) and stamp(before)==stamp(os.fstat(fd))==stamp(p.stat()),'stable private log tail')
        if truncated:raw=raw.partition(b'\n')[2]
        return raw,truncated
    finally:os.close(fd)


def exact(p, pin):
    keys(pin,('bytes','sha256')); identity(pin)
    raw=read(p,pin['bytes'])
    require(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'fixed source identity')
    return raw


def identity(pin):
    keys(pin,('bytes','sha256'))
    require(type(pin['bytes']) is int and 0<pin['bytes']<=64*MIB and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',pin['sha256']), 'safe size and digest')


def unique(pairs):
    obj={}
    for key,value in pairs:
        require(key not in obj,'duplicate JSON key');obj[key]=value
    return obj


def decode(raw):
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:require(False,'nonfinite JSON'))


def canonical(obj): return (json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def pin_map():
    value=decode(exact(HERE/'SOURCE_PINS.json',{'bytes':PINS_SIZE,'sha256':PINS_SHA}))
    keys(value,('schema','files'));require(value['schema']=='host93-micro-source-pins-v1','source schema')
    require(type(value['files']) is dict and 5<=len(value['files'])<=64,'source count')
    for name,pin in value['files'].items():
        require(type(name) is str and name.startswith((BASE,PREFIX,'development_snapshots/')) and re.fullmatch('[A-Za-z0-9_./-]+',name) and '..' not in name.split('/'),'fixed public source ID')
        identity(pin)
    return value['files']


def public_sources(pins):
    raw=read(HERE/'run.py',MIB)
    combined=dict(pins)
    combined[PREFIX+'run.py']={'bytes':len(raw),'sha256':sha(raw)}
    combined[PREFIX+'SOURCE_PINS.json']={'bytes':PINS_SIZE,'sha256':PINS_SHA}
    return [{'path':n,**p} for n,p in sorted(combined.items())]


def module(raw,p,name):
    # raw is the already hash-verified buffer, never a second path read.
    loaded=types.ModuleType(name);loaded.__file__=str(p)
    exec(compile(raw,str(p),'exec',dont_inherit=True),loaded.__dict__)
    return loaded


def load_sources(repo):
    pins=pin_map()
    buffers={name:exact(HERE/name[len(PREFIX):] if name.startswith(PREFIX) else repo/name,pin) for name,pin in pins.items()}
    def loaded(name,label):
        return module(buffers[name],HERE/name[len(PREFIX):] if name.startswith(PREFIX) else repo/name,label)
    return pins,buffers,loaded


def empty_context(state='NOT_COLLECTED'):
    return {'observations':[],'merged_log_tail':'','truncated':False,'context_state':state}


def validate_context(obj):
    keys(obj,('observations','merged_log_tail','truncated','context_state'))
    require(obj['context_state'] in ('NOT_COLLECTED','READ_ERROR','SANITIZER_ERROR','AVAILABLE') and type(obj['truncated']) is bool and type(obj['observations']) is list and len(obj['observations'])<=20,'finite context')
    for row in obj['observations']:
        require(type(row) is dict and row.get('category') in MESSAGES and row.get('message')==MESSAGES[row['category']],'fixed context prose')
        if row['category']=='compiler_termination_reported': keys(row,('category','message'))
        else:
            keys(row,('path','line','column','category','message'))
            require(row['path'] in PUBLIC_PATHS and type(row['line']) is int and 1<=row['line']<=9999999 and (row['column'] is None or type(row['column']) is int and 1<=row['column']<=9999999),'fixed public location')
    tail=obj['merged_log_tail']
    require(type(tail) is str and all(32<=ord(c)<=126 or c=='\n' for c in tail) and len(tail.split('\n'))<=80 and all(len(x)<=512 for x in tail.split('\n')),'context line bounds')
    require(len((json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode('ascii'))<=16384,'context byte cap')
    if obj['context_state']!='AVAILABLE': require(obj==empty_context(obj['context_state']),'unavailable context empty')


def natural_nonzero(row):
    return (type(row['exit_code']) is int and 0<row['exit_code']<=255 and row['final_reap_signal'] is None and row['receipt_timed_out'] is False and row['cleanup_confirmed'] is True and row['waitid_code']==1 and row['waitid_status']==row['exit_code'] and row['native_record_status']=='FAIL' and row['failure_code']=='CHILD_EXIT_NONZERO' and row['failure_boundary']=='NATIVE_SUPERVISION' and row['kill_attempted'] is True and row['kill_result'] in ('SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT'))


def opaque_observation(raw,row):
    require(natural_nonzero(row) and type(raw) is bytes and 0<len(raw)<65536,'natural nonzero opaque result')
    text=raw.decode('ascii');require('\r' not in text and all(c in '\n\t' or 32<=ord(c)<=126 for c in text),'clean complete opaque log')
    lines=text.splitlines();warnings=[];summaries=[]
    for index,line in enumerate(lines):
        if line.lstrip().startswith('%'):
            if re.fullmatch(r'%Warning-UNOPTFLAT: [ -~]+',line): warnings.append(index)
            elif re.fullmatch(r'%Error: Exiting due to [1-9][0-9]* warning\(s\)',line): summaries.append(index)
            else: require(False,'unexpected or malformed diagnostic header')
    require(1<=len(warnings)<=64 and len(summaries)==1 and summaries[0]==len(lines)-1 and max(warnings)<summaries[0],'sole final fatal-warning summary')
    count=int(re.fullmatch(r'%Error: Exiting due to ([1-9][0-9]*) warning\(s\)',lines[-1])[1])
    require(count==len(warnings),'warning count correlation')
    # Require one diagnostic path that connects this fixed model's combo call
    # and a shared atomic handshake. Never export the native symbol/path text.
    mechanism=False
    for start,end in zip(warnings,warnings[1:]+summaries):
        block=lines[start:end]
        combo=any(re.search(r'leaf_opaque_model\.sv:(?:30|31):[1-9][0-9]*: +Example path: ALWAYS$',x) for x in block)
        handshake=any(re.search(r'host_handshake_micro\.sv:(?:16|18|23|24|25|26|36|37|38|39):[1-9][0-9]*: +Example path: host_handshake_micro\.(?:cmd_valid|step_valid|out_ready|completion_ready|all_command_ready|all_step_ready|all_out_valid|all_completion)$',x) for x in block)
        mechanism=mechanism or (combo and handshake)
    require(mechanism,'fixed opaque combo and atomic handshake path')
    return count


def fifo_observation(raw,fixture):
    require(type(raw) is bytes and 0<len(raw)<65536,'bounded FIFO log')
    lines=raw.decode('ascii').splitlines()
    require(len(lines)==6 and lines[4]==FIFO_PASS and set(lines[:4])==FIFO_LINES,'exact four cases and sole final PASS')
    require(re.fullmatch(re.escape(str(path(fixture)))+r':229: \$finish called at (?:0|[1-9][0-9]{0,6}) \(1ps\)',lines[5]),'fixed Icarus finish notice and finite picoseconds')
    return {'cases':4,'comparisons':5180}


def limits(total,work,cpu,tree):
    return {'total_seconds':total,'work_seconds':work,'cpu_seconds':cpu,'as_bytes':512*MIB,'fsize_bytes':4*MIB,'tree_bytes':tree*MIB,'log_bytes':65536,'sample_rows':total+2,'file_count':512,'entry_count':1024}


ACQUIRE_LIMITS=limits(120,90,40,16)
MICRO_LIMITS=limits(30,10,10,8)


def expected_tool_limits(tool):
    return dict([('official_source473',tool.SOURCE_LIMITS),('flex_header_acquire',tool.HEADER_LIMITS),('flex_header_compile',tool.PROBE_LIMITS)]+[('host_'+x+'-'+y,tool.PROBE_LIMITS) for y in ('version','micro') for x in tool.FIVE]+[('fresh_'+x,tool.BUILD_LIMITS[x]) for x in ('autoconf','configure','make')]+[('derived_tiny_'+x,tool.TINY_LIMITS[x]) for x in ('version','generate','compile','run')])


def verify_evidence(out):
    root=path(out)/'evidence'
    require(root.is_dir() and not root.is_symlink() and set(p.name for p in root.iterdir())==set(EVIDENCE),'exact three evidence files')
    buffers={n:read(root/n,256*1024) for n in EVIDENCE}
    require(sum(map(len,buffers.values()))<=512*1024,'combined evidence cap')
    validate_evidence({n:decode(raw) for n,raw in buffers.items()})
    return 0


def validate_evidence(objects):
    keys(objects,EVIDENCE);summary,sources,exits=(objects[n] for n in EVIDENCE)
    keys(summary,('schema','status','failure_category','contract_failure','seconds','fifo','toolchain','host_pair','production_host_qualified'))
    require(summary['schema']=='host93-micro-summary-v2' and summary['status'] in ('INCOMPLETE','DIAGNOSTIC_OBSERVED') and summary['failure_category'] in CATEGORIES and finite(summary['seconds']) and summary['production_host_qualified'] is False,'finite summary')
    detail=summary['contract_failure'];keys(detail,('boundary','code'))
    boundary,code=detail['boundary'],detail['code']
    require(type(boundary) is str and type(code) is str and boundary in CONTRACT_BOUNDARIES and code in CONTRACT_CODES,'finite safe contract labels')
    if summary['failure_category']=='NONE':
        require(detail=={'boundary':'NONE','code':'NONE'},'success has no contract failure')
    else:
        require(safe_contract_pair(boundary,code) or boundary=='UNREPORTED' and code==FALLBACK_CODES[summary['failure_category']],'failure has correlated finite labels')
        if boundary in TOOL_CONTRACT_BOUNDARIES and boundary not in ('NONE','UNREPORTED'):
            require(summary['failure_category']=='INPUT_OR_CONTRACT','toolchain contract category')
    keys(summary['fifo'],('cases','comparisons'));require(summary['fifo'] in ({'cases':0,'comparisons':0},{'cases':4,'comparisons':5180}),'finite FIFO observation')
    require(type(summary['toolchain']) is bool,'toolchain Boolean')
    keys(summary['host_pair'],('transparent_exit0','opaque_warning_count','opaque_combo_handshake_path'))
    pair=summary['host_pair'];require(type(pair['opaque_combo_handshake_path']) is bool and pair['opaque_combo_handshake_path']==(pair['opaque_warning_count']>0) and type(pair['transparent_exit0']) is bool and type(pair['opaque_warning_count']) is int and 0<=pair['opaque_warning_count']<=64,'finite pair')
    keys(sources,('schema','project_sources','tools'));require(sources['schema']=='host93-micro-source-hashes-v1','source schema')
    require(type(sources['project_sources']) is list and len(sources['project_sources'])<=64,'source rows')
    pins=pin_map();expected=public_sources(pins)
    require(sources['project_sources'] in ([],expected),'exact public fixed source identities')
    require(type(sources['tools']) is dict and set(sources['tools'])<= {'icarus','vvp','derived_backend'},'fixed tool aliases')
    for value in sources['tools'].values(): identity(value)
    for alias,pin in ICARUS_IDENTITIES.items():
        if alias in sources['tools']:require(sources['tools'][alias]==pin,'fixed staged Icarus binary identity')
    keys(exits,('schema','stages'));require(exits['schema']=='host93-micro-stage-exits-v1' and type(exits['stages']) is list and len(exits['stages'])<=25,'stage schema')
    rows=exits['stages'];require([r.get('name') for r in rows]==list(STAGES[:len(rows)]),'exact stage prefix')
    failed=False
    for row in rows:
        require(not failed,'stop after failed stage');keys(row,('name','status','seconds','diagnostics')+OBS_KEYS)
        require(row['status'] in ('FAILED','EXIT0_CLEANED') and finite(row['seconds']),'stage values')
        for k in ('cleanup_confirmed','receipt_timed_out','kill_attempted'): require(row[k] is None or type(row[k]) is bool,'finite Boolean')
        for k in ('exit_code','final_reap_signal','waitid_code','waitid_status','child_maxrss_kib_cumulative'): require(row[k] is None or type(row[k]) is int,'finite integer')
        require(row['exit_code'] is None or -255<=row['exit_code']<=255,'exit range')
        require(row['final_reap_signal']==(-row['exit_code'] if row['exit_code'] is not None and row['exit_code']<0 else None),'signal correlation')
        require((row['waitid_code'] is None and row['waitid_status'] is None) or type(row['waitid_code']) is int and 1<=row['waitid_code']<=6 and type(row['waitid_status']) is int and 0<=row['waitid_status']<=255,'waitid bounds')
        for k in ('child_user_cpu_seconds','child_system_cpu_seconds'): require(row[k] is None or finite(row[k],6600),'CPU bound')
        require(row['child_maxrss_kib_cumulative'] is None or 0<=row['child_maxrss_kib_cumulative']<=16*1024**2,'RSS bound')
        require(row['native_record_status'] in ('UNKNOWN','PASS','FAIL') and row['failure_code'] in FAILURES and row['failure_boundary'] in ('NONE','UNKNOWN','PREPARE','NATIVE_SUPERVISION','USAGE_OR_POSTFLIGHT') and row['kill_result'] in ('UNKNOWN','NOT_REQUESTED','SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT'),'finite status fields')
        validate_context(row['diagnostics'])
        if row['status']=='FAILED':
            failed=True;require(row['diagnostics']['context_state']!='NOT_COLLECTED','failed context attempted')
        else:
            require(row['exit_code']==0 and row['cleanup_confirmed'] is True and row['receipt_timed_out'] is False and row['native_record_status']=='PASS' and row['failure_code']=='NONE' and row['failure_boundary']=='NONE' and row['waitid_code']==1 and row['waitid_status']==0 and row['kill_attempted'] is True and row['kill_result'] in ('SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT') and row['diagnostics']==empty_context(),'clean successful terminal tuple')
    if boundary in PARENT_CONTRACTS:
        count=len(rows)
        if boundary.startswith('ICARUS_') or boundary.startswith('FIFO_BEFORE_COMPILE') or boundary=='FIFO_WORKROOT': wanted=(1,)
        elif boundary.startswith('LIBRARY_'): wanted=(1,2,3)
        elif boundary.startswith('FIFO_AFTER_COMPILE') or boundary.startswith('FIFO_COMPILED') or boundary=='FIFO_MODULE_RECEIPT': wanted=(2,)
        elif boundary.startswith('FIFO_AFTER_RUN') or boundary.startswith('FIFO_RUN_'): wanted=(3,)
        elif boundary=='TOOLCHAIN_STAGE_COUNT': wanted=tuple(range(3,26))
        elif boundary.startswith('TOOLCHAIN_') or boundary.startswith('HOST_RUNTIME_') or boundary in ('HOST_WORKROOT','HOST_ENVIRONMENT'): wanted=(23,)
        elif boundary.startswith('HOST_TRANSPARENT_BEFORE_'): wanted=(23,)
        elif boundary.startswith('HOST_TRANSPARENT_'): wanted=(24,)
        elif boundary.startswith('HOST_OPAQUE_BEFORE_'): wanted=(24,)
        elif boundary.startswith(('HOST_OPAQUE_','OPAQUE_','FINAL_')): wanted=(25,)
        elif boundary=='PHASE_LOG_POSTFLIGHT': wanted=tuple(range(1,26))
        elif boundary=='PHASE_ORDER': wanted=tuple(range(26))
        else: wanted=tuple(range(25))
        require(count in wanted,'parent contract stage prefix')
        if boundary=='PHASE_ORDER':
            pass  # This guard also rejects re-entry after a failed/final row.
        elif boundary=='PHASE_LOG_POSTFLIGHT':
            require(failed,'log rejection precedes clean phase assignment')
        elif boundary.startswith('OPAQUE_'):
            require(failed and pair['opaque_warning_count']==0 and pair['opaque_combo_handshake_path'] is False,'opaque rejection precedes completed observation')
            if boundary=='OPAQUE_BUDGET':
                require(natural_nonzero(rows[-1]) and rows[-1]['diagnostics']['context_state']=='AVAILABLE','opaque budget follows validated natural warning')
        elif boundary.startswith('FINAL_'):
            require(failed and natural_nonzero(rows[-1]) and pair['opaque_warning_count']>0,'final source checks follow completed opaque observation')
        elif boundary=='TOOLCHAIN_STAGE_COUNT' or boundary.startswith('HOST_OPAQUE_') and '_BEFORE_' not in boundary:
            require(not failed or count==25 and natural_nonzero(rows[-1]) and rows[-1]['diagnostics']['context_state']=='AVAILABLE','post-return checks require clean phases or validated opaque warning')
        else:
            require(not failed,'ordinary parent postflight requires clean native prefix')
    clean=lambda n:len(rows)>n and rows[n]['status']=='EXIT0_CLEANED'
    fifo=summary['fifo']['cases']==4
    require(not fifo or clean(2) and {'icarus','vvp'}<=set(sources['tools']),'FIFO requires successful run and fixed tool identities')
    require(not summary['toolchain'] or fifo and clean(22),'toolchain requires all twenty stages')
    require(not pair['transparent_exit0'] or summary['toolchain'] and clean(23),'transparent correlation')
    require((set(sources['tools'])=={'icarus','vvp','derived_backend'}) if summary['toolchain'] else set(sources['tools']) in (set(),{'icarus','vvp'}),'tool identities correlation')
    if rows: require(bool(sources['project_sources']),'stage needs source identities')
    if pair['opaque_warning_count']:
        require(pair['transparent_exit0'] and len(rows)==25 and rows[-1]['status']=='FAILED' and natural_nonzero(rows[-1]) and rows[-1]['diagnostics']['context_state']=='AVAILABLE','opaque natural failure and available context correlation')
    success=summary['status']=='DIAGNOSTIC_OBSERVED'
    require(success==(summary['failure_category']=='NONE'),'summary failure correlation')
    require(not success or fifo and summary['toolchain'] and pair['transparent_exit0'] and pair['opaque_warning_count']>0 and len(rows)==25,'success needs all diagnostic observations')


def write_json(p,obj):
    raw=canonical(obj);require(len(raw)<=256*1024,'JSON cap')
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        require(stream.write(raw)==len(raw),'complete JSON write');stream.flush();os.fsync(stream.fileno())
    require(read(p,len(raw))==raw,'JSON readback')


def interrupted(_sig,_frame): raise TimeoutError('shared work deadline')


def deadline(value):
    now=time.monotonic()
    require(type(value) is float and math.isfinite(value) and now<value<=now+6480 and os.environ.get('GITHUB_ACTIONS')=='true','current pre-checkout work deadline required')
    require(float(os.environ['HOST93_WORK_DEADLINE'])==value and float(os.environ['HOST93_JOB_DEADLINE'])==value+120,'same pre-checkout deadline and upload reserve')
    return value


def acquisition_argv(raw,destination,module_path):
    code=('import sys\nif not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode): raise SystemExit(1)\nimport types\nfrom pathlib import Path\n'
          'm=types.ModuleType("fixed_icarus_acquisition")\nm.__file__='+repr(str(module_path))+'\n'
          'exec(compile('+repr(raw)+',m.__file__,"exec",dont_inherit=True),m.__dict__)\nm.stage(Path('+repr(str(destination))+'))\n')
    return ['/usr/bin/python3','-I','-S','-B','-c',code]


def host_argv(backend,fixtures,work,opaque):
    return [backend,'--cc','--top-module','host_handshake_micro',"-GOPAQUE=1'b"+str(int(opaque)),'--Mdir',str(work/('opaque' if opaque else 'transparent')),'--prefix','Vhost_handshake_micro']+[str(fixtures/n) for n in FIXTURES[2:]]


LIBRARIES = ('libbz2.so.1.0','libc.so.6','libgcc_s.so.1','libm.so.6','libreadline.so.8','libstdc++.so.6','libz.so.1','libtinfo.so.6','ld-linux-x86-64.so.2')
INTERPRETER = '/lib64/ld-linux-x86-64.so.2'
LIBRARY_ALIASES = dict(zip(LIBRARIES,('BZ2', 'C', 'GCC_S', 'M', 'READLINE', 'STDCXX', 'Z', 'TINFO', 'LOADER')))


def elf_dependencies(raw):
    """Finite ELF64/x86-64 metadata read; never invoke ldd or the loader."""
    require(type(raw) is bytes and 64<=len(raw)<=32*MIB and raw[:7]==b'\x7fELF\x02\x01\x01','ELF64 little endian')
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    require(header[1] in (2,3) and header[2]==62 and header[3]==1 and header[8]==64 and header[9]==56 and 0<header[10]<=64,'fixed x86-64 ELF header')
    phoff,count=header[5],header[10]
    require(phoff+count*56<=len(raw),'ELF program-header bound')
    loads=[];dynamics=[];interps=[]
    for i in range(count):
        kind,flags,offset,address,_,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+56*i)
        require(offset+filesz<=len(raw) and filesz<=memsz,'ELF segment bound')
        if kind==1: loads.append((address,offset,filesz))
        elif kind==2:
            require(filesz%16==0 and filesz<=16384,'ELF dynamic bound');dynamics.append((offset,filesz))
        elif kind==3:
            value=raw[offset:offset+filesz];require(value==INTERPRETER.encode()+b'\0','fixed dynamic interpreter');interps.append(INTERPRETER)
    require(len(dynamics)==1 and len(interps)<=1,'one dynamic table')
    offset,size=dynamics[0];tags={};terminated=False
    for pos in range(offset,offset+size,16):
        tag,value=struct.unpack_from('<qQ',raw,pos)
        if tag==0: terminated=True;break
        tags.setdefault(tag,[]).append(value)
    require(terminated and 15 not in tags and 29 not in tags and len(tags.get(5,[]))==1 and len(tags.get(10,[]))==1,'no RPATH and exact string table')
    address,stringsz=tags[5][0],tags[10][0]
    matches=[off+address-start for start,off,n in loads if start<=address and address+stringsz<=start+n]
    require(len(matches)==1 and 0<stringsz<=MIB,'mapped bounded string table')
    table=raw[matches[0]:matches[0]+stringsz];needed=[]
    for offset in tags.get(1,[]):
        require(offset<stringsz,'dynamic dependency offset');end=table.find(b'\0',offset)
        require(offset<end<=offset+128,'bounded soname')
        name=table[offset:end].decode('ascii');require(name in LIBRARIES,'fixed dependency soname');needed.append(name)
    require(len(needed)==len(set(needed)),'unique needed sonames')
    return {'needed':sorted(needed),'interpreter':interps[0] if interps else None}


def library_identities():
    result={}
    for name in LIBRARIES:
        invoked=Path(INTERPRETER if name=='ld-linux-x86-64.so.2' else '/usr/lib/x86_64-linux-gnu/'+name)
        boundary='LIBRARY_'+LIBRARY_ALIASES[name]
        with contract_check(boundary+'_RESOLVE'):
            resolved=Path(os.path.realpath(invoked));require(str(resolved).startswith('/usr/lib/x86_64-linux-gnu/'),'fixed system library directory')
        with contract_check(boundary+'_OWNERSHIP'):
            before=resolved.stat();require(before.st_uid==0 and before.st_nlink>=1 and stat.S_ISREG(before.st_mode) and not before.st_mode&0o022,'protected root-owned host library')
        with contract_check(boundary+'_READ'): raw=read(resolved,32*MIB)
        with contract_check(boundary+'_ELF'): meta=elf_dependencies(raw)
        with contract_check(boundary+'_STABLE'):
            after=resolved.stat();require((before.st_dev,before.st_ino,before.st_mode,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_mode,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and Path(os.path.realpath(invoked))==resolved,'stable library resolution')
        result[name]={'path':str(resolved),'bytes':len(raw),'sha256':sha(raw),'mode':oct(stat.S_IMODE(before.st_mode)),**meta}
    with contract_check('LIBRARY_READLINE_TRANSITIVE'):
        require('libtinfo.so.6' in result['libreadline.so.8']['needed'],'target readline transitive dependency')
    return result


def verify_package_elf(stage,package):
    seen=0;needed=set()
    for row in package['selected']:
        raw=exact(stage/row['path'],{k:row[k] for k in ('bytes','sha256')})
        if raw.startswith(b'\x7fELF'):
            meta=elf_dependencies(raw);seen+=1;needed.update(meta['needed'])
    require(seen==21 and needed==set(LIBRARIES[:7]),'fixed package ELF dependency closure')


def verify_vvp_modules(raw,ivl):
    require(type(raw) is bytes and 0<len(raw)<=4*MIB,'bounded compiled FIFO')
    lines=raw.decode('ascii').splitlines();modules=[]
    for line in lines:
        if 'vpi_module' in line:
            found=re.fullmatch(r':vpi_module "([^"\r\n]+)";',line)
            require(found is not None,'canonical compiled VPI declaration')
            target=Path(found[1]);require(target.parent==ivl and target.name in ('system.vpi','v2005_math.vpi','v2009.vpi','va_math.vpi','vhdl_sys.vpi','vhdl_textio.vpi'),'only staged VPI modules')
            modules.append(target.name)
    require(len(modules)==len(set(modules)) and 'system.vpi' in modules,'fixed staged system VPI witness')
    return sorted(modules)


def execute(repo,out,supplied_deadline):
    start=time.monotonic();stop=deadline(supplied_deadline)
    repo,out=path(repo),path(out)
    require(repo.is_dir() and out.parent.is_dir() and not os.path.lexists(out) and not out.is_relative_to(repo) and not repo.is_relative_to(out),'fresh disjoint workroot')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]) and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'unoccupied deadline signal')
    mask=os.umask(0o077);old_alarm=signal.signal(signal.SIGALRM,interrupted);old_term=signal.signal(signal.SIGTERM,interrupted)
    signal.setitimer(signal.ITIMER_REAL,max(0.001,stop-time.monotonic()))
    owner={'handler':interrupted,'deadline':stop};rows=[];source_rows=[];safe_tools={};failure=None
    observed_fifo={'cases':0,'comparisons':0};tool_ok=False;pair={'transparent_exit0':False,'opaque_warning_count':0,'opaque_combo_handshake_path':False}
    try:
        out.mkdir(mode=0o700)
        for n in ('phases','fixtures','home','tmp'): (out/n).mkdir(mode=0o700)
        pins,buffers,loaded=load_sources(repo)
        source_rows=public_sources(pins)
        supervisor=loaded(BASE+'ci_support_v3.py','fixed_micro_supervisor')
        tool=loaded(BASE+'toolchain/ci_toolchain.py','fixed_micro_toolchain')
        sanitizer=loaded(BASE+'safe_build_diagnostics.py','fixed_micro_sanitizer')
        support,base,_=supervisor.fixed_support(repo)
        bounds=expected_tool_limits(tool);bounds.update(icarus_acquire=ACQUIRE_LIMITS,fifo_compile=MICRO_LIMITS,fifo_run=MICRO_LIMITS,host_transparent=MICRO_LIMITS,host_opaque=MICRO_LIMITS)
        for n in FIXTURES:
            raw=buffers[PREFIX+'fixtures/'+n]
            tool.write_fixture(out/'fixtures'/n,raw)
        def unchanged_fixtures():
            for n in FIXTURES: exact(out/'fixtures'/n,pins[PREFIX+'fixtures/'+n])
        def context(log):
            try: raw,truncated=log_tail(log)
            except BaseException: return empty_context('READ_ERROR')
            try:
                value=sanitizer.sanitize_build_context(raw,str(out/'toolchain/verilator'),PUBLIC_PATHS)
                value['truncated']=value['truncated'] or truncated;validate_context(value);return value
            except BaseException: return empty_context('SANITIZER_ERROR')
        def call_phase(name,argv,cwd,environment,bound):
            with contract_check('PHASE_ORDER'):
                require(len(rows)<25 and name==STAGES[len(rows)] and (not rows or rows[-1]['status']=='EXIT0_CLEANED'),'single ordered phase')
            with contract_check('PHASE_BUDGET'):
                require(bound==bounds[name] and time.monotonic()<stop-15,'unchanged fixed budget within shared deadline')
            began=time.monotonic();evidence=out/'phases'/name;observation={}
            row={'name':name,'status':'FAILED','seconds':0.0,'diagnostics':empty_context(),**supervisor.diagnostic_defaults()};rows.append(row)
            print(json.dumps({'phase':name,'status':'START'},sort_keys=True),flush=True)
            try:
                record,raw,usage=supervisor.run_phase(support,base,name,argv,cwd,evidence,environment,bound,stop,owner,diagnostics=observation)
                with contract_check('PHASE_LOG_POSTFLIGHT'):
                    require(len(raw)<=bound['log_bytes'],'bounded complete log')
                row.update(observation);row['status']='EXIT0_CLEANED'
                return {'record':record,'raw_log':raw,'usage':usage,'evidence_root':str(evidence)}
            except BaseException:
                row.update(observation);row['diagnostics']=context(evidence/'native.log')
                if name=='host_opaque':
                    with contract_check('OPAQUE_CONTEXT'):
                        require(row['diagnostics']['context_state']=='AVAILABLE','opaque context collection required')
                    with contract_check('OPAQUE_LOG_READ'):
                        raw=read(evidence/'native.log',65536)
                    with contract_check('OPAQUE_OBSERVATION'):
                        count=opaque_observation(raw,row)
                    with contract_check('OPAQUE_BUDGET'):
                        require(time.monotonic()-began<bound['total_seconds'],'opaque postflight total budget')
                    return {'opaque_warning_count':count}
                raise
            finally:
                row['seconds']=round(time.monotonic()-began,6)
                print(json.dumps({'phase':name,'status':row['status'],'seconds':row['seconds']},sort_keys=True),flush=True)
        env={'PATH':'/usr/bin:/bin','HOME':str(out/'home'),'TMPDIR':str(out/'tmp'),'LC_ALL':'C','LANG':'C','TZ':'UTC','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        transport=dict(env)
        for k in tool.TRANSPORT_KEYS:
            if k in os.environ: transport[k]=os.environ[k]
        stage=out/'icarus'
        call_phase('icarus_acquire',acquisition_argv(buffers[PREFIX+'icarus_stage.py'],stage,HERE/'icarus_stage.py'),out,transport,ACQUIRE_LIMITS)
        # Acquisition contract and binary/library identity checking are supplied
        # by the separately reviewed fixed package component, never host PATH.
        with contract_check('ICARUS_CONTRACT_LOAD'):
            acquisition=loaded(PREFIX+'icarus_stage.py','fixed_icarus_contract')
        with contract_check('ICARUS_RECEIPT_READ'):
            package_raw=read(stage/'RECEIPT.json',32768)
        with contract_check('ICARUS_RECEIPT_DECODE'):
            package=decode(package_raw)
        with contract_check('ICARUS_STAGE_VERIFY'):
            acquisition.verify_stage(stage,package)
        with contract_check('ICARUS_PACKAGE_ELF'):
            verify_package_elf(stage,package)
        with contract_check('ICARUS_LIBRARY_IDENTITIES'):
            libraries=library_identities()
        with contract_check('ICARUS_LIBRARY_RECEIPT'):
            write_json(out/'icarus_libraries_private.json',libraries)
        with contract_check('ICARUS_TOOL_IDENTITIES'):
            members={r['path']:r for r in package['selected']}
            safe_tools.update({alias:{k:members['usr/bin/'+name][k] for k in ('bytes','sha256')} for alias,name in (('icarus','iverilog'),('vvp','vvp'))})
        icarus=str(stage/'usr/bin/iverilog');vvp=str(stage/'usr/bin/vvp');ivl=stage/'usr/lib/x86_64-linux-gnu/ivl'
        with contract_check('FIFO_WORKROOT'):
            fifo=out/'fifo';fifo.mkdir(mode=0o700)
        def fifo_identity(boundary):
            with contract_check(boundary+'_STAGE'): acquisition.verify_stage(stage,package)
            with contract_check(boundary+'_FIXTURES'): unchanged_fixtures()
            with contract_check(boundary+'_LIBRARIES'):
                require(library_identities()==libraries,'unchanged Icarus library closure')
        fifo_identity('FIFO_BEFORE_COMPILE')
        compile_argv=[icarus,'-B'+str(ivl),'-g2012','-s','fifo_valid_split_tb','-o',str(fifo/'fifo.vvp')]+[str(out/'fixtures'/n) for n in FIXTURES[:2]]
        call_phase('fifo_compile',compile_argv,fifo,env,MICRO_LIMITS)
        fifo_identity('FIFO_AFTER_COMPILE')
        with contract_check('FIFO_AFTER_COMPILE_TREE'): support.tree_inventory(fifo,8*MIB,512,1024,4*MIB)
        with contract_check('FIFO_COMPILED_IDENTITY'):
            compiled=support.identity(fifo/'fifo.vvp',4*MIB)
        with contract_check('FIFO_COMPILED_NONEMPTY'):
            require(compiled['bytes']>0,'new compiled FIFO')
        with contract_check('FIFO_COMPILED_READ'):
            compiled_raw=support.checked_read(fifo/'fifo.vvp',compiled['bytes'],compiled['sha256'])
        with contract_check('FIFO_COMPILED_MODULES'):
            modules=verify_vvp_modules(compiled_raw,ivl)
        with contract_check('FIFO_MODULE_RECEIPT'):
            write_json(out/'fifo_modules_private.json',{'modules':modules,'staged_only':True})
        result=call_phase('fifo_run',[vvp,'-N','-M'+str(ivl),str(fifo/'fifo.vvp')],fifo,env,MICRO_LIMITS)
        fifo_identity('FIFO_AFTER_RUN')
        with contract_check('FIFO_RUN_SAME_COMPILED'): require(support.identity(fifo/'fifo.vvp',4*MIB)==compiled,'same compiled FIFO')
        with contract_check('FIFO_AFTER_RUN_TREE'):
            support.tree_inventory(fifo,8*MIB,512,1024,4*MIB)
        with contract_check('FIFO_RUN_OBSERVATION'):
            observed_fifo=fifo_observation(result['raw_log'],out/'fixtures/fifo_valid_split_cases.sv')
        tools=tool.run(repo,out/'toolchain',call_phase)
        with contract_check('TOOLCHAIN_STAGE_COUNT'):
            require(len(rows)==23,'exact original twenty toolchain stages')
        with contract_check('TOOLCHAIN_IDENTITIES'):
            safe_tools['derived_backend']={k:tools['backend'][k] for k in ('bytes','sha256')};tool_ok=True
        with contract_check('HOST_RUNTIME_ROOT'): root=path(tools['verilator_root']);backend=tools['backend']
        with contract_check('HOST_RUNTIME_READ'):
            runtime_raw=support.checked_read(tools['configured_runtime']['path'],tools['configured_runtime']['bytes'],tools['configured_runtime']['sha256'])
        with contract_check('HOST_RUNTIME_DECODE'): runtime=decode(runtime_raw)
        with contract_check('HOST_WORKROOT'):
            host=out/'host';host.mkdir(mode=0o700)
        with contract_check('HOST_ENVIRONMENT'):
            hostenv=tool.environment(out,root)
        for opaque in (False,True):
            boundary='HOST_OPAQUE' if opaque else 'HOST_TRANSPARENT'
            with contract_check(boundary+'_BEFORE_FIXTURES'): unchanged_fixtures()
            with contract_check(boundary+'_BEFORE_TOOLS'): tool.unchanged_tools(support,tools['host_programs'])
            with contract_check(boundary+'_BEFORE_RUNTIME'): tool.verify_runtime(support,root,runtime)
            with contract_check(boundary+'_BEFORE_BACKEND'):
                require(support.identity(backend['path'],64*MIB)=={k:backend[k] for k in ('bytes','sha256','mode')},'same derived backend')
            result=call_phase('host_opaque' if opaque else 'host_transparent',host_argv(backend['path'],out/'fixtures',host,opaque),host,hostenv,MICRO_LIMITS)
            with contract_check(boundary+'_TREE'): support.tree_inventory(host,8*MIB,512,1024,4*MIB)
            with contract_check(boundary+'_AFTER_FIXTURES'): unchanged_fixtures()
            with contract_check(boundary+'_AFTER_TOOLS'): tool.unchanged_tools(support,tools['host_programs'])
            with contract_check(boundary+'_AFTER_RUNTIME'): tool.verify_runtime(support,root,runtime)
            with contract_check(boundary+'_AFTER_BACKEND'):
                require(support.identity(backend['path'],64*MIB)=={k:backend[k] for k in ('bytes','sha256','mode')},'unchanged derived backend')
            if opaque:
                with contract_check('HOST_OPAQUE_RESULT'):
                    pair['opaque_warning_count']=result['opaque_warning_count'];pair['opaque_combo_handshake_path']=True
            else:
                with contract_check('HOST_TRANSPARENT_LOG'):
                    require(not re.search(rb'(?mi)^\s*%(?:Warning|Error)',result['raw_log']),'transparent has no warning or error')
                pair['transparent_exit0']=True
        with contract_check('FINAL_SOURCE_IDENTITIES'):
            for n,pin in pins.items(): exact(HERE/n[len(PREFIX):] if n.startswith(PREFIX) else repo/n,pin)
        with contract_check('FINAL_RUNNER_IDENTITIES'):
            require(public_sources(pins)==source_rows,'unchanged runner and manifest')
    except BaseException as error: failure=error
    finally:
        try:
            require(time.monotonic()<stop,'same work deadline before evidence')
            category=failure_category(failure)
            summary={'schema':'host93-micro-summary-v2','status':'DIAGNOSTIC_OBSERVED' if failure is None else 'INCOMPLETE','failure_category':category,'contract_failure':contract_failure_observation(failure),'seconds':round(time.monotonic()-start,6),'fifo':observed_fifo,'toolchain':tool_ok,'host_pair':pair,'production_host_qualified':False}
            objects={'summary.json':summary,'source_hashes.json':{'schema':'host93-micro-source-hashes-v1','project_sources':source_rows,'tools':safe_tools},'stage_exits.json':{'schema':'host93-micro-stage-exits-v1','stages':rows}}
            validate_evidence(objects);(out/'evidence').mkdir(mode=0o700)
            for n,obj in objects.items(): write_json(out/'evidence'/n,obj)
            verify_evidence(out);require(time.monotonic()<stop,'same work deadline after evidence')
        except BaseException as error:
            if failure is None: failure=error
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_alarm);signal.signal(signal.SIGTERM,old_term);os.umask(mask)
    print(json.dumps({'status':'DIAGNOSTIC_OBSERVED' if failure is None else 'INCOMPLETE'},sort_keys=True),flush=True)
    return 0 if failure is None else 1


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--verify-evidence',action='store_true')
    parser.add_argument('--repo',type=Path);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--deadline',type=float)
    args=parser.parse_args(argv)
    if args.verify_evidence:
        require(not args.execute and args.repo is None and args.deadline is None,'verify-only interface')
        return verify_evidence(args.out)
    require(args.execute and args.repo is not None and args.deadline is not None,'native execution is opt-in with original deadline')
    return execute(args.repo,args.out,args.deadline)


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception:
        print('{"status":"INCOMPLETE"}',flush=True);raise SystemExit(1)
