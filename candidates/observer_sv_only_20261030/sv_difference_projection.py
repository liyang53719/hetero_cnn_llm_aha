"""Two specific unchanged-HIGH modules only. No generic logic deletion/renaming.
Full old/new SV identities are independently fixed before strict normalized-byte projection.
No emit, elaboration, subprocess, network, frontend or numerical qualification.
"""
import argparse,hashlib,io,json,pathlib,re,struct,sys,tempfile
P=pathlib.Path
SCANNER='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
FULL={'old':'6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5','new':'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72'}
INSTANCE_LABELS_SHA='4cc62a5acb5a4b0a572f18a2fb9d6117b4900795f6091c21c5d80b84b07eb165'
COLLECTOR_SHA='9295a2affa25970812a8b71d096b81be925facb0918223747df91b16a113cfb8'
MODULES=('Public21QkvReductionRouter','TransposedDenseDownOwner')
FIELDS=(('identity',32),('slot',2),('ng',16),('index',11))
MOD_NORMALIZED={
 'old':{'Public21QkvReductionRouter':'1e87261c949e8fe372f64ec54886aa597479cb1e6b23ab6c4311242c6b71271d','TransposedDenseDownOwner':'e07f04f309da1a58a528082ab327d0f361dd117eb8fbc4bc878b4b15faa9b78f'},
 'new':{'Public21QkvReductionRouter':'4a11a5c08ef38434ecf827120e6627b96f9537049ed0ca7eaaef24a7954b973e','TransposedDenseDownOwner':'d26f8e11bcd4e663774f921d38e22d442faf176657067401001d0fd7cd5f8a6f'}}
