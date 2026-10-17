import argparse,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
REL=Path('rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv')
def compose():
 old=(P/'baseline/front_control.sv').read_text();begin=(P/'begin_fix/source'/REL).read_text();final=(P/'reserved_fix/source'/REL).read_text()
 import re
 undo=begin.replace('quiescent,begin_quiescent,','quiescent,').replace('&&begin_quiescent;','&&quiescent;')
 undo=re.sub(r'    // BEGIN valid already.*?    assign identity_matches=', '    assign identity_matches=',undo,flags=re.S)
 if undo!=old:raise ValueError('begin exact delta')
 undo=final
 for name in ['seed_beat_ready_o','seed_commit_ready_o']:
  a=f'assign {name}=reserved_q&&!ack_valid_q&&!poison_q&&!seed_abort_i&&begin_quiescent;'
  if undo.count(a)!=1:raise ValueError('reserved exact statement')
  undo=undo.replace(a,a.replace('&&begin_quiescent;','&&quiescent;'))
 if undo!=begin:raise ValueError('reserved exact delta')
 return final
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();s=compose()
 if a.out.exists() or a.out.is_symlink():raise ValueError('fresh output required')
 a.out.mkdir(parents=True);f=a.out/REL;f.parent.mkdir(parents=True);f.write_text(s);print(hashlib.sha256(f.read_bytes()).hexdigest())
