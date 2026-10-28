from pathlib import Path
import argparse,json,hashlib
C=Path(__file__).resolve().parent; W=C.parent
parser=argparse.ArgumentParser()
parser.add_argument('--original-rawprep-source',type=Path,required=True)
old=parser.parse_args().original_rawprep_source
r=json.loads((C/'SOURCE_PINS.json').read_text())['original_rawprep'];raw=old.read_bytes()
if len(raw)!=r['bytes'] or hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('exact original RawPrep source required')
new=C/'source/GdnRuntimeRawPrepOwnerV7.scala'
a='head(4).asUInt.pad(66)'; b='head(4,4).pad(66)'
def need(v,m):
 if not v:raise ValueError(m)
s=old.read_text(); t=new.read_text();need(s.count(a)==1,'single old expression');need(t.count(b)==1 and a not in t,'exact explicit UInt slice');need(t.replace(b,a)==s,'only one expression changed')
cases=0
for base in [0,64,4096,(1<<56)-128]:
 for head in range(32):
  bit=(head>>4)&1; slice_value=(head>>4)&((1<<1)-1)
  need(base+(bit<<6)==base+(slice_value<<6),'address equivalence');cases+=1
# Source checker rejects deleted change, changed bit, changed shift and extra edits.
for bad in [t.replace(b,a),t.replace(b,'head(3,3).pad(66)'),t.replace(b,'head(4,4).pad(65)'),t+'\n//unreviewed\n']:
 need(not (bad.count(b)==1 and a not in bad and bad.replace(b,a)==s),'mutation rejected')
print(json.dumps({'status':'PASS_SOURCE_AND_INTEGER_MODEL_ONLY','address_cases':cases,'negative_classes':4,'not_Chisel_elaboration':True,'source_sha256':hashlib.sha256(new.read_bytes()).hexdigest()}))
