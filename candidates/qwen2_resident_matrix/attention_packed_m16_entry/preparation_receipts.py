"""Hash-bound caller/launcher/reference chain. No producer or native execution."""
from pathlib import Path
from ..attention_packed_m16_assets import reuse as R
from ..attention_packed_m16_assets_launch import receipt
from . import contract
HERE=Path(__file__).resolve().parent

def provenance():
 value=R.strict_json((HERE/'provenance.json').read_bytes())
 receipt.exact(value,('schema','profile','preparation_contract_sha256','references_sha256',
  'launch_receipt_sha256','preparation_summary_sha256','supervisor_sha256','compile_receipt_sha256',
  'library_sha256','reference_verifier_sha256','numerical_acceptance'))
 R.need(type(value['schema']) is int and value['schema']==1 and value['profile']==contract.PROFILE and
  value['numerical_acceptance'] is False and all(R.digest(v) for k,v in value.items() if k.endswith('_sha256')),
  'reviewed completed preparation identities')
 return value

def read_pointer(pointer,expected):
 receipt.exact(pointer,('path','sha256'))
 R.need(pointer['sha256']==expected and R.digest(expected),'exact executed receipt identity')
 path=R.safe_path(pointer['path'])
 with path.open('rb') as stream:raw=stream.read(R.MAX_JSON+1)
 R.need(len(raw)<=R.MAX_JSON and R.sha(raw)==expected,'same-byte executed receipt binding')
 return path,R.strict_json(raw)

def validate_terminal(supervisor,summary,launch,pins):
 # Their complete bytes are already pinned; independently check the successful
 # terminal links and canonical control fields before deriving child exit0.
 R.need(supervisor['status']=='OBSERVED_ZERO_REFERENCE_LAUNCHER_EXIT' and
  supervisor['observation']=='tool_terminal_result' and
  type(supervisor['outer_exit_code']) is int and supervisor['outer_exit_code']==0 and
  type(supervisor['child_exit_code']) is int and supervisor['child_exit_code']==0 and
  supervisor['cleanup_complete'] is True and supervisor['numerical_acceptance'] is False and
  supervisor['ready_for_actual'] is False,'observed successful caller exit required')
 R.need(supervisor['summary_sha256']==pins['preparation_summary_sha256'] and
  supervisor['launch_receipt_sha256']==pins['launch_receipt_sha256'] and
  supervisor['reference_receipt_sha256']==pins['references_sha256'],'caller receipt links')
 R.need(summary['status']=='COMPLETE_REFERENCE_PREPARATION_ONLY' and summary['phase']=='complete' and
  type(summary['child_exit_code']) is int and summary['child_exit_code']==0 and summary['cleanup_complete'] is True and
  summary['numerical_acceptance'] is False and summary['ready_for_actual'] is False and
  summary['launch_receipt_sha256']==pins['launch_receipt_sha256'] and summary['receipt_sha256']==pins['references_sha256'],
  'successful supervisor summary required')
 R.need(launch['status']=='VALIDATED_REFERENCE_CHILD_EXIT_ONLY' and launch['caller_must_observe_launcher_exit'] is True and
  type(launch['child']['returncode']) is int and launch['child']['returncode']==0 and
  launch['child']['cleanup_complete'] is True and launch['numerical_acceptance'] is False and
  launch['ready_for_actual'] is False and launch['references']['sha256']==pins['references_sha256'],
  'linked child terminal required')
 R.need(all(x['contract_sha256']==pins['preparation_contract_sha256'] for x in (supervisor,summary,launch)),
  'same executed preparation contract')

def verify(manifest):
 contract.snapshot();pins=provenance()
 R.need(manifest['library']['receipt']['sha256']==pins['compile_receipt_sha256'] and
  manifest['library']['sha256']==pins['library_sha256'],'reviewed combined ELF identity')
 ref_path,references=read_pointer(manifest['references'],pins['references_sha256'])
 launch_path,launch=read_pointer(manifest['preparation_launch'],pins['launch_receipt_sha256'])
 summary_path,summary=read_pointer(manifest['preparation_summary'],pins['preparation_summary_sha256'])
 supervisor_path,supervisor=read_pointer(manifest['supervisor'],pins['supervisor_sha256'])
 workspace=launch_path.parent
 R.need(summary_path==workspace/'summary.json' and supervisor_path==workspace/'SUPERVISOR.json' and
  launch_path==workspace/'LAUNCH_RECEIPT.json' and
  R.checked(workspace,launch['references'],content=True)==ref_path,'one completed preparation workspace')
 validate_terminal(supervisor,summary,launch,pins)
 R.need(R.same(launch['asset_source_sha256'],R.snapshot()) and
  launch['origin_commit']==R.contract()['origin_commit'],'original asset sources and Git provenance')
 verifier_path=contract.ROOT/'candidates/qwen2_resident_matrix/attention_packed_m16_assets_launch/receipt.py'
 R.need(Path(receipt.__file__).resolve()==verifier_path and R.file_hash(verifier_path)==pins['reference_verifier_sha256'],
  'exact executed reference verifier')
 origin=R.safe_path(manifest['origin'],directory=True)
 context=receipt.read_record(workspace,launch['context'])
 marker=receipt.read_record(workspace,launch['child']['completion_marker'])
 R.need(context['origin']==str(origin) and marker['status']=='CHILD_REFERENCE_PREPARATION_COMPLETE' and
  type(marker['pid']) is int and marker['pid']==launch['child']['pid'] and
  marker['receipt_sha256']==pins['references_sha256'] and R.same(marker['asset_source_sha256'],R.snapshot()),
  'private context/child completion binding')
 verified=receipt.validate(origin,ref_path.parent,child_returncode=supervisor['child_exit_code'],
  sources=R.snapshot(),origin_before=references['origin'])
 R.need(R.same(verified,launch['verification']),'authentic artifact revalidation')
 return ref_path.parent,references
