"""Pre-acquisition guard only. Does not fetch, dispatch, or substitute new artifacts."""
import argparse,datetime,hashlib,json,pathlib
ARTIFACT=12099239717
RUN=39030773068
SHA='a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'
EXPIRY='2026-11-16T12:00:15Z'
def check(meta,archive=None):
 if meta.get('id')!=ARTIFACT or meta.get('expired') is not False or meta.get('workflow_run',{}).get('id')!=RUN:raise ValueError('Exact original artifact identity/live metadata required; no rerun')
 expiry=datetime.datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))
 if expiry!=datetime.datetime.fromisoformat(EXPIRY.replace('Z','+00:00')) or datetime.datetime.now(datetime.timezone.utc)>=expiry:raise ValueError('Artifact expiry; source reconstruction required, no implicit rerun')
 if archive is None:return {'status':'ACQUISITION_REQUIRED_WITHIN_EXISTING_AUTHORIZATION','artifact_id':ARTIFACT,'run_id':RUN,'expires_at':EXPIRY,'expected_archive_sha256':SHA}
 p=pathlib.Path(archive)
 if not p.is_file() or p.is_symlink() or p.stat().st_size!=9926876:raise ValueError('Archive size/type')
 with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 if h!=SHA:raise ValueError('Archive hash')
 return {'status':'ARCHIVE_BYTES_ONLY_EXTRACTION_CLOSURE_STILL_REQUIRED','sha256':h}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--metadata',type=pathlib.Path,required=True);a.add_argument('--archive',type=pathlib.Path);v=a.parse_args();print(json.dumps(check(json.loads(v.metadata.read_text()),v.archive),indent=2))