# Diagnostic state contains finite identifiers and already observed bounded scalars only.
REJECTION_CODES={'SV line cap': 'REJECT_SV_LINE_CAP', 'SV source changed during proof': 'REJECT_SV_SOURCE_CHANGED_DURING_PROOF', 'actual complete92 modules': 'REJECT_ACTUAL_COMPLETE92_MODULES', 'actual completed source-pinned scan': 'REJECT_ACTUAL_COMPLETED_SOURCE_PINNED_SCAN', 'actual selected module fingerprint': 'REJECT_ACTUAL_SELECTED_MODULE_FINGERPRINT', 'assign deletion must be unconditional module-level lexical code': 'REJECT_ASSIGN_DELETION_MUST_BE_UNCONDITIONAL_MODULE_LEVEL_LEXICAL_CODE', 'balanced preprocessor conditional': 'REJECT_BALANCED_PREPROCESSOR_CONDITIONAL', 'bounded actual SV file': 'REJECT_BOUNDED_ACTUAL_SV_FILE', 'bounded emitter line': 'REJECT_BOUNDED_EMITTER_LINE', 'bounded original scan stage receipt': 'REJECT_BOUNDED_ORIGINAL_SCAN_STAGE_RECEIPT', 'bounded proof export': 'REJECT_BOUNDED_PROOF_EXPORT', 'bounded proof integer': 'REJECT_BOUNDED_PROOF_INTEGER', 'bounded proof metadata': 'REJECT_BOUNDED_PROOF_METADATA', 'bounded whole scanner metadata': 'REJECT_BOUNDED_WHOLE_SCANNER_METADATA', 'complete emitter header': 'REJECT_COMPLETE_EMITTER_HEADER', 'complete same named module': 'REJECT_COMPLETE_SAME_NAMED_MODULE', 'complete source read': 'REJECT_COMPLETE_SOURCE_READ', 'complete supported lexical/preprocessor structure': 'REJECT_COMPLETE_SUPPORTED_LEXICAL_PREPROCESSOR_STRUCTURE', 'complete92 metadata': 'REJECT_COMPLETE92_METADATA', 'direct streamed byte equality required': 'REJECT_DIRECT_STREAMED_BYTE_EQUALITY_REQUIRED', 'duplicate projected assign': 'REJECT_DUPLICATE_PROJECTED_ASSIGN', 'duplicate projected port': 'REJECT_DUPLICATE_PROJECTED_PORT', 'endmodule without module': 'REJECT_ENDMODULE_WITHOUT_MODULE', 'exact actual full scanner command': 'REJECT_EXACT_ACTUAL_FULL_SCANNER_COMMAND', 'exact complete added key ports': 'REJECT_EXACT_COMPLETE_ADDED_KEY_PORTS', 'exact complete direct key assigns': 'REJECT_EXACT_COMPLETE_DIRECT_KEY_ASSIGNS', 'exact direct key forwarder': 'REJECT_EXACT_DIRECT_KEY_FORWARDER', 'exact key port direction/width': 'REJECT_EXACT_KEY_PORT_DIRECTION_WIDTH', 'exact narrow proof scope': 'REJECT_EXACT_NARROW_PROOF_SCOPE', 'exact projected direct assigns': 'REJECT_EXACT_PROJECTED_DIRECT_ASSIGNS', 'exact projected key ports': 'REJECT_EXACT_PROJECTED_KEY_PORTS', 'exact proof fields': 'REJECT_EXACT_PROOF_FIELDS', 'exact remaining byte comparison differs': 'REJECT_EXACT_REMAINING_BYTE_COMPARISON_DIFFERS', 'exact retained final emitter port': 'REJECT_EXACT_RETAINED_FINAL_EMITTER_PORT', 'existing nonprojected port required': 'REJECT_EXISTING_NONPROJECTED_PORT_REQUIRED', 'fixed complete normalizedSV identity': 'REJECT_FIXED_COMPLETE_NORMALIZEDSV_IDENTITY', 'header buffer cap': 'REJECT_HEADER_BUFFER_CAP', 'independently known full normalized identity bound actual raw file': 'REJECT_INDEPENDENTLY_KNOWN_FULL_NORMALIZED_IDENTITY_BOUND_ACTUAL_RAW_FILE', 'known actual selected module identity': 'REJECT_KNOWN_ACTUAL_SELECTED_MODULE_IDENTITY', 'location-sensitive macro not admitted': 'REJECT_LOCATION_SENSITIVE_MACRO_NOT_ADMITTED', 'module line-object memory bound': 'REJECT_MODULE_LINE_OBJECT_MEMORY_BOUND', 'nested module': 'REJECT_NESTED_MODULE', 'new key remains in unprojected logic/port': 'REJECT_NEW_KEY_REMAINS_IN_UNPROJECTED_LOGIC_PORT', 'no numerical or auto-repin claim': 'REJECT_NO_NUMERICAL_OR_AUTO_REPIN_CLAIM', 'nonprojected normalized SV byte difference: reject': 'REJECT_NONPROJECTED_NORMALIZED_SV_BYTE_DIFFERENCE_REJECT', 'normalized module cap': 'REJECT_NORMALIZED_MODULE_CAP', 'normalized module96MiB cap': 'REJECT_NORMALIZED_MODULE96MIB_CAP', 'old module unexpectedly contains projected assignment': 'REJECT_OLD_MODULE_UNEXPECTEDLY_CONTAINS_PROJECTED_ASSIGNMENT', 'old module unexpectedly contains projected port': 'REJECT_OLD_MODULE_UNEXPECTEDLY_CONTAINS_PROJECTED_PORT', 'old side unmodified': 'REJECT_OLD_SIDE_UNMODIFIED', 'only actual removed final port leaves allowed comma': 'REJECT_ONLY_ACTUAL_REMOVED_FINAL_PORT_LEAVES_ALLOWED_COMMA', 'only original recognized SourceInfo comment on removed line': 'REJECT_ONLY_ORIGINAL_RECOGNIZED_SOURCEINFO_COMMENT_ON_REMOVED_LINE', 'only two reviewed module names': 'REJECT_ONLY_TWO_REVIEWED_MODULE_NAMES', 'original exact scanner source': 'REJECT_ORIGINAL_EXACT_SCANNER_SOURCE', 'original observed scanner contract': 'REJECT_ORIGINAL_OBSERVED_SCANNER_CONTRACT', 'port deletion must be unconditional lexical code': 'REJECT_PORT_DELETION_MUST_BE_UNCONDITIONAL_LEXICAL_CODE', 'proof digest': 'REJECT_PROOF_DIGEST', 'remaining normalized bytes exactly same': 'REJECT_REMAINING_NORMALIZED_BYTES_EXACTLY_SAME', 'removed final port lacks preceding separator': 'REJECT_REMOVED_FINAL_PORT_LACKS_PRECEDING_SEPARATOR', 'removed no-comma final key port must be last': 'REJECT_REMOVED_NO_COMMA_FINAL_KEY_PORT_MUST_BE_LAST', 'reviewed exact algorithms': 'REJECT_REVIEWED_EXACT_ALGORITHMS', 'reviewed exact instance label classifier': 'REJECT_REVIEWED_EXACT_INSTANCE_LABEL_CLASSIFIER', 'reviewed scanner collector/current Python': 'REJECT_REVIEWED_SCANNER_COLLECTOR_CURRENT_PYTHON', 'same actual module fingerprint': 'REJECT_SAME_ACTUAL_MODULE_FINGERPRINT', 'same complete92 module order': 'REJECT_SAME_COMPLETE92_MODULE_ORDER', 'selected module bound': 'REJECT_SELECTED_MODULE_BOUND', 'token bound': 'REJECT_TOKEN_BOUND', 'unknown lexical byte before projection': 'REJECT_UNKNOWN_LEXICAL_BYTE_BEFORE_PROJECTION', 'unrecognized SV lexical byte': 'REJECT_UNRECOGNIZED_SV_LEXICAL_BYTE', 'unterminated/unknown SV lexical suffix': 'REJECT_UNTERMINATED_UNKNOWN_SV_LEXICAL_SUFFIX'}
PHASES=('START','INPUT_BINDING','EXTRACT_MODULES','NORMALIZE_MODULE','PROJECT_MODULE','COMPARE_MODULE','RECHECK_INPUTS','PROJECT_PROOF','WRITE_PROOF')
PROGRESS_KEYS=('line_number','lexical_byte_offset','normalized_module_bytes','projected_normalized_bytes','removed_ports','removed_assignments','removed_sourceinfo_comments','normalized_module_sha256','projected_normalized_sha256')
PROGRESS_CAPS={k:(1500001 if k=='line_number'else 96*1024**2 if k=='lexical_byte_offset'else 512*1024**2 if k.endswith('bytes')else 16)for k in PROGRESS_KEYS if not k.endswith('sha256')}
DIAGNOSTIC={}
def reset_diagnostic():
 DIAGNOSTIC.clear();DIAGNOSTIC.update(phase='START',module=None,kind=None,saturated_fields=[],full_sv={'old':None,'new':None},progress={k:None for k in PROGRESS_KEYS},comparison={'old':None,'new':None,'projected_bytes_equal':None,'projected_sha256_equal':None})
