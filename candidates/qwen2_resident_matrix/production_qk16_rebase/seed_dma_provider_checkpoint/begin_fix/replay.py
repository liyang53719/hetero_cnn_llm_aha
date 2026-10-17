"""Copy the one reviewed endpoint source into a fresh isolated candidate; no EDA."""
import argparse,hashlib,json
from pathlib import Path
P=Path(__file__).resolve().parent
REL=Path('rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv')
def run(source_root,out):
 pins=json.loads((P/'SOURCE_PINS.json').read_text());key=next(n for n in pins if n.endswith(str(REL)))
 if hashlib.sha256((source_root/REL).read_bytes()).hexdigest()!=pins[key]:raise ValueError('original source mismatch')
 if out.exists() or out.is_symlink():raise ValueError('fresh isolated output required')
 out.mkdir(parents=True);target=out/REL;target.parent.mkdir(parents=True);target.write_bytes((P/'source'/REL).read_bytes())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.source_root,a.out)
