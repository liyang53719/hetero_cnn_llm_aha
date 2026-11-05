"""Compare future bounded Scala receipts. Does not execute Scala or accept Host."""
import re,hashlib
CASES=('flat','repeated','hash_collision','registered','cycle','invalid_duplicate','packed_alias_cycle','unpacked_alias')
EXPECTED_ERRORS={k:hashlib.sha256(v.encode()).hexdigest() for k,v in {'cycle':'firrtl2.graph.CyclicException','invalid_duplicate':'treadle2.executable.TreadleException','packed_alias_cycle':'firrtl2.graph.CyclicException'}.items()}
HEX='[0-9a-f]{64}'
CASE=re.compile(r'STRUCTURAL_DIFF_CASE_V1 id=([a-z_]+) (GRAPH digest|ERROR classSha)=('+HEX+')')
FINAL=re.compile(r'STRUCTURAL_DIFF_RUN_V1 label=(official|cached) sourceSha=('+HEX+r') classSha=('+HEX+r') companionSha=('+HEX+r') cases=8 keyLaws=PASS numericalPass=false')
def need(ok):
 if not ok:raise ValueError('fixture receipt rejected')
def parse(text,label,expected,process_receipt):
 # The caller must supply independently verified class/source and process pins.
 need(process_receipt=={'exit':0,'errors':[],'cleanup_complete':True,'log_finalized':True})
 need(type(text)is str and text.isascii() and len(text)<=16384 and text.endswith('\n'))
 lines=text.splitlines();need(len(lines)==9)
 cases=[]
 for index,line in enumerate(lines[:-1]):
  m=CASE.fullmatch(line);need(m is not None)
  need(m[1]==CASES[index]);need(m[2]==('ERROR classSha'if m[1] in EXPECTED_ERRORS else'GRAPH digest'))
  if m[1] in EXPECTED_ERRORS:need(m[3]==EXPECTED_ERRORS[m[1]])
  cases.append((m[1],m[2],m[3]))
 m=FINAL.fullmatch(lines[-1]);need(m is not None and m[1]==label)
 need(set(expected)=={'source_sha256','class_sha256','companion_sha256'})
 need(tuple(m.groups()[1:])==tuple(expected[k]for k in ('source_sha256','class_sha256','companion_sha256')))
 return tuple(cases)
def compare(official_text,cached_text,official_pins,cached_pins,official_process,cached_process):
 need(official_pins['source_sha256']!=cached_pins['source_sha256'])
 need(official_pins['companion_sha256']!=cached_pins['companion_sha256'])
 a=parse(official_text,'official',official_pins,official_process)
 b=parse(cached_text,'cached',cached_pins,cached_process)
 need(a==b)
 return {'status':'PASS_SMALL_SCALA_FIXTURE_DIFFERENTIAL_ONLY','cases':8,'key_laws':True,'host_graph_qualified':False,'numerical_pass':False}
