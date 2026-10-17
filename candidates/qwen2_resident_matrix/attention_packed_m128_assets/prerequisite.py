"""Successful repaired-M16 caller evidence is a prerequisite, never an M128 verdict."""
from . import origin as O
R=O.R

def verify(root, current_sources):
 pins=O.provenance()['m16_prerequisite']; root=R.safe_path(root,directory=True)
 meta={n:R.read_metadata(root,n,p) for n,p in pins['metadata'].items()}
 actual=meta['actual/summary.json'];summary=meta['summary.json'];caller=meta['SUPERVISOR.json'];snapshot=meta['snapshot/SNAPSHOT.json']
 O.need(caller['status'] == 'OBSERVED_PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY' and
  caller['observation'] == 'tool_terminal_result' and type(caller['outer_exit_code']) is int and
  caller['outer_exit_code'] == 0 and type(caller['child_exit_code']) is int and caller['child_exit_code'] == 0 and
  caller['cleanup_complete'] is True and caller['actual_chain_completion_verified'] is True,
  'authentic repaired M16 caller exit required')
 O.need(summary['status'] == 'PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY' and summary['child_exit_code'] == 0 and
  summary['cleanup_complete'] is True and summary['assigned_official_observed_gates_passed'] is True and
  caller['contract_sha256'] == summary['contract_sha256'] == pins['contract_sha256'], 'M16 completed prerequisite links')
 O.need(caller['private_actual_summary_sha256'] == summary['validation']['summary_sha256'] == pins['metadata']['actual/summary.json']['sha256'] and
  caller['summary_sha256'] == pins['metadata']['summary.json']['sha256'] and
  actual['snapshot_sha256'] == pins['metadata']['snapshot/SNAPSHOT.json']['sha256'], 'M16 authentic receipt chain')
 O.need(type(actual['rows']) is int and actual['rows'] == 16 and
  actual['status'] == 'PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES' and actual['actual_dataflow_pass'] is True and
  actual['native_acceptance'] == 'PASS_OBSERVED_ONLY' and actual['old_pass_inherited'] is False,
  'repaired M16 exact actual result scope')
 O.need(all(x['full_29_node_acceptance'] is False for x in (actual,summary,caller)) and
  caller['assigned_official_gates'] == summary['validation']['assigned_official_gates'] == 27 and
  caller['official_observed_stages'] == 28 and caller['public_completions'] == 21 and caller['owner_jobs'] == 17,
  'M16 original assigned gate and Public scope')
 O.need(R.same(actual['source_sha256'],actual['source_sha256_after']) and
  R.same(actual['source_sha256'],snapshot['source_sha256']) and
  R.sha(R.encoded(actual['source_sha256'])) == pins['source_manifest_sha256'] ==
  summary['source_manifest_sha256'] == caller['source_manifest_compact_sha256'], 'M16 source before/after identity')
 for name,digest in pins['compatible_source_sha256'].items():
  O.need(actual['source_sha256'].get(name) == current_sources.get(name) == digest,
   'M16/M128 unchanged arithmetic, owner, services or storage source differs: '+name)
 lib=O.provenance()['library'];built=actual['binaries']
 O.need(built['compile_sha256'] == lib['receipt_sha256'] and built['library_sha256'] == lib['sha256'],
  'M16 qualified combined library identity')
 return dict(root=str(root),metadata_sha256={n:p['sha256'] for n,p in pins['metadata'].items()},
  compatible_source_sha256=pins['compatible_source_sha256'],m16_completion_verified=True,
  m128_verdict_inherited=False,old_pass_inherited=False,full_29_node_acceptance=False)
