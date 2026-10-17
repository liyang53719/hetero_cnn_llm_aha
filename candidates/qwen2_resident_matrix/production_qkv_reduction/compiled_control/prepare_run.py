"""Create a fresh runnable source tree and regenerate metadata tables; no hardware."""
import argparse,shutil
from pathlib import Path
from generate_fixtures import generate
HERE=Path(__file__).resolve().parent
def run(source_root,out):
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 out.mkdir(parents=True)
 for p in HERE.iterdir():
  if p.name in ['fixtures','__pycache__']:continue
  if p.is_dir():shutil.copytree(p,out/p.name)
  elif p.is_file():shutil.copyfile(p,out/p.name)
 generate(source_root,out/'fixtures')
 print('PASS_RUN_SOURCE_PREPARATION no hardware execution')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.source_root,a.out)
