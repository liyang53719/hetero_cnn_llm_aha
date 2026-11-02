"""Read-only, explicitly reviewed host-only executor source adaptation.

The external adaptation pin must come from the trusted invocation, not from this
JSON itself. Builder source/ELF/SV/driver remain immutable. A different executor
commit is disclosed and its complete catalog must differ by exactly the reviewed
host-only allowlist. An identical builder/executor commit instead requires exact
complete catalog equality and an independently reviewed empty diff. Neither
branch nor a source review is numerical PASS.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

D = Path(__file__).resolve().parent
PREFIX = 'candidates/same_job_execution_20261030/'
ADAPTER_PATH = PREFIX + 'executor_adaptation.py'
CATALOG_PATH = PREFIX + 'SOURCE_PINS.json'
# No build producer, Scala, C++, SV, reference math, original input transformer
# or stimulus source may change through this host adapter. The exact host-only
# P0 data-reuse wrapper paths below require independent source/data review.
ALLOWED_PATHS = frozenset(PREFIX + x for x in (
    'test_model_candidate_inputs.py',
    'evidence/first_fault_summary_join_20261102/README_CN.md',
    'evidence/first_fault_summary_join_20261102/SYNTHETIC_FULL_SUMMARY_JOIN.json',
    'evidence/first_fault_summary_join_20261102/test_full_summary_join.py',
    'numeric/FIXED_NONHIER_SCHEMA.json',
    'numeric/candidate_admission.py',
    'numeric/candidate_artifact_handoff.py',
    'numeric/first_fault_driver_contract.py',
    'numeric/terminal_finite_records.py',
    'numeric/test_terminal_finite_records.py',
    'numeric/test_terminal_contract_summary.py',
    'numeric/fixtures/readonly_first_fault_v1.hpp',
    'numeric/first_fault_records.py',
    'numeric/p0_first_fault_contract.py',
    'numeric/test_first_fault_contract.py',
    'numeric/test_first_fault_gate_paths.py',
    'numeric/test_first_fault_p0_reuse.py',
    'numeric/test_first_fault_records.py',
    'numeric/test_support_first_fault.py',
    'test_first_fault_controller.py',
    'test_first_fault_execution.py',
    'test_first_fault_pipeline_join.py',
    'test_first_fault_real_join.py',
    'test_first_fault_summary_projection.py',
    'test_profile_policy.py',
    'runtime/test_cloud_runtime.py',
    'evidence/reference_data_reuse_20261101/README_CN.md',
    'evidence/reference_data_reuse_20261101/SAFE_EVIDENCE.json',
    'evidence/reference_data_reuse_20261101/run_all_reference_links.py',
    'evidence/reference_data_reuse_20261101/run_reference_pure_chain.py',

    'test_reference_tree_budget.py',
    'numeric/reference_data_reuse.py',
    'numeric/test_reference_data_reuse.py',
    'numeric/test_reference_numeric.py',
    'numeric/locked_phase.py',
    'numeric/live_budget.py',

    'test_stage_document.py',
    'evidence/p0_data_reuse_20261101/README_CN.md',
    'evidence/p0_data_reuse_20261101/SAFE_EVIDENCE.json',
    'evidence/p0_data_reuse_20261101/negative_checks.py',
    'evidence/p0_data_reuse_20261101/run_pure_chain.py',
    'numeric/test_support_p0_reuse.py',
    'numeric/test_p0_provider_data_reuse.py',
    'numeric/fixtures/p0_reuse/program_commands.hex',
    'numeric/fixtures/p0_reuse/program_descriptors.hex',
    'numeric/fixtures/p0_reuse/program_manifest',
    'numeric/fixtures/p0_reuse/source_config',
    'numeric/fixtures/p0_reuse/source_convert',
    'numeric/fixtures/p0_reuse/source_emit',
    'numeric/fixtures/p0_reuse/source_pack',
    'numeric/fixtures/p0_reuse/source_rebuild',
    'numeric/fixtures/p0_reuse/source_reconstruct',
    'test_stage_coverage.py',
    'test_stage_summary.py',
    'numeric/test_stage_numeric.py',
    'numeric/provider_from_frozen.py',
    'numeric/p0_provider_data_reuse.py',
    'numeric/emit_reused_p0_tsv.py',
    'numeric/test_p0_reuse_wiring.py',
    'evidence/contract_domain_20261101/ACTUAL_PURE_CHAIN_SAFE_RESULT.json',
    'evidence/contract_domain_20261101/PURE_CHAIN_README.md',
    'evidence/contract_domain_20261101/reproduce_pure_chain.py',
    'numeric/candidate_observation_contract.py',
    'numeric/test_candidate_observation_contract.py',
    'execution_mode.py', 'test_candidate_full_budget.py', 'test_disk_receipt.py', 'numeric/test_contract_domains.py',
    'cloud_budget.py', 'prepare_cloud_execution.py', 'controller/cloud_flow.py',
    'summarize_cloud_execution.py', 'executor_adaptation.py',
    'numeric/test_p0_source_relocation.py', 'test_backend_baseline_join.py',
    'numeric/artifact_handoff.py', 'numeric/runtime_abi_owned.py',
    'numeric/consumer_owned.py', 'numeric/numeric_tail.py', 'numeric/connect_owned.py',
    'numeric/driver_dependency_proof.py', 'numeric/consumption_proof.py',
    'numeric/observation_contract.py', 'numeric/CONNECTION_OWNED_SOURCE_PINS.json',
    'numeric/workspace_loader.py', 'test_executor_adaptation.py',
    'numeric/test_artifact_handoff.py',
    'runtime/retained_materials.py', 'runtime/test_retained_materials.py',
    'controller/flow.py', 'runtime/runtime_reuse.py', 'runtime/install_job.py',
    'runtime/test_supervisor_return.py', 'runtime/test_install_supervisor_return.py',
    'test_stage_return_retention.py', 'numeric/test_prelaunch.py',
    'test_cloud_budget.py', 'test_cloud_controller.py', 'test_cloud_flow_mock.py',
    'acceptance_tests/test_cloud_summary.py', 'acceptance_tests/test_original_initialize.py', 'acceptance_tests/test_lifecycle.py', 'acceptance_tests/test_main_mock.py',
    'acceptance_tests/test_split_consumer_cli.py', 'acceptance_tests/test_consumer_memory.py',
    'numeric/test_builder_tool_paths.py', 'numeric/test_make_recipe_grammar.py',
    'numeric/ACTUAL_MAKE_CHECKER_REVIEW.json', 'numeric/test_workspace_loader.py',
    'numeric/test_workspace_abi_adapter.py', 'numeric/test_owned_abi_environment.py',
    'test_common_observer_integration.py', 'WORKSPACE_EXECUTOR_ADAPTATION.zh.md',
)) | {'plans/CURRENT_HARDWARE_FIVE_BLOCK_PARALLEL_20261026_ZH.md',
       'candidates/same_job_materialization_20261029/REPO_DEPENDENCIES.json',
       'candidates/same_job_materialization_20261029/CONNECTION_SOURCE_PINS.json'}
BUILDER_FIELDS = {'run_id', 'artifact_name', 'source_commit', 'launch_commit',
                  'launch_manifest_path', 'launch_manifest_blob_sha'}


def need(value, message):
    if not value:
        raise ValueError(message)


def hex_value(value, count):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(count) + '}', value) is not None


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def regular(path, cap):
    p = Path(path)
    need(p.is_absolute() and p == p.resolve() and
         all(not q.is_symlink() for q in (p, *p.parents)) and p.is_file(),
         'canonical regular adaptation input')
    need(0 < p.stat().st_size <= cap, 'bounded adaptation input')
    return p


def pin(path):
    p = Path(path)
    return dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p))


def checked(value, cap=2 << 20):
    need(type(value) is dict and set(value) == {'path', 'bytes', 'sha256'},
         'exact independent adaptation input pin')
    need(type(value['bytes']) is int and 0 < value['bytes'] <= cap and
         hex_value(value['sha256'], 64), 'bounded independently pinned bytes')
    p = regular(value['path'], cap)
    need(pin(p) == value, 'independent adaptation input byte mismatch')
    return p


def relative(value):
    need(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./+\-]+', value) and
         not value.startswith('/') and value == PurePosixPath(value).as_posix() and
         all(x not in ('', '.', '..') for x in value.split('/')),
         'canonical source-relative path')
    return value


def catalog(value):
    path = checked(value)
    doc = json.loads(path.read_text())
    need(type(doc) is dict and set(doc) in ({'schema', 'files'}, {'schema', 'original_source_commit', 'files'}) and
         doc['schema'] == 'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1' and
         ('original_source_commit' not in doc or hex_value(doc['original_source_commit'], 40)),
         'source catalog schema')
    need(type(doc['files']) is list and 0 < len(doc['files']) <= 4096,
         'bounded complete source catalog')
    rows = {}
    for row in doc['files']:
        need(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'},
             'exact source catalog row')
        name = relative(row['path'])
        need(name != CATALOG_PATH and name not in rows, 'unique non-self-referential source catalog')
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= 32 << 20 and
             hex_value(row['sha256'], 64), 'bounded source file pin')
        rows[name] = row
    return rows


def changes_sha256(changes):
    return hashlib.sha256(json.dumps(changes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify(adaptation_pin, builder_identity, executor_identity,
           current_source_pins_pin=None, repo=None):
    path = checked(adaptation_pin)
    doc = json.loads(path.read_text())
    fields = {'schema', 'scope', 'builder_identity', 'executor_source_commit',
              'artifact_manifest_sha256', 'builder_source_pins', 'executor_source_pins',
              'review', 'changes', 'numerical_pass'}
    need(type(doc) is dict and set(doc) == fields and
         doc['schema'] == 'HOST_ONLY_EXECUTOR_ADAPTATION_V1' and
         doc['scope'] == 'FROZEN_BUILDER_BYTES_HOST_EXECUTOR_ONLY' and
         doc['numerical_pass'] is False, 'explicit host-only adaptation scope')
    need(type(builder_identity) is dict and set(builder_identity) == BUILDER_FIELDS and
         type(builder_identity['run_id']) is int and builder_identity['run_id'] > 0 and
         all(hex_value(builder_identity[k], 40) for k in
             ('source_commit', 'launch_commit', 'launch_manifest_blob_sha')) and
         isinstance(builder_identity['artifact_name'], str) and
         re.fullmatch('[A-Za-z0-9_.-]{1,128}', builder_identity['artifact_name']) and
         isinstance(builder_identity['launch_manifest_path'], str) and
         re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json', builder_identity['launch_manifest_path']) and
         builder_identity['source_commit'] != builder_identity['launch_commit'],
         'actual distinct builder six-field identity')
    need(doc['builder_identity'] == builder_identity, 'adaptation belongs to exact actual builder')
    need(type(executor_identity) is dict and hex_value(executor_identity.get('source_commit'), 40) and
         doc['executor_source_commit'] == executor_identity['source_commit'],
         'truthful executor source commit')
    same_source = doc['executor_source_commit'] == builder_identity['source_commit']
    need(hex_value(doc['artifact_manifest_sha256'], 64), 'frozen artifact manifest identity')
    old = catalog(doc['builder_source_pins'])
    new = catalog(doc['executor_source_pins'])
    current = current_source_pins_pin if current_source_pins_pin is not None else pin(D / 'SOURCE_PINS.json')
    checked(current)
    need(current == doc['executor_source_pins'], 'actual executor catalog not a substitute catalog')
    root = Path(repo) if repo is not None else D.parent.parent
    need(root.is_absolute() and root == root.resolve() and root.is_dir() and
         all(not p.is_symlink() for p in (root, *root.parents)), 'canonical executor checkout')
    need(Path(current['path']) == root / CATALOG_PATH, 'catalog belongs to actual executor checkout')
    for name, row in new.items():
        p = root / name
        need(p.is_file() and all(not q.is_symlink() for q in (p, *p.parents)) and
             p.stat().st_size == row['bytes'] and sha(p) == row['sha256'],
             'current executor source byte mismatch')
    need(ADAPTER_PATH in new and new[ADAPTER_PATH]['sha256'] == sha(__file__),
         'this exact checker is in the reviewed executor closure')
    calculated = []
    for name in sorted(set(old) | set(new)):
        if old.get(name) == new.get(name):
            continue
        need(name in ALLOWED_PATHS, 'non-host source change forbidden: ' + name)
        need(name in new, 'host adapter source deletion not admitted')
        old_sha = old[name]['sha256'] if name in old else None
        new_sha = new[name]['sha256']
        need(old_sha != new_sha, 'catalog size drift without source change')
        calculated.append(dict(path=name, old_sha256=old_sha, new_sha256=new_sha))
    # A newly built artifact may already contain the reviewed host adapter.
    # Do not manufacture a second commit just to use its exact loader closure.
    # Same-source admission requires identical complete catalog bytes, no diff,
    # and the same independent review binding as the distinct-source branch.
    if same_source:
        need(not calculated and old == new and
             doc['builder_source_pins']['sha256'] == doc['executor_source_pins']['sha256'],
             'same-source requires identical complete catalogs and empty diff')
    else:
        need(bool(calculated), 'distinct-source requires actual reviewed host diff')
    need(type(doc['changes']) is list and doc['changes'] == calculated,
         'exact complete reviewed source diff required')
    review_path = checked(doc['review'], 65536)
    review = json.loads(review_path.read_text())
    expected_review = dict(schema='HOST_ONLY_EXECUTOR_ADAPTATION_REVIEW_V1',
        status='SOURCE_ONLY_GO_NOT_NUMERICAL',
        builder_source_commit=builder_identity['source_commit'],
        executor_source_commit=executor_identity['source_commit'],
        builder_source_pins_sha256=doc['builder_source_pins']['sha256'],
        executor_source_pins_sha256=doc['executor_source_pins']['sha256'],
        artifact_manifest_sha256=doc['artifact_manifest_sha256'],
        changes_sha256=changes_sha256(calculated), numerical_pass=False)
    need(review == expected_review, 'independent review binds exact catalogs and complete diff')
    # Recheck the inputs after all source reads; no mutable catalog joins.
    for row in (adaptation_pin, doc['builder_source_pins'], doc['executor_source_pins'], doc['review']):
        checked(row)
    return dict(status='VERIFIED_HOST_ONLY_SOURCE_ADAPTATION_NOT_NUMERICAL',
        builder_source_commit=builder_identity['source_commit'],
        executor_source_commit=executor_identity['source_commit'],
        builder_source_pins_sha256=doc['builder_source_pins']['sha256'],
        executor_source_pins_sha256=doc['executor_source_pins']['sha256'],
        artifact_manifest_sha256=doc['artifact_manifest_sha256'],
        adaptation_sha256=adaptation_pin['sha256'], review_sha256=doc['review']['sha256'],
        changes_sha256=changes_sha256(calculated), changed_paths=[x['path'] for x in calculated],
        numerical_pass=False)