def diagnostic_context(phase,module=None,kind=None):
 comparison=DIAGNOSTIC['comparison']if module is not None and DIAGNOSTIC.get('module')==module else {'old':None,'new':None,'projected_bytes_equal':None,'projected_sha256_equal':None}
 DIAGNOSTIC.update(phase=phase,module=module,kind=kind,saturated_fields=[],progress={k:None for k in PROGRESS_KEYS},comparison=comparison)
def diagnostic_progress(**values):
 saturated=set(DIAGNOSTIC['saturated_fields'])
 for k,v in values.items():
  if k in PROGRESS_CAPS and type(v)is int and not 0<=v<=PROGRESS_CAPS[k]:
   DIAGNOSTIC['progress'][k]=None;saturated.add(k)
  else:
   DIAGNOSTIC['progress'][k]=v
   if v is not None:saturated.discard(k)
 DIAGNOSTIC['saturated_fields']=sorted(saturated)
def diagnostic_comparison(rows):
 result={'old':None,'new':None,'projected_bytes_equal':None,'projected_sha256_equal':None}
 for side,row in rows.items():
  result[side]=dict(normalized_module_sha256=row.get('normalized_module_sha256'),projected_normalized_sha256=row['projected_normalized_sha256'],projected_normalized_bytes=row['projected_normalized_bytes'],removed_ports=len(row['removed_ports']),removed_assignments=len(row['removed_assignments']),removed_sourceinfo_comments=row['removed_sourceinfo_comments'])
 if result['old']is not None and result['new']is not None:
  result['projected_bytes_equal']=result['old']['projected_normalized_bytes']==result['new']['projected_normalized_bytes']
  result['projected_sha256_equal']=result['old']['projected_normalized_sha256']==result['new']['projected_normalized_sha256']
 DIAGNOSTIC['comparison']=result
class ProjectionRejected(ValueError):
 def __init__(self,code):self.reason_code=code;super().__init__(code)
reset_diagnostic()
def need(v,s):
 if not v:raise ProjectionRejected(REJECTION_CODES.get(s,'UNCLASSIFIED_CONTRACT_REJECTION'))
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Bounded lexical context recognition only; NOT an equivalence normalizer. All
# lexical classes locate code-state only; remaining-byte identity does not
# serialize or normalize these tokens or assume a complete SV operator grammar.
LEX=re.compile(rb'(?P<space>\s+)|(?P<line>//[^\r\n]*(?:\r?\n|$))|(?P<block>/\*.*?\*/)|(?P<string>"(?:\\.|[^"\\])*")|(?P<escape>\\[^\s]+)|(?P<ident>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<number>(?:[0-9][0-9_]*\s*)?\'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\'[01xXzZ]|[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9_]+)?)|(?P<op><<<|>>>|===|!==|==\?|!=\?|<<=|>>=|\*\*|&&|\|\||==|!=|<=|>=|<<|>>|~\^|\^~|\^\||~\||~&|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|->|=>|\*>|::|\+:|-:|##|[()\[\]{},;:.?~!%^&*+\-/|<>=@#`])',re.S)
def tokens(data):
 pos=0;preprocessor_line=False
 for m in LEX.finditer(data):
  need(m.start()==pos,'unrecognized SV lexical byte');pos=m.end();token=m.group()
  if m.lastgroup=='space':
   yield b'\x00SPACE'+token
   if b'\n'in token and preprocessor_line:
    yield b'\x00PREPROCESSOR_EOL';preprocessor_line=False
   continue
  if m.lastgroup in ('line','block'):
   # Preserve ALL comments including tool pragmas, without classification or
   # semantic assumptions. Input has already used the original pinned scanner.
   yield b'\x00COMMENT'+token
   if b'\n'in token and preprocessor_line:
    yield b'\x00PREPROCESSOR_EOL';preprocessor_line=False
   continue
  need(len(token)<=65536,'token bound')
  need(token not in (b'__LINE__',b'__FILE__'),'location-sensitive macro not admitted')
  if token==b'`':preprocessor_line=True
  yield token
 need(pos==len(data),'unterminated/unknown SV lexical suffix')
 if preprocessor_line:yield b'\x00PREPROCESSOR_EOF'
def contract(module):
 need(module in MODULES,'only two reviewed module names');ports={};assigns={}
 for field,width in FIELDS:
  src='io_tiles_response_bits_key_'+field
  if module==MODULES[0]:
   dst='io_residentTiles_response_bits_key_'+field;ports[src]=('input',width);ports[dst]=('output',width)
  else:dst=src;src='banks_io_tiles_response_bits_key_'+field;ports[dst]=('output',width)
  assigns[dst]=src
 return ports,assigns

