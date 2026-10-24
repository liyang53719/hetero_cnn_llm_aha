"""Generate only small successor metadata; never copy inputs or materialize a run.

The caller supplies the exact predecessor assembly directory. This reads pinned
source/metadata files only, not staged tensor payloads or run evidence. Output is
an incomplete assembly plan, not an actual-ready candidate or admission.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
OWNER = 'candidates/qwen2_fixed93_attention/owner.py'
SCALA = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read_pinned(root, relative, expected):
    need(type(relative) is str and relative and not Path(relative).is_absolute() and
         '..' not in Path(relative).parts, 'relative source metadata path required')
    path = root / relative
    need(path.resolve() == path and not any(p.is_symlink() for p in (path,*path.parents)), 'source metadata alias')
    with os.fdopen(os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK), 'rb') as stream:
        before=os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=2**20, 'bounded regular metadata/source')
        raw=stream.read(2**20+1);after=os.fstat(stream.fileno())
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    need(stamp(before)==stamp(after)==stamp(path.stat()) and pin(raw)==expected, 'pinned metadata/source drift: '+relative)
    return raw


def validate_inventory_contract(inventory):
    need(type(inventory) is dict and inventory.get('evidence_contract') == CONTRACT,
         'algorithm inventory must use the current evidence contract')


def build(baseline, output):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,
         'use python -I -S -B')
    baseline, output = Path(baseline).absolute(), Path(output).absolute()
    need(baseline.resolve()==baseline and output.resolve()==output and not output.exists(), 'canonical fresh metadata output required')
    need(output != baseline and baseline not in output.parents and output not in baseline.parents,
         'metadata output must not overlap predecessor')
    inputs=json.loads((HERE/'INPUT_PINS.json').read_bytes())
    base={name:read_pinned(baseline,name,spec) for name,spec in inputs['baseline'].items()}
    overlay={name:read_pinned(HERE/'overlay',name,spec) for name,spec in inputs['overlay'].items()}
    validate_inventory_contract(json.loads(overlay['integration/EVIDENCE_INVENTORY.json']))
    old=json.loads(base['SOURCE_MANIFEST.json'])
    # The historical production manifest is pinned as provenance only. New
    # production pins come from current top, excluding its own future digest.
    prod=json.loads(base['SOURCE_MANIFEST.json'])
    prod['preparation_files'].pop('PRODUCTION_SOURCE_MANIFEST.json',None)
    metadata={}
    anchors=json.loads(base['capture/anchors.json'])
    owner_raw=overlay['source/'+OWNER]
    owner_tree=ast.parse(owner_raw)
    owner_class=next(n for n in owner_tree.body if isinstance(n,ast.ClassDef) and n.name=='Fixed93AttentionOwner')
    for label,method in (('owner_attention','_attention'),('owner_tick','tick')):
        node=next(n for n in owner_class.body if isinstance(n,ast.FunctionDef) and n.name==method)
        anchors[label].update(firstlineno=node.lineno,end_lineno=node.end_lineno,sha256=pin(owner_raw)['sha256'])
    metadata['capture/anchors.json']=encoded(anchors)
    capacity=json.loads((HERE/'CAPACITY_PROPOSAL.json').read_bytes())
    metadata['contract/PV_REUSE_CAPACITY.json']=encoded(capacity)
    budget=json.loads(base['BUDGET_PROPOSAL.json'])
    caps=capacity['preserved_old_slack_proposal']
    budget.update(status='OPEN_PV_REUSE_BUDGET_PENDING_COMBINED_REVIEW',actual_execution_authorized=False,
                  approval_scope='Numeric capacity delta only; new combined source/cold review and root authority still required',
                  output_bytes=caps['owned_output_bytes'],startup_available_bytes_required=caps['startup_available_bytes_required'])
    budget['attention_trace_limits']['schema']='fixed93-attention-pv-reuse-trace-limits-v1'
    budget['attention_trace_limits']['codec_limits'].update({k:caps[k] for k in ('max_records','max_raw','max_output')})
    budget['owned_reservation_components']['attention_stream']=caps['max_output']
    budget['capacity_source_binding']=dict(path='contract/PV_REUSE_CAPACITY.json',**pin(metadata['contract/PV_REUSE_CAPACITY.json']))
    need(sum(budget['owned_reservation_components'].values())==budget['output_bytes'],'complete owned component sum')
    need(budget['output_bytes']+budget['free_space_margin_bytes']==budget['startup_available_bytes_required'],'reserve sum')
    for trace in (budget['wholeblock_trace_limits']['codec'],budget['attention_trace_limits']['codec_limits']):
        need(198+trace['max_raw']+trace['max_records']*(88+trace['max_metadata'])<=trace['max_output']<=budget['file_bytes'], 'raw fallback capacity')
    metadata['BUDGET_PROPOSAL.json']=encoded(budget)
    new_observer=json.loads(base['observation/SOURCE_MANIFEST.json'])
    new_observer={k:new_observer[k] for k in ('source_bytes','source_sha256')}
    new_observer.update(schema='fixed93-pv-reuse-observation-source-plan-v1',status='SOURCE_PREPARED_REVIEW_SEPARATE',
                        fullblock_executed=False,native_executed=False,numerical_acceptance=False,
                        old_pass_inherited=False,old_cold_evidence_is_historical=True)
    for name in ('fullblock_attention.py','source_guard.py','event_stream.py'):
        value=pin(overlay['observation/'+name]);new_observer['source_bytes'][name]=value['bytes'];new_observer['source_sha256'][name]=value['sha256']
    metadata['observation/SOURCE_MANIFEST.json']=encoded(new_observer)
    bounds=json.loads(base['observation/RESOURCE_BOUNDS.json'])
    bounds['normal_success_event_prediction']['pv_boundary_records']=3269376
    bounds['normal_success_total_event_prediction']=15164937
    bounds['normalization_evaluations_per_causal_key']=1
    bounds['probability_fp32_uses_per_causal_key']=8
    bounds['normalization_reuses_per_causal_key']=7
    bounds['source_prediction_only']=True
    metadata['observation/RESOURCE_BOUNDS.json']=encoded(bounds)
    for manifest in (old,prod):
        manifest.update(schema='fixed93-pv-reuse-source-manifest-v1',candidate_identity='fixed93-pv-normalization-reuse-source-candidate-v1',
                        candidate_review_status='SOURCE_PREPARED_REVIEW_SEPARATE',evidence_contract=CONTRACT,
                        reviewed_manifest_sha256=None,predecessor_reviewed_manifest_sha256='26928f829488600765cefa2d836f4afe32413e03798ae0eb958bfd016994e13d',
                        status='SOURCE_PLAN_NOT_COMBINED_REVIEWED',old_pass_inherited=False,
                        historical_nonruntime_nested_manifests={'capture/SOURCE_MANIFEST.json':'HISTORICAL_INNER_PINS_NOT_CURRENT; current capture files are pinned by this outer manifest'},
                        actual_execution_authorized=False,native_executed=False,M128_executed=False)
        for relative,hkey,skey,name in (('source/'+OWNER,'source_sha256','source_bytes',OWNER),('selected/'+SCALA,'selected_source_sha256','selected_source_bytes',SCALA)):
            value=pin(overlay[relative]);manifest[hkey][name]=value['sha256'];manifest[skey][name]=value['bytes']
    binding=json.loads(base['source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json'])
    mapping={name:dict(bytes=old['source_bytes'][name],sha256=sha) for name,sha in old['source_sha256'].items()}
    binding['source_closure_sha256']=hashlib.sha256(json.dumps(mapping,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    binding.update(status='SOURCE_REBINDING_PLAN_NOT_ACTUAL_ADMISSION',old_pass_inherited=False,
                   scope='Unchanged frozen input/reference pins rebound only to exact two-entry source successor; no current acceptance')
    metadata['source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json']=encoded(binding)
    changes={**overlay,**metadata}
    for manifest in (old,prod):
        for name,raw in changes.items():
            if not name.startswith(('source/candidates/','selected/')):
                manifest['preparation_files'][name]=pin(raw)
    metadata['PRODUCTION_SOURCE_MANIFEST.json']=encoded(prod)
    old['preparation_files']['PRODUCTION_SOURCE_MANIFEST.json']=pin(metadata['PRODUCTION_SOURCE_MANIFEST.json'])
    metadata['SOURCE_MANIFEST.json']=encoded(old)
    # Invoke actual new pure closure guards, never preflight or DUT modules.
    namespace={'__name__':'_source_plan_checks','__file__':str(HERE/'overlay/assembly_preflight.py')}
    exec(compile(overlay['assembly_preflight.py'],namespace['__file__'],'exec',dont_inherit=True),namespace)
    namespace['validate_successor_identity'](old)
    expected=namespace['successor_assembly'](json.loads(base['ASSEMBLY_BASE.json'])['objects'])
    for directory,hkey,skey,count in (('source','source_sha256','source_bytes',306),('selected','selected_source_sha256','selected_source_bytes',9),('support','support_sha256','support_bytes',6)):
        namespace['validate_successor_domain'](old,expected,directory,hkey,skey,count)
    output.mkdir()
    for name,raw in metadata.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    receipt=dict(status='METADATA_PLAN_ONLY_NO_MATERIALIZED_ASSEMBLY',source_only=True,
                 output_files={name:pin(raw) for name,raw in metadata.items()},exact_changed_assembly_entries=list(namespace['PV_REUSE_DELTA']),
                 unchanged_assembly_entries=319,baseline_manifest=inputs['baseline']['SOURCE_MANIFEST.json'],
                 weights_or_reference_payload_read=False,DUT_imported=False,native_executed=False,
                 actual_authorized=False,source_qualified=False,fullblock_acceptance=False)
    (output/'PLAN_RECEIPT.json').write_bytes(encoded(receipt))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(build(args.baseline,args.output),sort_keys=True))
