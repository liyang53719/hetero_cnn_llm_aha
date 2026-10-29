"""Read-only GitHub acquisition of the original iDMA source artifact; never reruns CI.
Requires existing GH_TOKEN supplied by authorized job; no credential handling.
Run under the outer supervisor; all evidence and data stay job-local.
"""
import argparse,hashlib,json,pathlib,subprocess
from provider_artifact_gate import check,ARTIFACT
from verify_extract_artifact import run as extract
REPO='liyang53719/hetero_cnn_llm_aha'
def main():
 a=argparse.ArgumentParser();a.add_argument('--gh',type=pathlib.Path,required=True);a.add_argument('--gh-sha256',required=True);a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--execute-reviewed-acquisition',action='store_true');v=a.parse_args()
 with v.gh.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 if h!=v.gh_sha256:raise ValueError('GH executable source binding drift')
 if not v.execute_reviewed_acquisition:raise ValueError('Explicit acquisition mode required, no implicit network')
 if v.output.exists():raise ValueError('Fresh destination required')
 v.output.mkdir();base=f'repos/{REPO}/actions/artifacts/{ARTIFACT}'
 m=subprocess.run([str(v.gh),'api',base],check=True,capture_output=True,timeout=30)
 if len(m.stdout)>65536:raise ValueError('metadata cap')
 meta=json.loads(m.stdout);check(meta);(v.output/'metadata.json').write_bytes(m.stdout)
 archive=v.output/'original-artifact.zip'
 with archive.open('xb') as f:subprocess.run([str(v.gh),'api',base+'/zip'],check=True,stdout=f,timeout=180)
 check(meta,archive)
 result=extract(archive,v.output/'extracted')
 (v.output/'SOURCE_RECEIPT.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