def removable_code_starts(data,forbidden=()):
 """Only lexical code, no macro body/conditional or procedural/generate scope.
 FIRRTL continuous port forwarders must precede procedural definitions. A new
 layout outside this narrow supported emitter shape fails closed.
 """
 allowed=set();occurrences=[];pos=0;directive=False;want_directive=False;conditional=0;procedural=False;last_significant=None
 for m in LEX.finditer(data):
  if m.start()!=pos:diagnostic_progress(lexical_byte_offset=pos)
  need(m.start()==pos,'unknown lexical byte before projection');pos=m.end();v=m.group()
  if m.lastgroup in ('space','line','block'):
   if b'\n'in v:directive=False;want_directive=False
   continue
  previous_significant=last_significant;last_significant=v
  if v==b'`':directive=True;want_directive=True;continue
  need(v not in (b'__LINE__',b'__FILE__'),'location-sensitive macro not admitted')
  if want_directive:
   if v in (b'ifdef',b'ifndef'):conditional+=1
   elif v==b'endif':conditional-=1;need(conditional>=0,'balanced preprocessor conditional')
   want_directive=False;continue
  if m.lastgroup in ('string','escape'):continue
  need(v not in (b'__LINE__',b'__FILE__'),'location-sensitive macro not admitted')
  if m.lastgroup=='ident' and v.decode('ascii')in forbidden:occurrences.append(m.start())
  if v==b'('and data[m.end():m.end()+1]==b'*':procedural=True
  if v in (b'always',b'always_comb',b'always_ff',b'always_latch',b'initial',b'generate',b'function',b'task',b'if',b'for',b'while',b'case',b'begin'):procedural=True
  if v in (b'input',b'output',b'assign')and not directive and conditional==0 and not procedural:allowed.add(m.start())
  if v==b'TransposedDownDenseBanks'and previous_significant==b';'and not directive and conditional==0 and not procedural:allowed.add(m.start())
 if pos!=len(data)or conditional!=0:diagnostic_progress(lexical_byte_offset=pos)
 need(pos==len(data)and conditional==0,'complete supported lexical/preprocessor structure')
 return allowed,occurrences

