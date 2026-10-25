"""Postterminal-only, read-only M2 evidence comparison. No oracle/model import.

The caller must enforce the separate read boundary and complete opaque payload
hash checks before permitting comparison. Metadata qualification does not grant
permission to decode tensors and never executes the retained independent recipe.
"""
import hashlib
import json
from pathlib import Path
import struct

FIELDS=('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp',
        'softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
CONTROL=('counts','service_counts','scalar_calls','native_fmas','edges',
         'owner_clock','held_checks','work_events','lane_calls','owner_counts')
SENTINEL=0xa5963cc3


def need(ok,message):
    if not ok:raise ValueError(message)


def _digest(raw):return hashlib.sha256(raw).hexdigest()


def _metadata(path,pin=None):
    path=Path(path);raw=path.read_bytes()
    if pin is not None:need(len(raw)==pin['bytes'] and _digest(raw)==pin['sha256'],'metadata pin: '+str(path))
    return json.loads(raw)


def qualify_reference(config):
    """Read only the sealed provenance/config/result JSON; no tensor reads."""
    path=Path(config['reference_seal'])
    seal=_metadata(path,config['files'][str(path)])
    directory=Path(config['reference_directory'])
    need(directory.is_absolute() and directory.resolve()==directory and
         seal['reference_directory']==str(directory),'exact retained reference directory')
    need(seal['status']=='REUSE_EXISTING_INDEPENDENT_M2_RECIPE_OUTPUT_ONLY_AFTER_BOTH_NEW_TERMINALS'
         and seal['recipe_will_be_executed'] is False,'retained-reference-only scope')
    expected={str(directory/'REFERENCE_FIELDS.json'),str(directory/'REFERENCE_OUTPUT.u32le'),str(directory/'REFERENCE_SCORES.u32le')}
    expected.update(str(directory/('REFERENCE_'+name+'.u32le')) for name in FIELDS)
    expected.update(str(directory/('REFERENCE_PRESENCE_'+name+'.binmeta')) for name in FIELDS)
    need(set(seal['artifacts'])==expected and config['reference_artifacts']==seal['artifacts'],
         'exact complete 23-file reference artifact inventory')
    need(all(config['files'][name]==pin for name,pin in seal['artifacts'].items()),'reference pins in new admission')
    previous=_metadata(seal['source_config']['path'],seal['source_config']['pin'])
    result=_metadata(seal['result']['path'],seal['result']['pin'])
    need(previous['rows']==2 and set(previous['inputs'])=={'qr','kr','v'},'retained original M2 source config')
    need(set(config['inputs'])==set(config['input_prefixes'])==set(seal['inputs'])=={'qr','kr','v'},'only frozen operator inputs')
    for role,width in (('qr',1536),('kr',256),('v',256)):
        old=previous['inputs'][role];current=config['inputs'][role];sealed=seal['inputs'][role]
        need(old==current and current['path']==sealed['path'] and
             {k:current[k] for k in ('bytes','sha256')}==sealed['whole'],'same original full input: '+role)
        prefix=config['input_prefixes'][role]
        need(prefix==sealed['prefix'] and prefix['shape']==[2,width] and
             prefix['offset_bytes']==0 and prefix['bytes']==2*width*4,'same exact M2 prefix: '+role)
    need(result['status']=='PASS_REAL_ATTENTION_M2_ROTATED_IDENTITY_TRIO_DIAGNOSTIC_ONLY'
         and result['m']==2 and result['reference_after_all_three_terminals'] is True
         and result['inputs_reverified'] is True and result['fullblock'] is False,'retained actual terminal/reference provenance')
    report=result['comparison']['reference_capture']
    need(report['status']=='COMPLETE_EXISTING_REFERENCE_RECIPE_CAPTURE'
         and report['execution_provenance']=='EXISTING_AST_INDEPENDENT_REFERENCE_RECIPE'
         and report['all_dut_terminals_before_reference'] is True
         and report['arithmetic_or_control_replaced'] is False
         and report['dut_values_consumed'] is False and report['hardware_acceptance'] is False,
         'retained independent recipe qualification')
    need(report['source_pins']==previous['reference_sources']==seal['source_roles']==config['reference_sources'],
         'same exact independent recipe and shared-primitive sources')
    need(result['comparison']['output_words']==3072 and result['comparison']['score_words']==36
         and result['comparison']['intermediate_fields']==10 and set(report['fields'])==set(FIELDS),
         'retained M2 output/score/ten-field geometry')
    need(seal['artifacts'][str(directory/'REFERENCE_OUTPUT.u32le')]['sha256']==result['comparison']['output_sha256']
         and seal['artifacts'][str(directory/'REFERENCE_SCORES.u32le')]['sha256']==result['comparison']['scores_sha256'],
         'reference output and score provenance hashes')
    return dict(status='QUALIFIED_RETAINED_INDEPENDENT_M2_REFERENCE_METADATA',rows=2,
                reference_directory=str(directory),reference_result_pin=seal['result']['pin'],
                same_input_prefixes=True,same_reference_sources=True,recipe_executed_now=False,
                tensor_values_read=False,payload_decode_permission_granted=False)


def _shape(name):
    return ((12,2,2,16) if name=='dot_parts' else (12,2,3) if name=='normalizer'
            else (12,2,128) if name in ('pv_raw','pv_bf16') else (12,2,2))


def _file(directory,name):
    need(type(name) is str and Path(name).name==name and name not in ('.','..'),'local artifact filename only')
    path=directory/name;need(path.resolve()==path and not path.is_symlink(),'unaliased artifact')
    return path


def _load_fields(directory,prefix,report,*,reference):
    directory=Path(directory);metadata=_metadata(directory/(prefix+'_FIELDS.json'))
    need(set(metadata)==set(report)==set(FIELDS),'exact ten field inventory')
    fields={};cell_count=0
    for name in FIELDS:
        row=metadata[name];summary=report[name];shape=_shape(name);count=1
        need(row['file']==prefix+'_'+name+'.u32le' and row['presence_file']==prefix+'_PRESENCE_'+name+'.binmeta','exact field artifact names')
        for dimension in shape:count*=dimension
        raw=_file(directory,row['file']).read_bytes();presence=_file(directory,row['presence_file']).read_bytes()
        frequency=row['frequency']
        need(tuple(row['shape'])==tuple(summary['shape'])==shape and len(raw)==row['bytes']==4*count
             and len(presence)==len(frequency)==count,'M2 field shape/extent: '+name)
        need(all(type(v) is int and 0<=v<65536 for v in frequency),'u16 frequency: '+name)
        need(_digest(raw)==row['sha256']==summary['raw_sha256'] and
             _digest(presence)==row['presence_sha256']==summary['presence_sha256'] and
             _digest(struct.pack('<%dH'%count,*frequency))==summary['frequency_sha256'],'field/report digest binding: '+name)
        words=struct.unpack('<%dI'%count,raw)
        width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
        causal=name not in ('normalizer','pv_raw','pv_bf16')
        for h in range(12):
            for token in range(2):
                for key in range(2) if causal else (None,):
                    present=key is None or key<=token
                    start=((h*2+token)*2+key)*width if causal else (h*2+token)*width
                    expected=(8*(token+1) if reference and name=='normalizer' else
                              8 if name in ('softmax_fp32','prob_bf16') else 1) if present else 0
                    for index in range(start,start+width):
                        need(presence[index]==int(present) and frequency[index]==expected
                             and (present or words[index]==SENTINEL),'causal presence/frequency/sentinel: '+name)
                        cell_count+=1
        observed=sum(presence);total=sum(frequency)
        need(summary['observed_words']==observed and summary['identical_repeats']==total-observed
             and summary['writes']==(total if reference else observed),'field write/repeat accounting: '+name)
        if not reference:need(summary['words']==count,'DUT field word count')
        fields[name]=dict(shape=shape,words=words,observed=presence,frequency=tuple(frequency),
                          artifact=dict(raw_file=str(directory/row['file']),raw_sha256=row['sha256'],
                          presence_file=str(directory/row['presence_file']),presence_sha256=row['presence_sha256'],
                          frequency_file=str(directory/(prefix+'_FIELDS.json')),frequency_sha256=summary['frequency_sha256']))
    return fields,cell_count


def _terminal(path,arm):
    terminal=_metadata(path)
    need(terminal['status']=='COMPLETE_REAL_M2_TERMINAL_REFERENCE_PENDING' and terminal['arm']==arm
         and terminal['terminal_acked'] is True and terminal['resources_released'] is True,
         'both actual fresh-worker terminal ACKs required before comparison')
    need(terminal['capture_error'] is None and terminal['service_trace_error'] is None,'failed observer/service trace cannot qualify')
    report=terminal['capture_report']
    need(report['status']=='COMPLETE_SOFTWARE_OBSERVATION_NOT_HARDWARE' and
         report['execution_provenance']=='NORMAL_LOADED_SOURCE_SOFTWARE' and
         report['terminal']==dict(clean=True,same_services=True,state='idle') and
         report['packed_acks']==report['packed_done']==24 and
         report['observer_launches_native_or_rtl'] is False,'complete real M2 observation terminal')
    need([r['phase'] for r in terminal['masks']]==['installed','cleaned'],'actual installed/cleaned observer lifecycle')
    if arm=='normalization_helper':
        need(report['observation_contract']=='normalization-helper-active-chain-v1' and
             report['normalization_boundary']=='helper_PY_RETURN_before_op_return' and
             report['original_owner_bytes_unchanged'] is False,'new helper observation contract')
    return terminal


def _probe_semantics(report):
    """Never compare traceback text or locations; only declared semantic receipt."""
    need(type(report) is dict and report,'real scalar-probe receipt required')
    need(report['scope']=='SIX_POST_TERMINAL_SCALAR_HELPER_PROBES_NOT_MATRIX_JOBS'
         and report['passed'] is True and len(report['cases'])==6
         and all(row['matches'] is True for row in report['cases'])
         and report['scalar_delta']=={'div':1,'mul':5}
         and report['matrix_fmas_before']==report['matrix_fmas_after']==933888,
         'successful bounded scalar-only exception/value qualification')
    def strip(value):
        if type(value) is dict:return {k:strip(v) for k,v in value.items() if k not in ('traceback','traceback_text','traceback_frames')}
        if type(value) is list:return [strip(v) for v in value]
        return value
    return strip(report)


def compare_saved(config,baseline_dir,candidate_dir,runtime_observer):
    """Caller unlocks this function only after both terminals/reference metadata.

    runtime_observer is the already source-bound worker helper; its unchanged
    canonical_events validates each lifecycle and renames only native tickets.
    """
    a,b=Path(baseline_dir).resolve(),Path(candidate_dir).resolve()
    need(a!=b,'distinct fresh-worker output directories')
    terminals=[_terminal(a/'TERMINAL.json','baseline'),_terminal(b/'TERMINAL.json','normalization_helper')]
    proof=qualify_reference(config)
    for key in CONTROL:need(terminals[0][key]==terminals[1][key],'model/observer changed control: '+key)
    need(terminals[0]['native_fmas']==933888 and terminals[0]['counts']==dict(read=768,memory_response=960,write=192)
         and terminals[0]['scalar_calls']==dict(bf=19968,add=360,mul=612,div=24),'original true M2 work/primitive-count contract')
    need(_probe_semantics(terminals[0]['scalar_probe_report'])==_probe_semantics(terminals[1]['scalar_probe_report']),
         'real scalar exception/value/probe-count qualification differs')
    reference_dir=Path(config['reference_directory'])
    seal=_metadata(config['reference_seal']);prior=_metadata(seal['result']['path'],seal['result']['pin'])
    reference,checked=_load_fields(reference_dir,'REFERENCE',prior['comparison']['reference_capture']['fields'],reference=True)
    expected_output=(reference_dir/'REFERENCE_OUTPUT.u32le').read_bytes();expected_scores=(reference_dir/'REFERENCE_SCORES.u32le').read_bytes()
    need(len(expected_output)==12288 and len(expected_scores)==144,'M2 reference terminal lengths')
    need(_digest(expected_output)==prior['comparison']['output_sha256'] and
         _digest(expected_scores)==prior['comparison']['scores_sha256'],'reference terminal byte identities')
    arms=[];events=[];writes=[]
    for worker_directory,terminal in zip((a,b),terminals):
        directory=worker_directory/'artifacts'
        actual_output=(directory/'OUTPUT.u32le').read_bytes();actual_scores=(directory/'SCORES.u32le').read_bytes()
        need(actual_output==expected_output and actual_scores==expected_scores,'full output/scores differ from retained independent recipe')
        fields,cells=_load_fields(directory,'CAPTURE',terminal['capture_report']['fields'],reference=False);checked+=cells
        for name in FIELDS:
            need(fields[name]['shape']==reference[name]['shape'] and fields[name]['words']==reference[name]['words']
                 and fields[name]['observed']==reference[name]['observed'],'ten-field retained reference mismatch: '+name)
        words=struct.unpack('<3072I',actual_output);scores=struct.unpack('<36I',actual_scores)
        need(all(words[t*1536+h*128+c]==fields['pv_bf16']['words'][(h*2+t)*128+c]
                 for t in range(2) for h in range(12) for c in range(128)),'published output/PV field layout')
        need(scores==tuple(fields['scores_bf16']['words'][(h*2+t)*2+k]
                           for t in range(2) for h in range(12) for k in range(t+1)),'published score/captured causal score layout')
        arms.append(fields);events.append(runtime_observer.canonical_events(_metadata(directory/'SERVICE_EVENTS.json')))
        writes.append(_metadata(directory/'WRITES.json'))
    for name in FIELDS:need(arms[0][name]['frequency']==arms[1][name]['frequency'],'DUT observation frequency changed: '+name)
    need(events[0]==events[1] and writes[0]==writes[1],'canonical service lifecycle or actual writes changed')
    return dict(status='PASS_TRUE_M2_MODEL_OBSERVER_EQUIVALENCE_WITH_RETAINED_INDEPENDENT_REFERENCE',
                rows=2,fields=10,field_cells_checked=checked,output_words=3072,score_words=36,
                output_sha256=_digest(expected_output),scores_sha256=_digest(expected_scores),
                service_events=len(events[0]),ticket_policy='original lifecycle validator; native ticket first-appearance alpha-renaming only',
                scalar_probe_comparison='return words or exception category/message and separate counts, not traceback',
                field_artifacts=dict(reference={n:reference[n]['artifact'] for n in FIELDS},
                                     baseline={n:arms[0][n]['artifact'] for n in FIELDS},
                                     normalization_helper={n:arms[1][n]['artifact'] for n in FIELDS}),
                reference_qualification=proof,reference_executed_now=False,fullblock=False,
                Scala_correspondence_proved=False,performance_adopted=False)
