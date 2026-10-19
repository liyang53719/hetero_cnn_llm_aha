#!/usr/bin/env python3
"""Read one fixed saved safe evidence set; no private-log reconstruction or native work."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import types

PINS = {
 'summary.json': (477, 'cdc65bcd68d56567fda0538be488bf9c6746243b1116df7ad4d2d7f48df8916c'),
 'source_hashes.json': (7600, '84b8b93de5688502846f5a08cfb801036a5337eb3c4a7faead625feb3277713f'),
 'stage_exits.json': (24222, '8477ee89b95ea4eaee1685f9a6918dc471137735e7facd5e99ac71ed9e939ce5')}
BASE_PINS = {
 'run.py': (53273, '7dffb2a2fbb108b2bf01926e00372346e5c85e9ef7cef7bbfa03b3b1b45577b0'),
 'SOURCE_PINS.json': (6377, '78961148de42d4bb1d377a6433915e818fd0e84ad39f2ae5717ae5d08bb2bac1')}

def require(ok, reason):
    if not ok: raise ValueError(reason)

def exact(p, pin):
    require(p.is_absolute() and '..' not in p.parts, 'absolute input')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_size == pin[0], 'fixed regular input size')
        with os.fdopen(fd, 'rb', closefd=False) as f: raw = f.read(pin[0] + 1)
        stamp = lambda x: (x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        require(stamp(a) == stamp(os.fstat(fd)) == stamp(os.stat(p,follow_symlinks=False)), 'stable input')
        require(len(raw) == pin[0] and hashlib.sha256(raw).hexdigest() == pin[1], 'fixed input SHA')
        return raw
    finally: os.close(fd)

def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--evidence-dir',type=Path,required=True)
    ap.add_argument('--baseline-dir',type=Path,required=True)
    args = ap.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2))
    signal.alarm(30)
    rawbase = {n:exact(args.baseline_dir/n,pin) for n,pin in BASE_PINS.items()}
    original = types.ModuleType('fixed_original_micro_validator')
    original.__file__ = str(args.baseline_dir/'run.py')
    exec(compile(rawbase['run.py'],original.__file__,'exec',dont_inherit=True),original.__dict__)
    inputs = {n:exact(args.evidence_dir/n,pin) for n,pin in PINS.items()}
    obj = {n:original.decode(raw) for n,raw in inputs.items()}
    original.validate_evidence(obj)
    summary = obj['summary.json']; rows = obj['stage_exits.json']['stages']; row = rows[-1]
    require(summary['status']=='INCOMPLETE' and summary['failure_category']=='INPUT_OR_CONTRACT' and summary['contract_failure']=={'boundary':'OPAQUE_OBSERVATION','code':'OPAQUE_OBSERVATION'},'fixed original rejection')
    require(len(rows)==25 and all(r['status']=='EXIT0_CLEANED' for r in rows[:-1]) and row['name']=='host_opaque' and original.natural_nonzero(row),'fixed successful prefix and natural opaque exit')
    require(summary['fifo']=={'cases':4,'comparisons':5180} and summary['toolchain'] and summary['host_pair']=={'transparent_exit0':True,'opaque_warning_count':0,'opaque_combo_handshake_path':False},'original finite observations')
    context = row['diagnostics']
    require(context['context_state']=='AVAILABLE' and context['truncated'] is False,'complete retained safe context flag')
    lines=context['merged_log_tail'].splitlines(); warnings=[]; fatals=[]
    for i,line in enumerate(lines):
        if line.lstrip().startswith('%'):
            if re.fullmatch(r'%Warning-UNOPTFLAT: \[PATH\]:[1-9][0-9]*:[1-9][0-9]*: [ -~]+',line): warnings.append(i)
            elif line=='%Error: Exiting due to 4 warning(s)': fatals.append(i)
            else: require(False,'unexpected retained diagnostic')
    require(len(warnings)==4 and fatals==[len(lines)-1] and warnings[0]==0,'four retained UNOPTFLAT and sole final four-warning fatal')
    witnesses=0
    for start,end in zip(warnings,warnings[1:]+fatals):
        block=lines[start:end]
        combo=any(re.fullmatch(r' +\[PATH\]:30:3: +Example path: ALWAYS',s) for s in block)
        atomic=any(re.fullmatch(r' +\[PATH\]:18:15: +Example path: all_command_ready',s) for s in block)
        model=any(re.fullmatch(r' +\[PATH\]:27:9: +Example path: host_handshake_micro\.leaves\[[0-7]\]\.opaque\.leaf\.cmd_ready_o_combo__V',s) for s in block)
        witnesses += int(combo and atomic and model)
    require(witnesses==4,'four same-block redacted model witnesses')
    # No substitution of [PATH], no call to opaque_observation, no summary mutation.
    for n,pin in BASE_PINS.items(): require(exact(args.baseline_dir/n,pin)==rawbase[n],'unchanged baseline')
    for n,pin in PINS.items(): require(exact(args.evidence_dir/n,pin)==inputs[n],'unchanged saved originals')
    result = {
      'schema':'host93-fixed-safe-context-reassessment-v1',
      'run_id':39213008977,
      'status':'SAFE_CONTEXT_SUPPORTS_MODELED_DEPENDENCY_OVERAGGREGATION',
      'original_status':'INCOMPLETE', 'original_contract_boundary':'OPAQUE_OBSERVATION',
      'original_warning_observation_accepted':False,
      'original_evidence_unmodified':True, 'original_schema_validation':'PASS',
      'source_identity_rows':len(obj['source_hashes.json']['project_sources']),
      'native_stage_count':25, 'clean_native_prefix':24,
      'fifo_cases':4, 'fifo_comparisons':5180,
      'fifo_scope':'EXTRACTED_COMBINATIONAL_FOUR_STATE_AND_MANUAL_STATE_TRACES_ONLY',
      'toolchain_twenty_stages_clean':True, 'transparent_native_exit':0,
      'opaque_native_exit':row['exit_code'], 'opaque_timeout':False, 'opaque_cleanup_confirmed':True,
      'safe_context_truncated':False, 'retained_safe_lines':len(lines),
      'retained_warning_count':4, 'retained_rules':['UNOPTFLAT'],
      'retained_fatal_warning_count':4, 'same_block_redacted_model_witnesses':witnesses,
      'raw_log_replayed':False, 'raw_observer_requalified':False,
      'private_source_file_mapping':'NOT_RECOVERABLE_FROM_REDACTED_PATHS',
      'model_scope':'HAND_WRITTEN_12_INPUT_4_OUTPUT_OPAQUE_VERSUS_TRANSPARENT',
      'production_host_qualified':False,
      'production_22_input_21_output_wrapper_equivalence':'NOT_ESTABLISHED',
      'native_work_performed':False,
      'inputs':{n:{'bytes':pin[0],'sha256':pin[1]} for n,pin in PINS.items()}}
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__': main()