def projected_hash(data,module,new,sourceinfo=None,sink=None):
 """Input is original-scanner normalized bytes. Only exact complete emitter
 port/assign lines are removed; their optional comment MUST be recognized
 SourceInfo, never pragma or unknown comment. No other comment is dropped.
 """
 diagnostic_context('PROJECT_MODULE',module if module in MODULES else None,'new'if new else'old')
 diagnostic_progress(normalized_module_bytes=len(data))
 need(len(data)<=96*1024**2,'normalized module96MiB cap')
 diagnostic_progress(normalized_module_sha256=hashlib.sha256(data).hexdigest())
 ports,assigns=contract(module)
 allowed_starts,key_occurrences=removable_code_starts(data,ports)
 helper=P(__file__).with_name('instance_port_labels.py');helper_bytes=helper.read_bytes();need(hashlib.sha256(helper_bytes).hexdigest()==INSTANCE_LABELS_SHA,'reviewed exact instance label classifier')
 import types
 classifier=types.ModuleType('reviewed_instance_port_labels');exec(compile(helper_bytes,str(helper),'exec'),classifier.__dict__)
 label_offsets=classifier.label_offsets(data,module,allowed_starts,LEX)
 key_occurrences=[location for location in key_occurrences if location not in label_offsets]
 offset=0;removed_ranges=[];digest=hashlib.sha256();projected_bytes=0
 def emit(line):
  nonlocal projected_bytes
  digest.update(line);projected_bytes+=len(line)
  if sink is not None:sink.write(line)
 removed_ports=[];removed_assigns=[];kept=[];in_header=True;removed_info=0;removed_last=False;last_header_port=None
 port_rx=re.compile(rb'^[ \t]*(input|output)[ \t]+\[([0-9]+):0\][ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*(,?)[ \t]*(?://([^\r\n]*))?\r?\n$')
 any_port_rx=re.compile(rb'^([ \t]*(?:input|output)[ \t]+(?:\[[0-9]+:0\][ \t]+)?[A-Za-z_][A-Za-z0-9_]*)(,?)([ \t]*(?://[^\r\n]*)?\r?\n)$')
 assign_rx=re.compile(rb'^[ \t]*assign[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*;[ \t]*(?://([^\r\n]*))?\r?\n$')
 def safe_info(body):
  nonlocal removed_info
  if body is not None:
   need(sourceinfo is not None and sourceinfo.fullmatch(body)is not None,'only original recognized SourceInfo comment on removed line')
   removed_info+=1
 for line_number,line in enumerate(io.BytesIO(data),1):
  diagnostic_progress(line_number=line_number,lexical_byte_offset=offset,projected_normalized_bytes=projected_bytes,removed_ports=len(removed_ports),removed_assignments=len(removed_assigns),removed_sourceinfo_comments=removed_info)
  start=offset;offset+=len(line);code_start=start+len(line)-len(line.lstrip(b' \t'))
  need(line_number<=1500000,'module line-object memory bound')
  need(len(line)<=65536,'bounded emitter line')
  if in_header:
   closes=bool(re.match(rb'^[ \t]*\);',line))
   need(not removed_last or closes or not line.strip(),'removed no-comma final key port must be last')
   match=port_rx.fullmatch(line)
   if match and match[3].decode()in ports:
    need(code_start in allowed_starts,'port deletion must be unconditional lexical code')
    name=match[3].decode();need(new,'old module unexpectedly contains projected port');need(name not in removed_ports,'duplicate projected port');direction,width=ports[name]
    need(match[1].decode()==direction and int(match[2])+1==width,'exact key port direction/width');safe_info(match[5]);removed_ports.append(name);removed_last=match[4]==b'';removed_ranges.append((start,offset));continue
   if closes:
    need(last_header_port is not None,'existing nonprojected port required')
    previous=any_port_rx.fullmatch(kept[last_header_port]);need(previous is not None,'exact retained final emitter port')
    if previous[2]==b',':
     need(new and removed_last,'only actual removed final port leaves allowed comma')
     kept[last_header_port]=previous[1]+previous[3]
    else:need(not removed_last,'removed final port lacks preceding separator')
    in_header=False
    for oldline in kept:emit(oldline)
    kept.clear()
   elif any_port_rx.fullmatch(line):last_header_port=len(kept)
  else:
   match=assign_rx.fullmatch(line)
   if match and match[1].decode()in assigns:
    need(code_start in allowed_starts,'assign deletion must be unconditional module-level lexical code')
    name=match[1].decode();need(new,'old module unexpectedly contains projected assignment');need(name not in removed_assigns,'duplicate projected assign');need(match[2].decode()==assigns[name],'exact direct key forwarder');safe_info(match[3]);removed_assigns.append(name);removed_ranges.append((start,offset));continue
  if in_header:
   kept.append(line);need(sum(map(len,kept))<=2*1024**2,'header buffer cap')
  else:emit(line)
 diagnostic_progress(projected_normalized_bytes=projected_bytes,removed_ports=len(removed_ports),removed_assignments=len(removed_assigns),removed_sourceinfo_comments=removed_info)
 need(not in_header,'complete emitter header')
 need(set(removed_ports)==(set(ports)if new else set()),'exact complete added key ports');need(set(removed_assigns)==(set(assigns)if new else set()),'exact complete direct key assigns')
 need(data.startswith(b'module '+module.encode()+b'(')and re.search(rb'\nendmodule[ \t\r\n]*\Z',data)is not None,'complete same named module')
 for location in key_occurrences:need(any(lo<=location<hi for lo,hi in removed_ranges),'new key remains in unprojected logic/port')
 diagnostic_progress(projected_normalized_sha256=digest.hexdigest())
 return dict(projected_normalized_sha256=digest.hexdigest(),projected_normalized_bytes=projected_bytes,removed_ports=sorted(removed_ports),removed_sourceinfo_comments=removed_info,removed_assignments=[dict(destination=k,source=assigns[k])for k in sorted(removed_assigns)])

def extract(source,output):
 names=[];active=None;dest=None;paths={};total=0
 try:
  with P(source).open('rb')as f:
   for line in iter(lambda:f.readline(65537),b''):
    need(len(line)<=65536,'SV line cap');total+=len(line)
    m=re.match(rb'module ([A-Za-z_][A-Za-z0-9_$]*)\(',line)
    if m:
     need(active is None,'nested module');active=m[1].decode();names.append(active)
     if active in MODULES:
      path=output/(active+'.sv');dest=path.open('xb');paths[active]=path
    if dest:dest.write(line)
    if re.match(rb'endmodule(?:\s|$)',line):
     need(active is not None,'endmodule without module')
     if dest:dest.close();dest=None
     active=None
  need(active is None and set(paths)==set(MODULES)and len(names)==len(set(names))==92,'actual complete92 modules')
  need(total==P(source).stat().st_size,'complete source read')
  return names,paths
 finally:
  if dest:dest.close()

