"""Two specific unchanged-HIGH modules only. No generic logic deletion/renaming.
Full old/new SV identities are independently fixed before strict normalized-byte projection.
No emit, elaboration, subprocess, network, frontend or numerical qualification.
"""
import argparse,hashlib,io,json,pathlib,re,struct,sys,tempfile
P=pathlib.Path
SCANNER='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
FULL={'old':'6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5','new':'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72'}
COLLECTOR_SHA='f314fee478766a847381288d1a675d3c55ea41562ec95c1e6bc4d9503f1e125f'
MODULES=('Public21QkvReductionRouter','TransposedDenseDownOwner')
FIELDS=(('identity',32),('slot',2),('ng',16),('index',11))
MOD_NORMALIZED={
 'old':{'Public21QkvReductionRouter':'1e87261c949e8fe372f64ec54886aa597479cb1e6b23ab6c4311242c6b71271d','TransposedDenseDownOwner':'e07f04f309da1a58a528082ab327d0f361dd117eb8fbc4bc878b4b15faa9b78f'},
 'new':{'Public21QkvReductionRouter':'4a11a5c08ef38434ecf827120e6627b96f9537049ed0ca7eaaef24a7954b973e','TransposedDenseDownOwner':'d26f8e11bcd4e663774f921d38e22d442faf176657067401001d0fd7cd5f8a6f'}}
def need(v,s):
 if not v:raise ValueError(s)
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
 allowed=set();occurrences=[];pos=0;directive=False;want_directive=False;conditional=0;procedural=False
 for m in LEX.finditer(data):
  need(m.start()==pos,'unknown lexical byte before projection');pos=m.end();v=m.group()
  if m.lastgroup in ('space','line','block'):
   if b'\n'in v:directive=False;want_directive=False
   continue
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
 need(pos==len(data)and conditional==0,'complete supported lexical/preprocessor structure')
 return allowed,occurrences

def projected_hash(data,module,new,sourceinfo=None,sink=None):
 """Input is original-scanner normalized bytes. Only exact complete emitter
 port/assign lines are removed; their optional comment MUST be recognized
 SourceInfo, never pragma or unknown comment. No other comment is dropped.
 """
 need(len(data)<=96*1024**2,'normalized module96MiB cap')
 ports,assigns=contract(module)
 allowed_starts,key_occurrences=removable_code_starts(data,ports);offset=0;removed_ranges=[];digest=hashlib.sha256();projected_bytes=0
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
 need(not in_header,'complete emitter header')
 need(set(removed_ports)==(set(ports)if new else set()),'exact complete added key ports');need(set(removed_assigns)==(set(assigns)if new else set()),'exact complete direct key assigns')
 need(data.startswith(b'module '+module.encode()+b'(')and re.search(rb'\nendmodule[ \t\r\n]*\Z',data)is not None,'complete same named module')
 for location in key_occurrences:need(any(lo<=location<hi for lo,hi in removed_ranges),'new key remains in unprojected logic/port')
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
 m=P(materialization).resolve();need(sha(m/'sv_comment_only_identity.py')==SCANNER,'original exact scanner source')
 sys.path.insert(0,str(m));import sv_comment_only_identity as scanner
 digest=scanner.digest
 sources={'old':P(old).resolve(),'new':P(new).resolve()};metadatas={'old':P(old_metadata).resolve(),'new':P(new_metadata).resolve()};identity={}
 for kind,p in sources.items():
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
 result={}
 with tempfile.TemporaryDirectory(prefix='owned-key-projection-')as td:
  allpaths={};orders=[]
  for kind,p in sources.items():
   d=P(td)/kind;d.mkdir();names,paths=extract(p,d);orders.append(names);allpaths[kind]=paths
  need(orders[0]==orders[1],'same complete92 module order')
  for name in MODULES:
   rows={}
   for kind in ('old','new'):
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
    need(normal==MOD_NORMALIZED[kind][name],'same actual module fingerprint')
    with p.with_suffix('.projected').open('xb')as projected_sink:
     rows[kind]=projected_hash(normalized.read_bytes(),name,kind=='new',scanner.SOURCEINFO,projected_sink)
    rows[kind]['normalized_module_sha256']=normal
   need(rows['old']['projected_normalized_sha256']==rows['new']['projected_normalized_sha256']and rows['old']['projected_normalized_bytes']==rows['new']['projected_normalized_bytes'],'nonprojected normalized SV byte difference: reject')
   with allpaths['old'][name].with_suffix('.projected').open('rb')as old_stream,allpaths['new'][name].with_suffix('.projected').open('rb')as new_stream:
    while True:
     left=old_stream.read(65536);right=new_stream.read(65536);need(left==right,'exact remaining byte comparison differs')
     if not left:break
   result[name]=rows
 for kind,p in sources.items():need(sha(p)==identity[kind]['raw_sha256'],'SV source changed during proof')
 r=dict(schema='EXACT_TWO_MODULE_KEY_PROJECTION_V1',status='PASS_ONLY_61BIT_OBSERVATION_PORT_FORWARDING_NORMALIZED_BYTE_PROJECTION',scope='TWO_SPECIFIC_MODULES_NOT_GENERAL_SV_EQUIVALENCE_OR_NUMERICAL_PASS',full_sv=identity,modules=result,scanner_sha256=SCANNER,projection_source_sha256=sha(__file__),full_m128_numeric_pass=False,final_rtl_pass=False,numerical_pass=False,sv_repin_authorized=False,remaining_bytes_compared=True)
 r=project_proof(r)
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

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--old-sv',required=True);a.add_argument('--new-sv',required=True);a.add_argument('--old-metadata',required=True);a.add_argument('--new-metadata',required=True);a.add_argument('--materialization',required=True);a.add_argument('--output',required=True);v=a.parse_args();prove(v.old_sv,v.new_sv,v.old_metadata,v.new_metadata,v.materialization,v.output)
