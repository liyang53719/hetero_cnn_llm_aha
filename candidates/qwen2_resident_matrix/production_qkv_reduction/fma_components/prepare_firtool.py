"""Extract one pinned official binary without executing it or accessing network."""
import argparse,hashlib,json,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent
def prepare(archive,out):
 pins=json.loads((P/'TOOL_PINS.json').read_text())
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>64*1024**2:raise ValueError('archive type/limit')
 raw=archive.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pins['archive_sha256']:raise ValueError('archive identity')
 with zipfile.ZipFile(archive) as z:
  name='org.chipsalliance/llvm-firtool/linux-x64/bin/firtool'
  if z.namelist().count(name)!=1 or z.getinfo(name).file_size>32*1024**2:raise ValueError('member count/size')
  data=z.read(name)
 if hashlib.sha256(data).hexdigest()!=pins['firtool_sha256']:raise ValueError('binary identity')
 with out.open('xb') as f:f.write(data)
 out.chmod(0o700)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();prepare(a.archive,a.out)