def prove(old,new,old_metadata,new_metadata,materialization,output):
 reset_diagnostic();diagnostic_context('INPUT_BINDING')
 m=P(materialization).resolve();need(sha(m/'sv_comment_only_identity.py')==SCANNER,'original exact scanner source')
 sys.path.insert(0,str(m));import sv_comment_only_identity as scanner
 digest=scanner.digest
 sources={'old':P(old).resolve(),'new':P(new).resolve()};metadatas={'old':P(old_metadata).resolve(),'new':P(new_metadata).resolve()};identity={}
 for kind,p in sources.items():
  diagnostic_context('INPUT_BINDING',kind=kind)
  need(p.is_file()and not p.is_symlink()and 0<p.stat().st_size<=512*1024**2,'bounded actual SV file')
  metadata=metadatas[kind];receipt=metadata.parent/'RESULT.json'
  need(metadata.is_file()and not metadata.is_symlink()and metadata.stat().st_size<=512*1024,'bounded whole scanner metadata')
  need(receipt.is_file()and not receipt.is_symlink()and receipt.stat().st_size<=16*1024**2,'bounded original scan stage receipt')
  doc=json.loads(metadata.read_text());run=json.loads(receipt.read_text())
  need(run.get('native_exit')==0 and run.get('errors')==[] and run.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and run.get('log_capture',{}).get('pipe_eof_observed')is True and run.get('log_capture',{}).get('gzip_finalized')is True,'actual completed source-pinned scan')
  argv=run['argv'];need(len(argv)==9 and argv[1]=='-B' and argv[3:]==['--observe-sv',str(p),'--materialization',str(m),'--output',metadata.name],'exact actual full scanner command')
  need(P(argv[0]).resolve()==P(sys.executable).resolve()and sha(argv[2])==COLLECTOR_SHA,'reviewed scanner collector/current Python')
  need(doc.get('schema')=='OBSERVED_FRONTEND_SV_V1' and doc.get('status')=='OBSERVED_UNREVIEWED_NOT_ACCEPTED' and doc.get('numerical_pass')is False and doc.get('scanner_sha256')==SCANNER,'original observed scanner contract')
  raw=sha(p);normal=doc['normalized_sha256']
  need(normal==FULL[kind] and doc['raw_sha256']==raw and doc['bytes']==p.stat().st_size,'independently known full normalized identity bound actual raw file')
  modulemap={x['module']:x for x in doc['modules']};need(len(modulemap)==len(doc['modules'])==92,'complete92 metadata')
  for name in MODULES:need(modulemap[name]['normalized_sha256']==MOD_NORMALIZED[kind][name],'known actual selected module identity')
  identity[kind]=dict(bytes=p.stat().st_size,raw_sha256=raw,normalized_sha256=normal,metadata_sha256=sha(metadata),scan_receipt_sha256=sha(receipt))
  DIAGNOSTIC['full_sv'][kind]=dict(identity[kind])
 result={}
 with tempfile.TemporaryDirectory(prefix='owned-key-projection-')as td:
  allpaths={};orders=[]
  for kind,p in sources.items():
   diagnostic_context('EXTRACT_MODULES',kind=kind)
   d=P(td)/kind;d.mkdir();names,paths=extract(p,d);orders.append(names);allpaths[kind]=paths
  need(orders[0]==orders[1],'same complete92 module order')
  for name in MODULES:
   rows={}
   for kind in ('old','new'):
    diagnostic_context('NORMALIZE_MODULE',name,kind)
    p=allpaths[kind][name];need(p.stat().st_size<=128*1024**2,'selected module bound')
    normalized=p.with_suffix('.normalized')
    class TeeHasher:
     def __init__(self):self.h=hashlib.sha256();self.bytes=0
     def update(self,data):
      self.bytes+=len(data);need(self.bytes<=128*1024**2,'normalized module cap');sink.write(data);self.h.update(data)
     def hexdigest(self):return self.h.hexdigest()
    import types
    original_hashlib=scanner.hashlib
    try:
     with normalized.open('xb')as sink:
      scanner.hashlib=types.SimpleNamespace(sha256=TeeHasher)
      with p.open('rb')as f:normal=scanner.digest(f)
    finally:scanner.hashlib=original_hashlib
    diagnostic_progress(normalized_module_sha256=normal,normalized_module_bytes=normalized.stat().st_size)
    need(normal==MOD_NORMALIZED[kind][name],'same actual module fingerprint')
    with p.with_suffix('.projected').open('xb')as projected_sink:
     rows[kind]=projected_hash(normalized.read_bytes(),name,kind=='new',scanner.SOURCEINFO,projected_sink)
    rows[kind]['normalized_module_sha256']=normal
    diagnostic_comparison(rows)
   diagnostic_context('COMPARE_MODULE',name)
   diagnostic_comparison(rows)
   need(rows['old']['projected_normalized_sha256']==rows['new']['projected_normalized_sha256']and rows['old']['projected_normalized_bytes']==rows['new']['projected_normalized_bytes'],'nonprojected normalized SV byte difference: reject')
   with allpaths['old'][name].with_suffix('.projected').open('rb')as old_stream,allpaths['new'][name].with_suffix('.projected').open('rb')as new_stream:
    while True:
     left=old_stream.read(65536);right=new_stream.read(65536);need(left==right,'exact remaining byte comparison differs')
     if not left:break
   result[name]=rows
 diagnostic_context('RECHECK_INPUTS')
 for kind,p in sources.items():need(sha(p)==identity[kind]['raw_sha256'],'SV source changed during proof')
 r=dict(schema='EXACT_TWO_MODULE_KEY_PROJECTION_V1',status='PASS_ONLY_61BIT_OBSERVATION_PORT_FORWARDING_NORMALIZED_BYTE_PROJECTION',scope='TWO_SPECIFIC_MODULES_NOT_GENERAL_SV_EQUIVALENCE_OR_NUMERICAL_PASS',full_sv=identity,modules=result,scanner_sha256=SCANNER,projection_source_sha256=sha(__file__),full_m128_numeric_pass=False,final_rtl_pass=False,numerical_pass=False,sv_repin_authorized=False,remaining_bytes_compared=True)
 diagnostic_context('PROJECT_PROOF')
 r=project_proof(r)
 diagnostic_context('WRITE_PROOF')
 b=(json.dumps(r,sort_keys=True,indent=2)+'\n').encode();need(len(b)<=65536,'bounded proof metadata')
 with P(output).open('xb')as f:f.write(b)
 return r
