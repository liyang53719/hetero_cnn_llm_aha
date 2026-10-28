"""Explicit local parent-input binding. No download, payload embedding or fallback."""
from pathlib import Path
import hashlib,json,os,re
HERE=Path(__file__).resolve().parent
BUNDLED={
 'fdf79e75eccd01f927d2d8f437c204ae70b90ddc2f425c8d87b63bc401e8779c':'input_generator.py',
 '86ad51be3fac1e462676ab3ab22c5b806fa5bb17b9b126e81ff68263740e30eb':'INPUT_RECIPE.json',
}
def path_for_sha(digest,size=None):
 if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('invalid SHA256 identity')
 if size is not None and (type(size) is not int or size<0):raise ValueError('invalid expected size')
 if digest in BUNDLED:p=HERE/BUNDLED[digest]
 else:
  config=os.environ.get('BYTE_PROVIDER_INPUTS')
  if not config:raise ValueError('requires-parent: BYTE_PROVIDER_INPUTS local hash-to-path JSON is required')
  doc=json.loads(Path(config).read_text());value=doc['files'].get(digest)
  if type(value) is not str or not value:raise ValueError('missing exact parent input '+digest)
  p=Path(value)
 if not p.is_file() or (size is not None and p.stat().st_size!=size):raise ValueError('parent file/size mismatch')
 with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 if actual!=digest:raise ValueError('parent source hash mismatch')
 return p.resolve()
