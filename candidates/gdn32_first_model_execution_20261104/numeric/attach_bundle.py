"""NEW bundle only; requires pinned P0 overlay; never mutates old bundle or executes DUT."""
import argparse,copy,json,pathlib
import run_compare as consumer

def assemble(old,policy_pin,evidence_pin):
 consumer.need(old['schema']=='SINGLE_PROFILE_RUNTIME_BUNDLE_V1','original materializer bundle V1 required')
 consumer.need(len(old['profiles'])==1 and old['profiles'][0]['id']==0,'overlay only P0')
 original=old['profiles'][0]
 consumer.need('observation_policy' not in original and 'original_runtime' not in original and 'consumption_evidence' not in original,'no repeat overlay')
 p=consumer.pin(policy_pin);policy=json.loads(p.read_text())
 for sk,bk in [('original_runtime','runtime'),('views','views')]:
  consumer.need(all(policy[sk][k]==original[bk][k] for k in ('path','bytes','sha256')),'policy binds original '+bk)
 result=copy.deepcopy(old);result['schema']='SINGLE_PROFILE_RUNTIME_BUNDLE_V3'
 result['profiles'][0]['original_runtime']=copy.deepcopy(original['runtime'])
 result['profiles'][0]['runtime']={k:policy['corrected_runtime'][k] for k in ('path','bytes','sha256')}
 result['profiles'][0]['observation_policy']=policy_pin
 result['profiles'][0]['consumption_evidence']=evidence_pin
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--original-bundle',type=pathlib.Path,required=True);p.add_argument('--original-bundle-sha256',required=True);p.add_argument('--policy',type=pathlib.Path,required=True);p.add_argument('--policy-sha256',required=True);p.add_argument('--consumption-evidence',type=pathlib.Path,required=True);p.add_argument('--consumption-evidence-sha256',required=True);p.add_argument('--artifact-manifest',type=pathlib.Path,required=True);p.add_argument('--artifact-manifest-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 consumer.verify_frozen(a.original_bundle,a.original_bundle_sha256);consumer.verify_frozen(a.policy,a.policy_sha256)
 consumer.need(a.output.is_absolute() and not a.output.exists() and a.output.parent.resolve()==a.original_bundle.parent.resolve(),'fresh sibling bundle only')
 old=json.loads(a.original_bundle.read_text());policy_pin=dict(path=str(a.policy.resolve()),bytes=a.policy.stat().st_size,sha256=a.policy_sha256)
 consumer.verify_frozen(a.consumption_evidence,a.consumption_evidence_sha256)
 evidence_pin=dict(path=str(a.consumption_evidence.resolve()),bytes=a.consumption_evidence.stat().st_size,sha256=a.consumption_evidence_sha256)
 result=assemble(old,policy_pin,evidence_pin)
 # Staged metadata is explicitly UNADMITTED; final path appears only after the
 # complete consumer common/build-receipt/source/overlay binding validation.
 staged=a.output.with_name(a.output.name+'.UNADMITTED')
 with staged.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 consumer.load_binding(a.artifact_manifest,a.artifact_manifest_sha256,staged,0)
 consumer.verify_frozen(a.original_bundle,a.original_bundle_sha256);consumer.verify_frozen(a.policy,a.policy_sha256)
 import os
 os.link(staged,a.output) # atomic no-clobber publication of this job-local metadata
 staged.unlink() # same verified bytes now retained at the final sibling path
 print('NEW_BUNDLE_METADATA_ONLY_REQUIRED_GATES_INCOMPLETE_NO_DUT')
if __name__=='__main__':main()
