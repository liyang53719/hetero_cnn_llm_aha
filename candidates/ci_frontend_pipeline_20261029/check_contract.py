"""Source-only policy checks. No network, compilation, process launch or deletion."""
import hashlib,json,pathlib,re,sys
PROFILES=['qwen2_1p5b','qwen35_0p8b_l0','qwen35_0p8b_l3','qwen35_35b_a3b_l0','qwen35_35b_a3b_l3']
SAFE=['summary.json','source_hashes.json','stage_exits.json','profile_results.json','canonical_gate.json','resource_peak.json']
def need(ok,msg):
 if not ok: raise ValueError(msg)
def validate_plan(p):
 need(p['matrix_mac']==4096 and p['vector_lanes']==32,'fixed resources')
 need(p['profiles']==PROFILES and p['tokens']==128,'all five M128 profiles')
 need(p['builds']==1 and p['profile_concurrency']==1,'single binary and serialized resource use')
 need(p['upload_whitelist']==SAFE,'exact safe summary whitelist')
 need(p['timeout_seconds']<=21600,'hosted job limit')
 need(sum(p['disk_caps_bytes'].values())<=14_000_000_000,'14GB decimal advertised storage cap')
 need(p['weights_and_reference_bins']=='job_local_only','no weight/reference upload')
def validate_results(rows):
 need([r['profile'] for r in rows]==PROFILES,'five ordered result identities')
 for k in ['binary_sha256','hardware_source_manifest_sha256','simulation_sv_sha256']:
  vals=[r[k] for r in rows]
  need(all(re.fullmatch('[0-9a-f]{64}',v) for v in vals) and len(set(vals))==1,'one immutable '+k)
 need(all(r['tokens']==128 for r in rows),'M128')
 need(all(r['scope']=='CHISEL_SIMULATION_BACKEND_NOT_FINAL_RTL' for r in rows),'qualification scope')
 need(all(r['status'] in ['PASS','FAIL','INCOMPLETE'] for r in rows),'explicit status')
def verify_upload(root):
 root=pathlib.Path(root)
 need(not root.is_symlink(),'summary dir symlink')
 need(sorted(x.name for x in root.iterdir())==sorted(SAFE),'no extra files')
 for name in SAFE:
  f=root/name;need(f.is_file() and not f.is_symlink() and f.stat().st_size<=262144,'safe file bound')
  json.loads(f.read_text())
 # This only enforces paths/JSON/size, NOT semantic sanitization of arbitrary JSON.
 # A separately reviewed allow-key/type schema per file is mandatory before upload.
 raise ValueError('INCOMPLETE: semantic safe-summary schemas not reviewed; uploading disabled')
if __name__=='__main__':
 p=json.loads((pathlib.Path(__file__).parent/'PLAN.json').read_text());validate_plan(p)
 print('PASS_STATIC_PLAN_CONTRACT_ONLY; NO_EXECUTION')
