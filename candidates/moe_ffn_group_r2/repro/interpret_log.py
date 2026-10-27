"""Inspect the included immutable log only; never launch a DUT or rewrite old results."""
from pathlib import Path
import hashlib,json,re
def need(ok,message):
 if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def parse(raw,b):
 text=raw.decode('utf-8');clean=re.sub(r'\x1b\[[0-9;]*m','',text)
 need('\x1b' not in clean,'unknown terminal control')
 lines=clean.splitlines();need(len(lines)==11 and all(x==x.strip() for x in lines),'exact11 reporter lines')
 headers=['Run starting. Expected test count is: 3',b['suite'].split('.')[-1]+':',b['behavior']]
 need(lines[:3]==headers,'exact single suite and behavior')
 need(len(b['selected_test_texts'])==3 and len(set(b['selected_test_texts']))==3,'exact unique selection')
 need(b['selected_full_names']==[b['behavior']+' should '+x for x in b['selected_test_texts']],'full names binding')
 rows=[]
 for line,name,full in zip(lines[3:6],b['selected_test_texts'],b['selected_full_names']):
  match=re.fullmatch(r'- should '+re.escape(name)+r' \(([0-9][0-9a-z ,]*)\)',line)
  need(match is not None,'exact should-prefixed selected reporter line')
  need(lines.count(line)==1,'case exactly once')
  rows.append({'full_test_name':full,'reporter_line':line,'duration_reporter_text':match.group(1)})
 need(re.fullmatch(r'Run completed in [0-9][0-9a-z ,]*\.',lines[6]) is not None,'run completion')
 need(lines[7:]==['Total number of tests run: 3','Suites: completed 1, aborted 0','Tests: succeeded 3, failed 0, canceled 0, ignored 0, pending 0','All tests passed.'],'exact complete aggregate')
 need(b['excluded_test_text'] not in clean,'excluded long case')
 return rows

if __name__=="__main__":
 root=Path(__file__).resolve().parents[1]
 b=json.loads((root/"repro/TEST_SELECTION.json").read_text())
 raw=(root/"actual/short_control.log").read_bytes()
 need(sha(raw)=="e5be95a562a92f310dc279403af2d542c479084a629b474ea9a62b9dea7fc7d1","original log hash")
 rows=parse(raw,b)
 print(json.dumps({"original_wrapper_qualified":False,"original_wrapper_exit":1,"existing_log_case_count":len(rows),"cases":rows,"target_rerun":False},indent=2))