def project_proof(r):
 """Exact read-only proof projection for exporter; no arbitrary data slots."""
 def keys(v,w):need(type(v)is dict and set(v)==set(w.split()),'exact proof fields')
 def digest(v):need(type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None,'proof digest')
 def integer(v,cap):need(type(v)is int and 0<=v<=cap,'bounded proof integer')
 keys(r,'schema status scope full_sv modules scanner_sha256 projection_source_sha256 full_m128_numeric_pass final_rtl_pass numerical_pass sv_repin_authorized remaining_bytes_compared')
 need(r['schema']=='EXACT_TWO_MODULE_KEY_PROJECTION_V1'and r['status']=='PASS_ONLY_61BIT_OBSERVATION_PORT_FORWARDING_NORMALIZED_BYTE_PROJECTION'and r['scope']=='TWO_SPECIFIC_MODULES_NOT_GENERAL_SV_EQUIVALENCE_OR_NUMERICAL_PASS','exact narrow proof scope')
 need(r['remaining_bytes_compared']is True,'direct streamed byte equality required')
 need(r['scanner_sha256']==SCANNER and r['projection_source_sha256']==sha(__file__),'reviewed exact algorithms')
 for k in ('full_m128_numeric_pass','final_rtl_pass','numerical_pass','sv_repin_authorized'):need(r[k]is False,'no numerical or auto-repin claim')
 keys(r['full_sv'],'old new')
 for kind,entry in r['full_sv'].items():
  keys(entry,'bytes raw_sha256 normalized_sha256 metadata_sha256 scan_receipt_sha256');integer(entry['bytes'],512*1024**2)
  for k in ('raw_sha256','normalized_sha256','metadata_sha256','scan_receipt_sha256'):digest(entry[k])
  need(entry['normalized_sha256']==FULL[kind],'fixed complete normalizedSV identity')
 keys(r['modules'],' '.join(MODULES))
 for name,records in r['modules'].items():
  keys(records,'old new');ports,assigns=contract(name)
  for kind,row in records.items():
   keys(row,'projected_normalized_sha256 projected_normalized_bytes removed_ports removed_sourceinfo_comments removed_assignments normalized_module_sha256')
   digest(row['projected_normalized_sha256']);integer(row['projected_normalized_bytes'],100000000);integer(row['removed_sourceinfo_comments'],len(ports)+len(assigns))
   need(row['normalized_module_sha256']==MOD_NORMALIZED[kind][name],'actual selected module fingerprint')
   need(row['removed_ports']==(sorted(ports)if kind=='new'else []),'exact projected key ports')
   need(row['removed_assignments']==([dict(destination=k,source=assigns[k])for k in sorted(assigns)]if kind=='new'else []),'exact projected direct assigns')
   if kind=='old':need(row['removed_sourceinfo_comments']==0,'old side unmodified')
  need(records['old']['projected_normalized_sha256']==records['new']['projected_normalized_sha256']and records['old']['projected_normalized_bytes']==records['new']['projected_normalized_bytes'],'remaining normalized bytes exactly same')
 need(len(json.dumps(r,sort_keys=True,indent=2).encode())+1<=65536,'bounded proof export')
 return json.loads(json.dumps(r))

EXCEPTION_CODES={'OSError':'IO_FAILURE','ValueError':'UNCLASSIFIED_VALUE_ERROR','KeyError':'MISSING_FIELD','TypeError':'INVALID_FIELD_TYPE','ImportError':'IMPORT_FAILURE','MemoryError':'MEMORY_FAILURE'}
def failure_record(error):
 if isinstance(error,ProjectionRejected):code=error.reason_code
 else:code=next((EXCEPTION_CODES[t.__name__]for t in (OSError,KeyError,TypeError,ImportError,MemoryError,ValueError)if isinstance(error,t)),'UNCLASSIFIED_CONTROLLED_FAILURE')
 return project_failure(dict(schema='EXACT_TWO_MODULE_KEY_PROJECTION_FAILED_V1',status='FAILED_PROJECTION_NOT_ACCEPTED',scope='DIAGNOSTIC_ONLY_NO_EQUIVALENCE_OR_NUMERICAL_PASS',reason_code=code,phase=DIAGNOSTIC['phase'],module=DIAGNOSTIC['module'],kind=DIAGNOSTIC['kind'],full_sv=DIAGNOSTIC['full_sv'],progress=DIAGNOSTIC['progress'],saturated_fields=DIAGNOSTIC['saturated_fields'],comparison=DIAGNOSTIC['comparison'],normalized_module_matches_expected=(None if DIAGNOSTIC['progress']['normalized_module_sha256']is None or DIAGNOSTIC['module']not in MODULES or DIAGNOSTIC['kind']not in ('old','new')else DIAGNOSTIC['progress']['normalized_module_sha256']==MOD_NORMALIZED[DIAGNOSTIC['kind']][DIAGNOSTIC['module']]),scanner_sha256=SCANNER,projection_source_sha256=sha(__file__),numerical_pass=False,sv_repin_authorized=False,remaining_bytes_compared=False))
