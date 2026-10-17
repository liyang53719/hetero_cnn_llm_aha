"""CHIRRTL structural evidence, not dynamic debt retirement verification."""
import re,hashlib,collections
from pathlib import Path
def need(ok,msg):
 if not ok:raise ValueError(msg)
def check(path):
 b=Path(path).read_bytes();need(len(b)<=48*1024**2,'CHIRRTL exceeds48MiB');text=b.decode()
 matches=list(re.finditer(r'^  (module|extmodule) (\w+)\s*:',text,re.M));need(0<len(matches)<=768,'module definition cap')
 need(len({m[2] for m in matches})==len(matches),'duplicate module definition')
 blocks={m[2]:text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)] for i,m in enumerate(matches)}
 need('ProductionQk16KernelBench' in blocks,'original top missing');need(re.search(r'^circuit ProductionQk16KernelCollection\s*:',text,re.M),'wrong circuit root')
 kinds={m[2]:m[1] for m in matches};instances={n:re.findall(r'^\s+inst (\w+) of (\w+)',body,re.M) for n,body in blocks.items()}
 for name,items in instances.items():need(len({n for n,_ in items})==len(items),'duplicate instance name '+name)
 need(kinds.get('ProductionQk16KernelCollection')=='module','collection missing')
 expected_siblings={'top':'ProductionQk16KernelBench','pre':'HeteroBF16FmaPre','mul':'HeteroBF16FmaMul','post':'HeteroBF16FmaPost','round':'HeteroBF16FmaRound'}
 need(dict(instances['ProductionQk16KernelCollection'])==expected_siblings,'exact collection sibling inventory')
 for mod in expected_siblings.values():need(kinds.get(mod)=='module','real collection child definition missing '+mod)
 counts=collections.Counter();paths={}
 def walk(mod,path,stack):
  need(mod not in stack,'recursive module graph');need(mod in blocks,'unknown module reference');counts[mod]+=1;paths[path]=mod
  need(len(paths)<=20000,'instance graph cap')
  for name,child in instances[mod]:walk(child,path+'.'+name,stack+[mod])
 walk('ProductionQk16KernelCollection','ProductionQk16KernelCollection',[])
 collection_instance_count=len(paths)
 counts.clear();paths.clear()
 walk('ProductionQk16KernelBench','ProductionQk16KernelBench',[])
 expected={'ProductionQk16KernelBench':1,'QwenOwnerKernel':1,'TransposedDenseDownOwner':1,'TransposedDownDenseBanks':1,'ScheduledSiluOwner':1,'VectorSiluOwner':1,'SiluVectorUnit':1,'MatrixPipelineService':1,'LegacyMatrixStreamClient':1,'FfnResidentCoordinator':1,'Public21QkvReductionRouter':1,'SharedMemoryArbiter':1,'RetainedIdmaWeightBurstAdapter':1,'idma_backend_rw_axi_flat_wrap':1,'qwen2_matrix_command_endpoint':8,'tc_clk_gating':8}
 canonical=collections.Counter()
 for name,count in counts.items():canonical[re.sub(r'_\d+$','',name)]+=count
 for name,count in expected.items():need(canonical[name]==count,'resource instance count '+name)
 need(canonical['HostBlockCommands']==0 and canonical['HostBlockTop']==0,'test shell must not be misreported as Host')
 need(canonical['TransposedDenseBanks']==0,'duplicate alternate bank set')
 vector_path=next(path for path,mod in paths.items() if mod=='SiluVectorUnit')
 need(sum(mod.startswith('BlockScalarFloat') for path,mod in paths.items() if path.startswith(vector_path+'.'))==16,'SFU16 lane count')
 kernel=blocks['QwenOwnerKernel'];debts=['matrixDebt','readDebt','writeDebt','memoryDebt','seedDebt']
 for name in debts:need(re.search(r'\breg(?:reset)? '+name+r'\s*:',kernel),'real production debt register absent '+name)
 node_rows=re.findall(r'^\s+node (\w+) = (.+?)(?: @\[.*)?$',kernel,re.M)
 need(len({n for n,_ in node_rows})==len(node_rows),'duplicate kernel node name')
 nodes=dict(node_rows)
 def conjunction(expr,seen=None):
  seen=set() if seen is None else seen;expr=expr.split(' @[')[0].strip()
  if expr in nodes:
   need(expr not in seen,'cyclic boolean node');return conjunction(nodes[expr],seen|{expr})
  if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',expr):return {(expr,True)}
  m=re.fullmatch(r'(and|not|eq)\((.*)\)',expr);need(m is not None,'unsupported boolean expression '+expr)
  args=[];depth=0;start=0
  for i,c in enumerate(m[2]):
   if c=='(':depth+=1
   elif c==')':depth-=1
   elif c==',' and depth==0:args.append(m[2][start:i].strip());start=i+1
  args.append(m[2][start:].strip())
  if m[1]=='and':
   need(len(args)>=2,'and arity');result=set()
   for x in args:result|=conjunction(x,seen)
   return result
  if m[1]=='eq':
   need(len(args)==2 and args[1] in ['UInt<1>(0h0)','UInt<1>(0)'],'only boolean eq-zero admitted');args=args[:1]
  need(len(args)==1,'negation arity');inner=conjunction(args[0],seen);need(len(inner)==1,'only atom negation admitted')
  atom,polarity=next(iter(inner));return {(atom,not polarity)}
 router=next(name for name,mod in instances['QwenOwnerKernel'] if mod=='Public21QkvReductionRouter')
 evidence={}
 matrix=next(name for name,mod in instances['QwenOwnerKernel'] if mod=='MatrixPipelineService')
 dense=next(name for name,mod in instances['QwenOwnerKernel'] if mod=='TransposedDenseDownOwner')
 for port,required in [('matrixDrained',['matrixDebt','seedDebt',matrix+'.io.port.result.valid',matrix+'.io.port.done.valid']),('dmaDrained',['readDebt','writeDebt','memoryDebt'])]:
  lines=re.findall(r'^\s+connect '+re.escape(router)+r'\.io\.'+port+r', (.+)$',kernel,re.M);need(len(lines)==1,'drained connect uniqueness '+port)
  need(conjunction(lines[0])=={(x,False) for x in required},'drained must be exact negative conjunction '+port);evidence[port]=dict(connect=lines[0],required_negative_dependencies=required)
 # Identify the real accepted/retired handshake guard for each debt update.
 updates={name:[] for name in debts};guards=[]
 for line in kernel.splitlines():
  indent=len(line)-len(line.lstrip())
  while guards and guards[-1][0]>=indent:guards.pop()
  match=re.match(r'\s*when (.+?)\s*:',line)
  if match:guards.append((indent,match[1]))
  match=re.match(r'\s*connect (matrixDebt|readDebt|writeDebt|memoryDebt|seedDebt), (.+)',line)
  if match:updates[match[1]].append(dict(value=match[2].split(' @[')[0],guard_expressions=[x[1] for x in guards]))
 handshakes={'matrixDebt':(matrix+'.io.port.group',matrix+'.io.port.done'),'readDebt':(dense+'.io.burst',dense+'.io.burstResponse'),'writeDebt':(dense+'.io.writeRequest',dense+'.io.writeResponse'),'memoryDebt':('io.memory','io.response'),'seedDebt':(matrix+'.io.port.seed.begin',matrix+'.io.port.seed.ack')}
 for debt,(accept,retire) in handshakes.items():
  need(len(updates[debt])==2 and {u['value'] for u in updates[debt]}=={'UInt<1>(0h0)','UInt<1>(0h1)'},'exact two debt updates required '+debt)
  for port,value in [(accept,'1'),(retire,'0')]:
   selected=[u for u in updates[debt] if re.fullmatch(r'UInt<1>\(0h'+value+r'\)',u['value'])]
   need(len(selected)==1,'unique debt update '+debt+' '+value)
   atoms=set()
   for expr in selected[0]['guard_expressions']:atoms|=conjunction(expr)
   need(atoms=={(port+'.valid',True),(port+'.ready',True)},'debt guard must be exact positive fire '+debt+' '+port)
 memory=[dict(module=n,declaration=line.strip()) for n,body in blocks.items() for line in body.splitlines() if re.match(r'^\s*(?:cmem|smem|mem)\s',line)]
 return dict(scope='COLLECTION_NAMESPACE_BENCH_SUBTREE_CHIRRTL_ONLY',emission_root='ProductionQk16KernelCollection',qualification_top='ProductionQk16KernelBench',collection_direct_instances=expected_siblings,collection_instance_count=collection_instance_count,resource_count_scope='Bench subtree only; four real FMA siblings excluded',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),definition_count=len(blocks),instance_count=len(paths),resource_counts=dict(canonical),raw_module_instance_counts=dict(counts),external_modules=sorted(n for n in blocks if kinds[n]=='extmodule'),memory_declarations=memory,physical_mac_lanes=4096,physical_mac_basis='eight original 16x32 retained endpoint interfaces; blackbox implementation not executed',drained_dependencies=evidence,debt_update_evidence=updates,debt_protocol_executed=False,arithmetic_executed=False,job_launched=False,capacity_tokens=1024,actual_job_m=None)
