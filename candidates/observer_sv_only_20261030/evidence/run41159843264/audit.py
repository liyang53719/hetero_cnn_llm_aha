if not __debug__:
 raise RuntimeError('Audit requires assertion-enabled Python; optimized mode rejected')
import pathlib,json,hashlib,importlib.util
D=pathlib.Path(__file__).resolve().parent
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--source-root',required=True);parser.add_argument('--frontend-metadata',required=True);args=parser.parse_args()
R=pathlib.Path(args.source_root).resolve()
Q=R/'candidates/observer_sv_only_20261030'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
s=load(D/'sv-only-summary.json');p=load(D/'sv-only-proof.json')
assert sha(Q/'SOURCE_PINS.json')==s['source_pins_sha256']=='a81ece66d5e70cdcbcc83ee138090f2422b67d79c945cf3b681dd48e77e537dd'
pins=load(Q/'SOURCE_PINS.json')['files'];assert len(pins)==676
for x in pins: assert (R/x['path']).stat().st_size==x['bytes'] and sha(R/x['path'])==x['sha256'],x['path']
f=Q/'sv_difference_projection.py';assert sha(f)==p['projection_source_sha256']=='52cc6957f9d8492dc6b039ede139041c0f9098d4f6ee689b12f8dd873abb5318'
spec=importlib.util.spec_from_file_location('projection',f);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);assert m.project_proof(p)==p
identity=dict(run_id=41159843264,artifact_name='hetero-observer-sv-only-summary-41159843264',source_commit='c312f2ee0a3ccbf23d898f0d8fe9142dedab8cd8',launch_commit='b845ae540e073130b5565bb6f71b0f534f59bb72',launch_manifest_path='ci_launch/observer_fixed4096_sv_only_difference_20261031_fileinfo_once.json',launch_manifest_blob_sha='d82231341c1ae6d27edbfbd41fd0e8aa92d80482');assert s['artifact_identity']==identity
assert s['proof_file']==dict(name='sv-only-proof.json',bytes=(D/'sv-only-proof.json').stat().st_size,sha256=sha(D/'sv-only-proof.json'))
names=['jdk','jars']+[side+'_'+x for side in ('old','new') for x in ('compile155','helper_compile','original_ir','canonical','emit_sv','svscan')]+['projection']
assert [x['name']for x in s['stages']]==names
for x in s['stages']:
 assert x['native_exit']==0 and x['error_count']==0 and x['error_categories']=={}
 assert all(x[k] is True for k in ('cleanup_complete','pipe_eof_observed','gzip_finalized','strict_complete'))
 assert x['elapsed_seconds']<x['wall_cap_seconds'] and x['observed_peak_rss']<=x['rss_cap_bytes']
for k in ('numerical_pass','archive_link_executed','verilator_gcc_executed','final_rtl_replay','sv_repin_authorized'):assert s[k] is False
assert s['full_m128_pass_count']==0
assert s['observed_canonical_sha256']==s['expected_canonical_sha256']
assert s['observed_normalized_sha256']==s['expected_normalized_sha256']
for side in ('old','new'):
 assert p['full_sv'][side]['normalized_sha256']==s['observed_normalized_sha256'][side]
 assert p['full_sv'][side]['scan_receipt_sha256']==next(x['result_sha256']for x in s['stages']if x['name']==side+'_svscan')
oldpath=R/'candidates/ci_frontend_materialization_r2_20261029/C7_MODULE_FINGERPRINTS.json';assert sha(oldpath)=='0d80da62c042b5da4f2879525d4660df957579a169295a5844deb0d953f2067a'
newpath=pathlib.Path(args.frontend_metadata);assert sha(newpath)=='510fa27c03b7db63bfaa364fb7334cbcff52398ee930f025a0f3862417b7cbf1'
a=load(oldpath)['modules'];sv=load(newpath)['sv'];b=sv['modules'];assert len(a)==len(b)==92 and [x['module']for x in a]==[x['module']for x in b]
changed=sorted(x['module']for x,y in zip(a,b)if x['normalized_sha256']!=y['normalized_sha256'])
expected=sorted(['HostBlockCommandsV4','FfnTileSiluBridge','FfnResidentCoordinator','QwenOwnerKernel','UnifiedMoeRouterNumericalOwnerV2','UnifiedMoeRouterPipelineBindingV2','UnifiedMoeRuntimeExpertLoopV4','HostBlockTopV4'])
assert changed==sorted(expected+list(m.MODULES))
assert sv['raw_sha256']==p['full_sv']['new']['raw_sha256'] and sv['normalized_sha256']==p['full_sv']['new']['normalized_sha256']
for name in m.MODULES:
 for side,rows in [('old',a),('new',b)]:assert next(x['normalized_sha256']for x in rows if x['module']==name)==p['modules'][name][side]['normalized_module_sha256']
out=dict(status='PASS_ACTUAL_TWO_MODULE_61BIT_NORMALIZED_BYTE_PROJECTION_ONLY',artifact_identity=identity,zip_sha256='950e3b29ff109bbd1738782c07cda817ac4a4b6b89d67e2b9f476b10d0582a64',summary_sha256=sha(D/'sv-only-summary.json'),proof_sha256=sha(D/'sv-only-proof.json'),source_pins_sha256=s['source_pins_sha256'],source_pin_count=len(pins),strict_stages=len(names),full_sv=p['full_sv'],canonical=s['observed_canonical_sha256'],module_order_unchanged=True,normalized_unchanged_modules=82,expected_observer_changes=expected,additional_two_modules_proved=list(m.MODULES),remaining_bytes_compared=True,scope='Exact actual whole hashes bind prior 92-module metadata; only additional two modules have strict deletion proof, eight observer changes retain separately audited source scope, not general equivalence.',production_gate_updated=False,sv_repin_automatically_authorized=False,full_m128_pass_count=0,final_rtl_replay=False)
assert load(D/'INDEPENDENT_AUDIT.json')==out;print(json.dumps(out,indent=2))
