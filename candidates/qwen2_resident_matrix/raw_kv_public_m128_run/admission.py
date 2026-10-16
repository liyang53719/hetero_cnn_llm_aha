"""Hash-only linkage of a completed setup to the original public M128 entry.

This gate imports no numerical runtime. It admits the exact committed setup
metadata, not a numerical PASS. The unchanged fresh entry must still verify all
asset bytes and strict ELF provenance inside the supervised venv child.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import stat

from ..raw_kv_public_fresh import assets, setup

PROFILE = 'qwen2-public-linked-m128-admission-v1'
ROWS = 128
SOURCE_COUNT = 221
PHASES = ('preflight','environment','acquisition','references','native16','native128','library','seal')
MAX_SETUP_BYTES = 131072
MAX_PHASE_BYTES = 4096
SETUP_KEYS = frozenset(('schema','profile','status','base_commit','base_profile','base_verifier_sha256',
    'setup_profile_sha256','source_sha256','source_manifest_sha256','asset_source_manifest_sha256',
    'asset_manifest_sha256','enable_raw_kv','rows','past_tokens','workspace','checkout_commit',
    'completed_phases','source_recheck','deadline_monotonic_ns','elapsed_seconds','total_budget_seconds',
    'actual_chain_executed','numerical_acceptance'))
SUMMARY_KEYS = frozenset(('schema','status','phase','elapsed_seconds','completed_phases',
    'total_budget_seconds','cleanup_grace_seconds','actual_chain_executed','numerical_acceptance',
    'source_manifest_sha256','manifest_sha256','reason','source_recheck','setup_profile',
    'setup_profile_sha256','asset_source_manifest_sha256','setup_receipt_sha256'))


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def selected_profile():
    """Only the final launch overlay can interpret this M128 setup credential."""
    from . import launch
    need(setup.PROFILE == launch.SETUP_PROFILE == 'qwen2-public-fresh-m128-setup-v1' and
         assets.PROFILE == 'qwen2-public-pv16-fresh-assets-m128-v1' and
         setup.BASE_COMMIT == launch.BASE_COMMIT and setup.PROFILE_PATH == launch.CONTRACT and
         type(setup.TOTAL_SECONDS) is int and setup.TOTAL_SECONDS == 900 and
         type(setup.CLEANUP_SECONDS) is int and setup.CLEANUP_SECONDS == 5 and
         type(setup.PHASES) is tuple and setup.PHASES == PHASES and
         assets.same(setup.BASE_VERIFIER_SHA256,launch.base_verifier_sources()),
         'linked_m128_launch_profile')
    return launch


def source_snapshot(enabled):
    need(type(enabled) is bool and enabled is True,'linked_request_domain')
    launch = selected_profile()
    expected = launch.contract_snapshot(composed=True)['sources']
    need(type(expected) is dict and len(expected) == SOURCE_COUNT and
         all(type(name) is str and assets.digest(identity) for name,identity in expected.items()),
         'linked_launch_source_closure')
    actual = setup.source_snapshot(enabled)
    need(assets.same(actual,expected),'linked_setup_launch_source_difference')
    need(assets.same(setup.asset_sources(actual),expected),'linked_asset_launch_source_difference')
    return dict(expected)


def _integer(value, *, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0)


def _file_identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


@dataclass(frozen=True)
class ReadIdentity:
    path: Path
    sha256: str
    identity: tuple


def read_json(path, *, limit):
    """Parse only the bounded bytes whose hash and live file identity are kept."""
    path = assets.safe_path(path)
    flags = os.O_RDONLY | getattr(os,'O_NOFOLLOW',0)
    descriptor = os.open(path,flags)
    with os.fdopen(descriptor,'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size <= limit,'linked_metadata_size_or_kind')
        raw = stream.read(limit+1)
        after = os.fstat(stream.fileno())
    need(len(raw) <= limit and len(raw) == before.st_size and _file_identity(before) == _file_identity(after),
         'linked_metadata_changed_during_read')
    need(assets.safe_path(path) == path and _file_identity(path.stat()) == _file_identity(after),
         'linked_metadata_replaced_during_read')
    return assets.json_bytes(raw,limit=limit), ReadIdentity(path,assets.sha(raw),_file_identity(after))


@dataclass(frozen=True)
class Admission:
    workspace: Path
    setup_summary: Path
    checkout_commit: str
    enable_raw_kv: bool
    manifest: Path
    manifest_sha256: str
    library_receipt: Path
    receipt_sha256: str
    summary_sha256: str
    source_manifest_sha256: str
    asset_source_manifest_sha256: str
    setup_profile_sha256: str
    workspace_identity: tuple
    summary_directory_identity: tuple
    linked_files: tuple
    sources: tuple

    @property
    def source_sha256(self):
        return dict(self.sources)

    @property
    def compile_receipt(self):
        return self.library_receipt

    @property
    def setup_receipt_sha256(self):
        return self.receipt_sha256


def validate_linkage(receipt, summary, manifest, *, receipt_sha256, manifest_sha256,
                     workspace, workspace_identity, sources, checkout_commit, enable_raw_kv):
    """Pure metadata contract; callers separately bind actual file bytes/inodes."""
    selected_profile()
    assets.exact(receipt,SETUP_KEYS,'linked_setup_schema')
    assets.exact(summary,SUMMARY_KEYS,'linked_summary_schema')
    need(type(receipt['schema']) is int and receipt['schema'] == 1 and
         receipt['profile'] == setup.PROFILE and receipt['status'] == setup.SETUP_STATUS and
         receipt['base_commit'] == setup.BASE_COMMIT and receipt['base_profile'] == assets.PROFILE and
         assets.same(receipt['base_verifier_sha256'],setup.BASE_VERIFIER_SHA256), 'linked_setup_profile')
    need(type(receipt['rows']) is int and receipt['rows'] == ROWS and
         type(receipt['past_tokens']) is int and receipt['past_tokens'] == 0 and
         type(receipt['enable_raw_kv']) is bool and receipt['enable_raw_kv'] is enable_raw_kv and
         receipt['checkout_commit'] == checkout_commit, 'linked_setup_workload')
    assets.exact(receipt['workspace'],('path','device','inode'),'linked_workspace_schema')
    selected = receipt['workspace']
    need(type(selected['path']) is str and selected['path'] == str(workspace) and
         _integer(selected['device']) and _integer(selected['inode'],positive=True) and
         (selected['device'],selected['inode']) == workspace_identity, 'linked_workspace_identity')
    need(type(receipt['completed_phases']) is list and receipt['completed_phases'] == list(setup.PHASES) and
         receipt['source_recheck'] == 'UNCHANGED' and receipt['actual_chain_executed'] is False and
         receipt['numerical_acceptance'] is False and type(receipt['total_budget_seconds']) is int and
         receipt['total_budget_seconds'] == setup.TOTAL_SECONDS and
         type(receipt['deadline_monotonic_ns']) is int and 0 < receipt['deadline_monotonic_ns'] < 1 << 63 and
         setup.finite(receipt['elapsed_seconds'],setup.TOTAL_SECONDS), 'linked_setup_completion')
    need(type(summary['schema']) is int and summary['schema'] == 1 and summary['status'] == setup.SETUP_STATUS and
         summary['setup_profile'] == setup.PROFILE and summary['phase'] == setup.PHASES[-1] and
         summary['completed_phases'] == list(setup.PHASES) and type(summary['completed_phases']) is list and
         summary['source_recheck'] == 'UNCHANGED' and summary['reason'] == 'fresh_assets_verified' and
         summary['actual_chain_executed'] is False and summary['numerical_acceptance'] is False and
         type(summary['total_budget_seconds']) is int and summary['total_budget_seconds'] == setup.TOTAL_SECONDS and
         type(summary['cleanup_grace_seconds']) is int and summary['cleanup_grace_seconds'] == setup.CLEANUP_SECONDS and
         setup.finite(summary['elapsed_seconds'],setup.TOTAL_SECONDS), 'linked_summary_completion')
    need(type(sources) is dict and len(sources) == SOURCE_COUNT and assets.same(receipt['source_sha256'],sources),
         'linked_setup_source_closure')
    asset_sources = setup.asset_sources(sources)
    source_digest = assets.sha(assets.encoded(sources))
    asset_digest = assets.sha(assets.encoded(asset_sources))
    profile_digest = sources[setup.PROFILE_PATH]
    need(len(asset_sources) == SOURCE_COUNT and assets.same(asset_sources,sources) and receipt['source_manifest_sha256'] == summary['source_manifest_sha256'] == source_digest and
         receipt['asset_source_manifest_sha256'] == summary['asset_source_manifest_sha256'] == asset_digest and
         receipt['setup_profile_sha256'] == summary['setup_profile_sha256'] == profile_digest and
         summary['setup_receipt_sha256'] == receipt_sha256 and
         receipt['asset_manifest_sha256'] == summary['manifest_sha256'] == manifest_sha256,
         'linked_setup_hash_chain')
    assets.validate_manifest(manifest,rows=ROWS)
    need(assets.same(manifest['source_sha256'],asset_sources) and manifest['source_manifest_sha256'] == asset_digest,
         'linked_asset_source_closure')


def verify_setup(workspace, setup_summary, *, checkout_commit, enable_raw_kv=True, rows=128):
    """Require the linked final commit before any numerical entry import/call."""
    need(type(rows) is int and rows == ROWS and type(enable_raw_kv) is bool and enable_raw_kv is True and
         setup.canonical_commit(checkout_commit),'linked_request_domain')
    selected_profile()
    workspace = assets.safe_path(workspace,directory=True)
    summary_path = assets.safe_path(setup_summary)
    summary_directory = assets.safe_path(summary_path.parent,directory=True)
    need(summary_path.name == 'summary.json' and workspace != summary_directory and
         not workspace.is_relative_to(summary_directory) and not summary_directory.is_relative_to(workspace),
         'linked_evidence_workspace_separation')
    workspace_info, summary_info = workspace.stat(), summary_directory.stat()
    workspace_identity = (workspace_info.st_dev,workspace_info.st_ino)
    summary_identity = (summary_info.st_dev,summary_info.st_ino)
    need(workspace_identity != summary_identity,'linked_directory_alias')
    receipt, receipt_read = read_json(workspace/'SETUP.json',limit=MAX_SETUP_BYTES)
    summary, summary_read = read_json(summary_path,limit=setup.MAX_SUMMARY_BYTES)
    # Reject incomplete status/obvious profile substitutions before source work
    # or even opening the ASSETS manifest.
    assets.exact(receipt,SETUP_KEYS,'linked_setup_schema')
    assets.exact(summary,SUMMARY_KEYS,'linked_summary_schema')
    need(receipt['status'] == summary['status'] == setup.SETUP_STATUS and
         receipt['profile'] == summary['setup_profile'] == setup.PROFILE and
         type(receipt['enable_raw_kv']) is bool and receipt['enable_raw_kv'] is enable_raw_kv and
         type(receipt['rows']) is int and receipt['rows'] == ROWS and
         type(receipt['past_tokens']) is int and receipt['past_tokens'] == 0,
         'linked_setup_not_complete')
    manifest, manifest_read = read_json(workspace/'ASSETS.json',limit=assets.MAX_MANIFEST_BYTES)
    assets.validate_manifest(manifest,rows=ROWS)
    sources = source_snapshot(enable_raw_kv)
    validate_linkage(receipt,summary,manifest,receipt_sha256=receipt_read.sha256,
        manifest_sha256=manifest_read.sha256,workspace=workspace,workspace_identity=workspace_identity,
        sources=sources,checkout_commit=checkout_commit,enable_raw_kv=enable_raw_kv)
    linked = [receipt_read,summary_read,manifest_read]
    for phase in setup.PHASES:
        value, observed = read_json(workspace/(phase+'.complete.json'),limit=MAX_PHASE_BYTES)
        expected = dict(schema=1,phase=phase,status='COMPLETE_SETUP_PHASE',
                        source_manifest_sha256=receipt['source_manifest_sha256'])
        if phase == 'seal':
            expected['manifest_sha256'] = manifest_read.sha256
        need(assets.same(value,expected),'linked_phase_receipt')
        linked.append(observed)
    need(len({(item.identity[0],item.identity[1]) for item in linked}) == len(linked),'linked_receipt_inode_alias')
    library_receipt = assets.resolve_artifact(workspace,manifest['library']['receipt'])
    # Metadata record hash only: the original strict verifier performs ELF and
    # installed-tool/runtime checks later inside the supervised numerical child.
    _, library_read = read_json(library_receipt,limit=assets.MAX_METADATA_BYTES)
    need(library_read.sha256 == manifest['library']['receipt']['sha256'],'linked_library_receipt_hash')
    linked.append(library_read)
    need(len({(item.identity[0],item.identity[1]) for item in linked}) == len(linked),'linked_receipt_inode_alias')
    need(assets.same(sources,source_snapshot(enable_raw_kv)), 'linked_source_changed_during_admission')
    for item in linked:
        need(_file_identity(assets.safe_path(item.path).stat()) == item.identity,'linked_metadata_changed_after_admission')
    need((workspace.stat().st_dev,workspace.stat().st_ino) == workspace_identity and
         (summary_directory.stat().st_dev,summary_directory.stat().st_ino) == summary_identity,'linked_directory_replaced')
    return Admission(workspace,summary_path,checkout_commit,enable_raw_kv,manifest_read.path,manifest_read.sha256,
        library_receipt,receipt_read.sha256,summary_read.sha256,receipt['source_manifest_sha256'],
        receipt['asset_source_manifest_sha256'],receipt['setup_profile_sha256'],workspace_identity,summary_identity,
        tuple(linked),tuple(sorted(sources.items())))


admit = verify_setup


def revalidate(admission):
    need(type(admission) is Admission,'linked_admission_type')
    current = verify_setup(admission.workspace,admission.setup_summary,checkout_commit=admission.checkout_commit,
                           enable_raw_kv=admission.enable_raw_kv,rows=ROWS)
    need(current == admission,'linked_admission_drift')
    return current


def safe_identity(admission):
    need(type(admission) is Admission,'linked_admission_type')
    return dict(profile=PROFILE,setup_profile=setup.PROFILE,asset_profile=assets.PROFILE,rows=ROWS,past_tokens=0,
        enable_raw_kv=admission.enable_raw_kv,setup_receipt_sha256=admission.receipt_sha256,
        setup_summary_sha256=admission.summary_sha256,asset_manifest_sha256=admission.manifest_sha256,
        setup_profile_sha256=admission.setup_profile_sha256,source_manifest_sha256=admission.source_manifest_sha256,
        asset_source_manifest_sha256=admission.asset_source_manifest_sha256,source_count=len(admission.sources),
        completed_phase_count=len(setup.PHASES),actual_chain_executed=False,numerical_acceptance=False)
