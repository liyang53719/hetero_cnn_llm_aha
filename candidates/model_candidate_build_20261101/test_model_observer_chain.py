"""Selected-source preservation only; synthetic path overlay tests never prove RTL."""
import copy,hashlib,json,os,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path(os.environ.get('MODEL_OBSERVER_ROOT',str(D.parents[1]))).resolve()
OVERLAY='candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json'
CHANGED={'GdnRuntimeRmsNormOwnerV3.scala','HostBlockTopV4.scala','HostRuntimePrefixLeaseWiringV8.scala','Qwen2Block.scala','QwenOwnerProtocol.scala','UnifiedMoeSharedArithmeticAdapterV5.scala','UnifiedMoeSharedArithmeticProtocolV5.scala'}
SIX={'FfnResidentCoordinator.scala','FfnTileSiluBridge.scala','HostBlockCommandsV4.scala','UnifiedMoeRouterNumericalOwnerV2.scala','UnifiedMoeRouterPipelineBindingV2.scala','UnifiedMoeRuntimeExpertLoopV4.scala'}
TOP_LINES=('val residentObservation=Output(Valid(new FfnResidentObservation))','val rawScoreObservation=Output(Valid(new UnifiedMoeRouterScoreObservationV1))','io.residentObservation:=owner.io.residentObservation','io.residentObservation.bits.profile:=cmd.io.observationProfile','io.rawScoreObservation:=moeLoop.io.rawScoreObservation')
OWNER_LINES=('val residentObservation=Output(Valid(new FfnResidentObservation))','io.residentObservation.valid:=false.B','io.residentObservation.bits:=0.U.asTypeOf(new FfnResidentObservation)','resident.foreach(r=>io.residentObservation:=r.io.observation)')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def fixtures():
 raw=(D/'fixtures/OBSERVER_BASELINE_155.json').read_bytes();need(sha(raw)=='9be7810a372572e87b40d86d0b30245140c31cd40cdd6cf2f9cacead459beda2','baseline fixture hash')
 obs=(D/'fixtures/OBSERVER_FIELDS_37.json').read_bytes();need(sha(obs)=='dea7b8c076a03182b61363f1fcc7ac7ed4f29ae7d4f722cecaa29550358c78ef','observer fixture hash')
 return json.loads(raw),json.loads(obs)
def check(root,overlay=None,read=None):
 # Optional overlay/read are explicit in-memory test seams, never execution authority.
 root=pathlib.Path(root);read=read or(lambda rel:(root/rel).read_bytes());overlay=overlay or json.loads(read(OVERLAY));base,obs=fixtures()
 rows=overlay['files'];need(len(rows)==159 and len({r['name']for r in rows})==159,'exact159 selected names');selected={r['name']:r for r in rows};old={r['name']:r for r in base['files']}
 need(set(overlay['changed_names'])==CHANGED and overlay['base_overlay_sha256']=='9be7810a372572e87b40d86d0b30245140c31cd40cdd6cf2f9cacead459beda2','actual observer baseline')
 texts={}
 for name,row in selected.items():
  rel=pathlib.Path(row['repo_path']);need(not rel.is_absolute()and '..'not in rel.parts,'selected relative source');raw=read(str(rel));need((len(raw),sha(raw))==(row['bytes'],row['sha256']),'selected source pin '+name);texts[name]=raw.decode()
 preserved=set(old)-CHANGED;need(len(preserved)==148 and SIX<=preserved,'148 + observer6 preservation')
 for name in preserved:
  need(selected[name]['repo_path']==old[name]['repo_path']and(selected[name]['bytes'],selected[name]['sha256'])==(old[name]['bytes'],old[name]['sha256']),'original unchanged source '+name)
 top=texts['HostBlockTopV4.scala'];start=top.index('  val io=IO(new Bundle {');end=top.index('  dontTouch(io)',start)
 need(sha(top[start:end].encode())=='764217ac9f10fbad97713c4f887a6419210f04945cd907373a29fbff35a01afb','complete original Top IO block')
 for line in TOP_LINES:need(sum(x.strip()==line for x in top.splitlines())==1,'unique actual Top observation '+line)
 for line in OWNER_LINES:need(sum(x.strip()==line for x in texts['QwenOwnerProtocol.scala'].splitlines())==1,'unique actual Owner observation '+line)
 portsraw=read('candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json');need(sha(portsraw)=='289f230ec8fc85e7aee0396ab34424f505855074a762707e874fbf8a2f45ca08','complete fixed122 typed contract')
 ports=json.loads(portsraw);need(len(ports)==122 and {k:v for k,v in ports.items()if k.startswith(('io_residentObservation','io_rawScoreObservation'))}==obs,'exact37 observer typed fields')
 driver=read('candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp');need(sha(driver)=='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61','unchanged actual observer driver')
 return True