def project_failure(r):
 """Exact diagnostic whitelist; no exception text, paths or raw source slots."""
 def check(v,label):
  if not v:raise ValueError('invalid failure '+label)
 def keys(v,w):check(type(v)is dict and set(v)==set(w.split()),'fields')
 def h(v):return type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None
 keys(r,'schema status scope reason_code phase module kind full_sv progress saturated_fields comparison normalized_module_matches_expected scanner_sha256 projection_source_sha256 numerical_pass sv_repin_authorized remaining_bytes_compared')
 check(r['schema']=='EXACT_TWO_MODULE_KEY_PROJECTION_FAILED_V1'and r['status']=='FAILED_PROJECTION_NOT_ACCEPTED'and r['scope']=='DIAGNOSTIC_ONLY_NO_EQUIVALENCE_OR_NUMERICAL_PASS','scope')
 check(r['reason_code']in set(REJECTION_CODES.values())|set(EXCEPTION_CODES.values())|{'UNCLASSIFIED_CONTRACT_REJECTION','UNCLASSIFIED_CONTROLLED_FAILURE'},'reason')
 check(r['phase']in PHASES and r['module']in (None,*MODULES) and r['kind']in (None,'old','new'),'context')
 check(r['scanner_sha256']==SCANNER and r['projection_source_sha256']==sha(__file__),'algorithm')
 for k in ('numerical_pass','sv_repin_authorized','remaining_bytes_compared'):check(r[k]is False,'flags')
 keys(r['full_sv'],'old new')
 for kind,row in r['full_sv'].items():
  if row is None:continue
  keys(row,'bytes raw_sha256 normalized_sha256 metadata_sha256 scan_receipt_sha256')
  check(type(row['bytes'])is int and 0<row['bytes']<=512*1024**2,'input bytes')
  check(all(h(row[k])for k in ('raw_sha256','normalized_sha256','metadata_sha256','scan_receipt_sha256'))and row['normalized_sha256']==FULL[kind],'input hashes')
 keys(r['progress'],' '.join(PROGRESS_KEYS))
 for k,v in r['progress'].items():
  if v is None:continue
  if k.endswith('sha256'):check(h(v),'progress hash')
  else:
   cap=PROGRESS_CAPS[k]
   check(type(v)is int and 0<=v<=cap,'progress count')
 check(type(r['saturated_fields'])is list and r['saturated_fields']==sorted(set(r['saturated_fields']))and all(k in PROGRESS_CAPS and r['progress'][k]is None for k in r['saturated_fields']),'saturated fields')
 keys(r['comparison'],'old new projected_bytes_equal projected_sha256_equal')
 for side in ('old','new'):
  row=r['comparison'][side]
  if row is None:continue
  keys(row,'normalized_module_sha256 projected_normalized_sha256 projected_normalized_bytes removed_ports removed_assignments removed_sourceinfo_comments')
  check(row['normalized_module_sha256']is None or h(row['normalized_module_sha256']),'comparison module hash')
  check(h(row['projected_normalized_sha256']),'comparison projected hash')
  for k in ('projected_normalized_bytes','removed_ports','removed_assignments','removed_sourceinfo_comments'):check(type(row[k])is int and 0<=row[k]<=(128*1024**2 if k.endswith('bytes')else 16),'comparison count')
 both=r['comparison']['old']is not None and r['comparison']['new']is not None
 for flag,field in [('projected_bytes_equal','projected_normalized_bytes'),('projected_sha256_equal','projected_normalized_sha256')]:
  expected=None if not both else r['comparison']['old'][field]==r['comparison']['new'][field]
  check(r['comparison'][flag]is expected,'comparison equality fact')
 actual=r['progress']['normalized_module_sha256']
 expected=None if actual is None or r['kind']not in ('old','new')or r['module']not in MODULES else actual==MOD_NORMALIZED[r['kind']][r['module']]
 check(r['normalized_module_matches_expected']is expected,'module mismatch fact')
 check(len(json.dumps(r,sort_keys=True,indent=2).encode())+1<=65536,'cap')
 return json.loads(json.dumps(r))
def main():
 a=argparse.ArgumentParser();a.add_argument('--old-sv',required=True);a.add_argument('--new-sv',required=True);a.add_argument('--old-metadata',required=True);a.add_argument('--new-metadata',required=True);a.add_argument('--materialization',required=True);a.add_argument('--output',required=True);v=a.parse_args()
 reset_diagnostic()
 try:prove(v.old_sv,v.new_sv,v.old_metadata,v.new_metadata,v.materialization,v.output)
 except (ProjectionRejected,OSError,ValueError,KeyError,TypeError,ImportError,MemoryError)as error:
  report=failure_record(error);data=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
  with P(v.output).open('xb')as f:f.write(data)
  return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
