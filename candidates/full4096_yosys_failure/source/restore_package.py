"""Restore official data bytes only. Never execute/install downloaded files."""
from pathlib import Path
import hashlib,json,urllib.request
H=Path(__file__).resolve().parent
url='https://deb.debian.org/debian/pool/main/y/yosys/yosys_0.52-2_amd64.deb'
expected='c950e58a1f554546a91602e5124eb05019a92040e57b0aaa43cf33b032ee9c40';size=6226136
p=H/'yosys_0.52-2_amd64.deb'
if p.exists():raise ValueError('no overwrite')
try:
 with urllib.request.urlopen(url,timeout=30) as r:b=r.read(size+1)
 if len(b)!=size or hashlib.sha256(b).hexdigest()!=expected:raise ValueError('official package bytes/hash mismatch')
 with p.open('xb') as f:f.write(b)
 p.chmod(0o444)
 out=dict(status='RESTORED_OFFICIAL_PACKAGE_BYTES_ONLY_NOT_EXECUTED',url=url,bytes=size,sha256=expected,source='https://packages.debian.org/trixie/amd64/yosys/download',installed=False,executed=False)
except Exception as e:out=dict(status='RESTORE_NOT_COMPLETED',url=url,error=type(e).__name__+': '+str(e),executed=False)
(H/'PACKAGE_RESTORE.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