class Tests(unittest.TestCase):
 def synthetic_restore(self):
  overlay=json.loads((ROOT/OVERLAY).read_text());override={}
  restore=os.environ.get('MODEL_OBSERVER_RESTORE')
  if restore:
   for row in overlay['files']:
    p=pathlib.Path(restore)/row['repo_path']
    if row['name']in('HostBlockTopV4.scala','QwenOwnerProtocol.scala'):
     raw=p.read_bytes();override[row['repo_path']]=raw;row.update(bytes=len(raw),sha256=sha(raw))
  return overlay,override
 def check_fixture(self,overlay,override):return check(ROOT,overlay,lambda rel:override.get(rel)if rel in override else(ROOT/rel).read_bytes())
 def test_selected_or_explicit_synthetic_restoration(self):
  overlay,override=self.synthetic_restore();self.assertTrue(self.check_fixture(overlay,override))
 def test_original_unrestored_rejected(self):
  overlay,override=self.synthetic_restore();row=next(r for r in overlay['files']if r['name']=='HostBlockTopV4.scala');raw=override.get(row['repo_path'],(ROOT/row['repo_path']).read_bytes())
  for line in TOP_LINES[:2]:raw=raw.replace((line+'\n').encode(),b'\n')
  override[row['repo_path']]=raw;row.update(bytes=len(raw),sha256=sha(raw))
  with self.assertRaisesRegex(ValueError,'Top IO block'):self.check_fixture(overlay,override)
  if os.environ.get('MODEL_OBSERVER_RESTORE'):
   with self.assertRaisesRegex(ValueError,'Top IO block'):check(ROOT)
 def test_semantic_deletions_rejected_even_with_updated_source_pin(self):
  for name,line in [('HostBlockTopV4.scala',TOP_LINES[3]),('QwenOwnerProtocol.scala',OWNER_LINES[1]),('HostBlockTopV4.scala',TOP_LINES[1])]:
   with self.subTest(line=line):
    overlay,override=self.synthetic_restore();row=next(r for r in overlay['files']if r['name']==name);raw=override.get(row['repo_path'],(ROOT/row['repo_path']).read_bytes());raw=raw.replace((line+'\n').encode(),b'\n');override[row['repo_path']]=raw;row.update(bytes=len(raw),sha256=sha(raw))
    with self.assertRaises(ValueError):self.check_fixture(overlay,override)
 def test_observer6_cannot_be_rebased_silently(self):
  overlay,override=self.synthetic_restore();row=next(r for r in overlay['files']if r['name']=='UnifiedMoeRouterNumericalOwnerV2.scala');raw=(ROOT/row['repo_path']).read_bytes()+b'// synthetic drift\n';override[row['repo_path']]=raw;row.update(bytes=len(raw),sha256=sha(raw))
  with self.assertRaisesRegex(ValueError,'original unchanged source'):self.check_fixture(overlay,override)
 def test_one_typed_observer_lost_rejected(self):
  overlay,override=self.synthetic_restore();rel='candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json';ports=json.loads((ROOT/rel).read_text());del ports['io_rawScoreObservation_valid'];override[rel]=json.dumps(ports).encode()
  with self.assertRaisesRegex(ValueError,'typed contract'):self.check_fixture(overlay,override)
if __name__=='__main__':unittest.main()
