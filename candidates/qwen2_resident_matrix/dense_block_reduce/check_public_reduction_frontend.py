#!/usr/bin/env python3
"""Full public Dense coordinator to actual shared owner/Vector CHIRRTL gate.

Reuse a verified official-BF16 or Dense-drain frontend source receipt. The
official baseline route composes all three overlays and compiles once, then
checks default-off IR, bounded resource changes and public integration.
Compile/elaborate only; no firtool, RTL, simulation or private memory.
The control graph is a conservative frontend check, not a full RTL loop proof.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode=True
TASK=Path(__file__).resolve().parent
ROOT=TASK.parents[2]
PROFILE='public_dense_reduction'
OWNER='candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala'
OFFICIAL_STATUS='PASS_OFFICIAL_BF16_TYPECHECK_AND_BOUNDED_FRONTEND_ONLY'
K_PROFILES=('parent_default','disabled_default','parent_official','disabled_official','enabled_official','enabled_burst')
VECTOR_PROFILES=('vector_before_legacy','vector_default','vector_before_official','vector_disabled_official',
                 'owner_before','owner_disabled','vector_enabled_legacy','vector_enabled_official')


def sha(data):return hashlib.sha256(data).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj


def control_dependencies(fir):
    text=re.sub(r' @\[[^\]]*\]','',fir)
    modules={m[1]:m[0] for m in re.finditer(r'^  module (\w+) :.*?(?=^  (?:extmodule|module) |\Z)',text,re.M|re.S)}
    chosen=(('PublicDenseReductionHarness','top'),('DenseBlockReductionCoordinator','top.coordinator'),
            ('DenseTileSumBridge','top.coordinator.bridge'),('TransposedDenseDownOwner','top.owner'),
            ('TransposedDownDenseBanks','top.owner.banks'),('VectorSiluOwner','top.vector'),
            ('SiluVectorUnit','top.vector.vector'))
    graph={};aliases={};registers=set()
    token=re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*')
    for name,prefix in chosen:
        if name not in modules:raise ValueError('missing real control module: '+name)
        body=modules[name]
        registers.update(prefix+'.'+n for n in re.findall(r'^\s*reg(?:reset)? (\w+) :',body,re.M))
        guards=[];last_when={}
        def refs(expr):return {prefix+'.'+n for n in token.findall(expr)}
        for line in body.splitlines()[1:]:
            indent=len(line)-len(line.lstrip());s=line.strip()
            guards=[(i,g) for i,g in guards if i<indent]
            if s.startswith('when '):
                condition=s[5:].rsplit(':',1)[0].strip();last_when[indent]=condition;guards.append((indent,condition))
            elif s.startswith('else :'):
                guards.append((indent,last_when[indent]))
            elif s.startswith('node '):
                lhs,rhs=s[5:].split(' = ',1);graph.setdefault(prefix+'.'+lhs,set()).update(refs(rhs))
            elif s.startswith('connect '):
                lhs,rhs=s[8:].split(', ',1);target=prefix+'.'+lhs
                if any(target==r or target.startswith(r+'.') or target.startswith(r+'[') for r in registers):continue
                graph.setdefault(target,set()).update(refs(rhs))
                if token.fullmatch(rhs):aliases.setdefault(target,set()).add(prefix+'.'+rhs)
                for _,guard in guards:graph[target].update(refs(guard))
    def observed(module_name,left,right):
        lines=[line.strip() for line in modules[module_name].splitlines() if line.strip().startswith('connect ')]
        if not any((line.startswith('connect '+left) and right in line) or
                   (line.startswith('connect '+right) and left in line) for line in lines):
            raise ValueError('missing actual frontend service connection: '+left+' / '+right)
    def edge(dst,src):
        graph.setdefault(dst,set()).add(src)
        aliases.setdefault(dst,set()).add(src)
    def request(client,server):
        edge(server+'.valid',client+'.valid');edge(server+'.bits',client+'.bits');edge(client+'.ready',server+'.ready')
    def result(client,server):
        edge(client+'.valid',server+'.valid');edge(client+'.bits',server+'.bits');edge(server+'.ready',client+'.ready')
    def loan(client,server):
        request(client+'.request',server+'.request');result(client+'.result',server+'.result')
        edge(server+'.abort',client+'.abort')
        for name in ('busy','drained','resetRequired'):edge(client+'.'+name,server+'.'+name)
    def tiles(client,server):
        for name in ('control','write','read'):request(client+'.'+name,server+'.'+name)
        result(client+'.response',server+'.response');edge(server+'.abort',client+'.abort')
        for name in ('busy','leased','drained','resetRequired','state'):edge(client+'.'+name,server+'.'+name)
    # CHIRRTL retains mixed-direction Bundle connects. Expand the actual
    # declared protocols to avoid omitting abort/ready paths across hierarchy.
    observed('PublicDenseReductionHarness','coordinator.io.vector','vector.io.loan')
    observed('DenseBlockReductionCoordinator','io.vector','bridge.io.vector')
    loan('top.coordinator.io.vector','top.vector.io.loan')
    loan('top.coordinator.bridge.io.vector','top.coordinator.io.vector')
    observed('PublicDenseReductionHarness','coordinator.io.tiles','owner.io.tiles')
    observed('DenseBlockReductionCoordinator','io.tiles','bridge.io.tiles')
    tiles('top.coordinator.io.tiles','top.owner.io.tiles')
    tiles('top.coordinator.bridge.io.tiles','top.coordinator.io.tiles')
    for name in ('window','drain'):
        observed('PublicDenseReductionHarness','coordinator.io.'+name,'owner.io.'+name)
        client='top.coordinator.io.'+name;server='top.owner.io.'+name
        request(client+'.request',server+'.request');result(client+'.result',server+'.result')
        for field in ('busy','resetRequired'):edge(client+'.'+field,server+'.'+field)
        if name=='window':
            edge(server+'.invalidateLease',client+'.invalidateLease');edge(client+'.leaseValid',server+'.leaseValid')
        else:edge(server+'.abort',client+'.abort')
    observed('PublicDenseReductionHarness','io.dense','coordinator.io.dense')
    request('top.io.dense.request','top.coordinator.io.dense.request')
    result('top.io.dense.result','top.coordinator.io.dense.result')
    edge('top.coordinator.io.dense.abort','top.io.dense.abort')
    for field in ('busy','resetRequired'):edge('top.io.dense.'+field,'top.coordinator.io.dense.'+field)
    roots=('top.coordinator.io.drain.abort','top.coordinator.io.backendAbort',
           'top.coordinator.io.backendReset','top.coordinator.io.sumBankGranted',
           'top.coordinator.bridge.io.bankGranted','top.vector.io.loan.abort',
           'top.vector.io.loan.result.valid','top.vector.io.loan.result.ready',
           'top.owner.io.tiles.abort','top.owner.io.tiles.write.valid',
           'top.io.dense.request.ready','top.io.dense.result.valid','top.io.dense.resetRequired')
    visited=set();active=[]
    def visit(node):
        if node in active:raise ValueError('control combinational dependency cycle: '+' -> '.join(active[active.index(node):]+[node]))
        if node in visited:return
        active.append(node);deps=set(graph.get(node,()))
        if node not in graph:
            for target,sources in aliases.items():
                if node.startswith(target+'.') or node.startswith(target+'['):
                    suffix=node[len(target):];deps.update(source+suffix for source in sources)
        for dep in deps:visit(dep)
        active.pop();visited.add(node)
    for root in roots:
        if root not in graph:raise ValueError('missing audited control endpoint: '+root)
        visit(root)
    return dict(status='PASS_CONSERVATIVE_PUBLIC_COORDINATOR_OWNER_BANK_LOAN_CONTROL',
                audited_roots=roots,visited_dependencies=len(visited),full_design_rtl_loop_check=False)


def audit(out,baseline_report):
    helper=module('public_reduction_normalizer',ROOT/'scripts/check_matrix_interface_candidate.py')
    official=module('public_reduction_inventory',TASK.parent/'official_bf16/check_frontend.py')
    regs=module('public_reduction_registers',TASK.parent/'transposed_host/check_frontend.py')
    banks=module('public_reduction_bank_audit',TASK.parent/'ffn_window/check_frontend.py')
    fir=official.normalized((out/'chirrtl'/(PROFILE+'.fir')).read_text(),helper)
    inv=official.resource_inventory(fir,regs)
    counts={}
    def walk(name):
        counts[name]=counts.get(name,0)+1
        for child in inv['instances_by_module'][name].values():walk(child)
    walk('PublicDenseReductionHarness')
    for name,n in (('TransposedDenseDownOwner',1),('TransposedDownDenseBanks',1),('DenseBlockReductionCoordinator',1),
                   ('DenseTileSumBridge',1),('VectorSiluOwner',1),('SiluVectorUnit',1),('BlockScalarFloat',16)):
        if sum(count for cls,count in counts.items() if re.fullmatch(re.escape(name)+r'(?:_\d+)?',cls))!=n:
            raise ValueError('public resource multiplicity: '+name)
    if any('Matrix' in name and not name.startswith('Queue') for name in counts):raise ValueError('new Matrix array elaborated')
    old=baseline_report['combined_resources']
    for name in ('TransposedDenseDownOwner','TransposedDownDenseBanks','VectorSiluOwner','SiluVectorUnit'):
        for key in ('registers_by_module','memories_by_module','instances_by_module'):
            if inv[key][name]!=old[key][name]:raise ValueError('shared resource drift: '+name+'/'+key)
    registers=inv['registers_by_module']
    if registers['TransposedDenseDownOwner']['finalValue']['bits']!=131072:raise ValueError('existing finalValue drift')
    if registers['DenseTileSumBridge']['lhs']['bits']!=512:raise ValueError('sum bridge hold drift')
    fence=registers['PublicDenseReductionHarness']
    if set(fence)!={'matrixOutstanding','readOutstanding','writeOutstanding','backendFault'} or any(v['bits']!=1 for v in fence.values()):
        raise ValueError('only four physical-fence/fault bits are allowed in wrapper')
    if inv['memories_by_module']['DenseBlockReductionCoordinator']:
        raise ValueError('coordinator added memory')
    if set(inv['instances_by_module']['DenseBlockReductionCoordinator'].values())!={'DenseTileSumBridge'}:
        raise ValueError('coordinator added arithmetic/bank instances')
    result=dict(resource_inventory=inv,instance_counts=counts,bank_audit=banks.memory_audit(fir,allow_operand_queue=True),
                wrapper_metadata_bits=4,coordinator_register_bits=sum(v['bits'] for v in registers['DenseBlockReductionCoordinator'].values()),
                new_payload_buffers=0,new_sram_arrays=0,new_arithmetic_instances=0,
                existing_final_value_bits=131072,existing_sum_lhs_hold_bits=512,
                actual_external_backend_ports=True,accepted_obligation_fences=True,
                public_full_job_coordinator_connected=True,host_parser_dispatch_connected=False,
                rtl_generated=False,hardware_arithmetic_executed=False)
    result['control_dependencies']=control_dependencies(fir)
    needle='connect io.drain.abort, cancel'
    if fir.count(needle)!=1:raise ValueError('missing unique registered-cancel drain abort')
    try:control_dependencies(fir.replace(needle,'connect io.drain.abort, bad'))
    except ValueError as exc:
        if 'cycle' not in str(exc):raise
        result['negative_current_bad_to_drain_abort_rejected']=True
        result['negative_probe_cycle']=str(exc)
    else:raise ValueError('control audit failed to reject current-bad drain abort feedback')
    result['status']='PASS_PUBLIC_DENSE_COORDINATOR_SHARED_RESOURCE_FRONTEND_ONLY'
    return result


def official_resources(out):
    helper=module('public_default_normalizer',ROOT/'scripts/check_matrix_interface_candidate.py')
    official=module('public_default_inventory',TASK.parent/'official_bf16/check_frontend.py')
    regs=module('public_default_registers',TASK.parent/'transposed_host/check_frontend.py')
    ir={p.stem:official.normalized(p.read_text(),helper) for p in (out/'chirrtl').glob('*.fir')}
    inv={p:official.resource_inventory(f,regs) for p,f in ir.items()}
    result={'default_off_ir':{},'k_window_resource_delta':{},'binary_add_register_delta':{}}
    pairs=(('parent_default','disabled_default'),('parent_official','disabled_official'),
           ('drain_parent','enabled_burst'),('vector_before_legacy','vector_default'),
           ('vector_before_official','vector_disabled_official'),('owner_before','owner_disabled'))
    for before,after in pairs:
        if ir[before]!=ir[after]:raise ValueError('default-off IR drift: '+before+'/'+after)
        result['default_off_ir'][before+'/'+after]={'equal':True,'normalized_sha256':sha(ir[before].encode())}
    base=inv['disabled_official']
    for profile in ('enabled_official','enabled_burst'):
        current=inv[profile]
        for key in ('instances_by_module','memories_by_module'):
            if current[key]!=base[key]:raise ValueError('K-window resource drift: '+profile+'/'+key)
        old=base['registers_by_module']['TransposedDenseDownOwner']
        new=current['registers_by_module']['TransposedDenseDownOwner']
        if any(k not in new or new[k]!=v for k,v in old.items()):raise ValueError('K-window existing register changed')
        delta={k:v for k,v in new.items() if k not in old}
        if set(delta)!={'kPolicy'} or delta['kPolicy']['bits']!=66:raise ValueError('K-window metadata delta drift')
        result['k_window_resource_delta'][profile]={'metadata_bits':66,'new_payload_buffers':0,'new_sram_arrays':0}
    for before,after in (('vector_default','vector_enabled_legacy'),('vector_disabled_official','vector_enabled_official')):
        a,b=inv[before],inv[after]
        for key in ('instances_by_module','memories_by_module'):
            if a[key]!=b[key]:raise ValueError('Vector Add resource drift: '+key)
        delta=b['hierarchical_register_bits']-a['hierarchical_register_bits']
        if delta!=1:raise ValueError('Vector Add must add only one mode bit')
        if any(b['memories_by_module'].values()):raise ValueError('Vector Add memory allocation')
        lanes=b['instances_by_module']['SiluVectorUnit']
        if len(lanes)!=16 or not all(re.fullmatch(r'BlockScalarFloat(?:_\d+)?',n) for n in lanes.values()):
            raise ValueError('Vector Add changed original sixteen lanes')
        result['binary_add_register_delta'][after]=delta
    # These are actual standalone modules elaborated in the same compilation.
    # Compare the public hierarchy against them without a second sum harness.
    selected={'TransposedDenseDownOwner':'enabled_burst','TransposedDownDenseBanks':'enabled_burst',
              'VectorSiluOwner':'owner_disabled','SiluVectorUnit':'vector_enabled_official'}
    reference={key:{name:inv[profile][key][name] for name,profile in selected.items()}
               for key in ('registers_by_module','memories_by_module','instances_by_module')}
    result['standalone_reference_profiles']=selected
    return result,{'combined_resources':reference}


def add_parent(source,text,name):
    body='class '+name+text.split('class TransposedDenseDownOwner',1)[1]
    body=body.replace(' extends Module {',' extends Module {\n  override def desiredName = "TransposedDenseDownOwner"',1)
    target=source/(name+'.scala')
    target.write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+body)
    return target


def compose_official(source,report):
    sys.path.insert(0,str(ROOT))
    from candidates.qwen2_resident_matrix.dense_block_reduce import check_vector_add as vector
    drain=module('public_dense_drain_source_audit',TASK/'check_dense_drain_frontend.py')
    additions=[add_parent(source,(source/OWNER).read_text(),'DenseKWindowParent')]
    for patch in ('k_window.patch','dense_drain.patch','vector_add.patch'):
        if patch=='dense_drain.patch':
            before=(source/OWNER).read_text();additions.append(add_parent(source,before,'DenseDrainParent'))
        if patch=='vector_add.patch':
            vector_before=(source/vector.VECTOR).read_text()
            path=source/'VectorAddBaseline.scala';path.write_text(vector.baseline_source(vector_before));additions.append(path)
        subprocess.run(['git','apply','--check',str(TASK/patch)],cwd=source,check=True)
        subprocess.run(['git','apply',str(TASK/patch)],cwd=source,check=True)
        if patch=='dense_drain.patch':report['dense_drain_source_audit']=drain.audit_source(before,(source/OWNER).read_text())
    report['vector_add_source_audit']=vector.audit({vector.VECTOR:vector_before},{vector.VECTOR:(source/vector.VECTOR).read_text()})
    for name in ('KWindowElaboration.scala','DenseDrainElaboration.scala','VectorAddElaboration.scala'):
        target=source/name;shutil.copyfile(TASK/name,target);additions.append(target)
    return additions


def verified_cache_argv(argv,cache,baseline):
    # Require every dependency already present and hash pinned. This gate
    # never installs or downloads tools; the earlier frontend owns cache setup.
    helper=module('public_cache_helper',ROOT/'scripts/check_matrix_interface_candidate.py')
    receipt=json.loads((baseline/'dependency_receipt.json').read_text())
    lock=ROOT/'chisel/rope_hardware_oracle/maven-lock.json'
    if sha(lock.read_bytes())!=receipt['lock_sha256']:raise ValueError('Maven lock drift')
    deps=helper.dependency_paths(json.loads(lock.read_text())['artifacts'])
    if len(deps)!=87:raise ValueError('Maven dependency count drift')
    for path,digest in deps.items():
        if sha((cache/path).read_bytes())!=digest:raise ValueError('cache dependency drift: '+path)
    cp=':'.join(str(cache/path) for path in sorted(deps))
    result=list(argv)
    for flag in ('-cp','-classpath'):result[result.index(flag)+1]=cp
    plugins=[i for i,a in enumerate(result) if a.startswith('-Xplugin:')]
    if len(plugins)!=1:raise ValueError('expected single pinned Chisel compiler plugin')
    result[plugins[0]]='-Xplugin:'+str(cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar')
    return result


def run(baseline,out,cache=None):
    if out.exists():raise ValueError('use a fresh evidence directory')
    parent=json.loads((baseline/'summary.json').read_text())
    is_official=parent['status']==OFFICIAL_STATUS
    if not is_official and parent['status']!='PASS_DENSE_DRAIN_AND_REAL_SHARED_BANK_SUM_FRONTEND_ONLY':
        raise ValueError('verified official-BF16 or Dense-drain frontend baseline required')
    for p,d in parent['source_sha256'].items():
        if sha((baseline/p).read_bytes())!=d:raise ValueError('baseline source drift: '+p)
    out.mkdir(parents=True);start=time.monotonic()
    report=dict(status='STARTED',commands=[],baseline=str(baseline),baseline_receipt_sha256=sha((baseline/'summary.json').read_bytes()),
                rtl_generated=False,hardware_arithmetic_executed=False,host_parser_dispatch_connected=False)
    def save():(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def command(argv,log):
        entry=dict(argv=argv,log=log,status='RUNNING');report['commands'].append(entry);save()
        with (out/log).open('w') as f:r=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        entry.update(status='FINISHED',exit_code=r.returncode);save()
        if r.returncode:raise RuntimeError('failed: '+log)
    try:
        source=out/'source';shutil.copytree(baseline/'source',source)
        inputs=('DenseBlockReductionCoordinator.scala','DenseTileSumBridge.scala','PublicReductionElaboration.scala')
        if is_official:inputs+=('k_window.patch','dense_drain.patch','vector_add.patch','KWindowElaboration.scala','DenseDrainElaboration.scala','VectorAddElaboration.scala','check_vector_add.py','check_dense_drain_frontend.py')
        report['input_sha256']={n:sha((TASK/n).read_bytes()) for n in inputs}
        additions=compose_official(source,report) if is_official else []
        for name in ('DenseBlockReductionCoordinator.scala','DenseTileSumBridge.scala','PublicReductionElaboration.scala'):
            shutil.copyfile(TASK/name,source/name)
        argv=[a.replace(str(baseline),str(out)) for a in parent['commands'][0]['argv']]
        if cache is not None:
            if not is_official:raise ValueError('--cache override requires official-BF16 baseline')
            argv=verified_cache_argv(argv,cache,baseline)
        argv += [str(p) for p in additions]
        if is_official:argv.append(str(source/'DenseTileSumBridge.scala'))
        argv += [str(source/n) for n in ('DenseBlockReductionCoordinator.scala','PublicReductionElaboration.scala')]
        (out/'classes').mkdir()
        report['source_sha256']={str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted(source.rglob('*.scala'))}
        report['tooling_sha256']=sha(Path(__file__).read_bytes())
        command(argv,'compile.log');report['full_source_typechecked']=True
        cp=argv[argv.index('-cp')+1]
        if is_official:
            profiles=[('KWindowElaboration',p) for p in K_PROFILES]+[('DenseDrainElaboration','drain_parent')]+[('VectorAddElaboration',p) for p in VECTOR_PROFILES]
            for entry,profile in profiles:
                command(['java','-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',str(out/'classes')+':'+cp,
                         'heteronpu.continuous.'+entry,str(out/'chirrtl'),profile],profile+'.log')
        java=['java','-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',str(out/'classes')+':'+cp,
              'heteronpu.continuous.PublicReductionElaboration',str(out/'chirrtl'),PROFILE]
        command(java,PROFILE+'.log')
        report['generated_chirrtl_sha256']={p.name:sha(p.read_bytes()) for p in sorted((out/'chirrtl').glob('*.fir'))};save()
        if is_official:
            defaults,reference=official_resources(out);report.update(defaults)
        else:reference=parent
        report.update(audit(out,reference));report['single_overlay_compilation']=is_official
        for name,digest in report['input_sha256'].items():
            if sha((TASK/name).read_bytes())!=digest:raise ValueError('source changed during frontend run: '+name)
    except Exception as exc:
        report.update(status='FAILED',error=str(exc));raise
    finally:
        report['wall_seconds']=time.monotonic()-start;save()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cache',type=Path);p.add_argument('--audit-existing',action='store_true');a=p.parse_args()
    if a.audit_existing:
        out=a.out.resolve();report=json.loads((out/'summary.json').read_text())
        parent=json.loads((a.baseline.resolve()/'summary.json').read_text())
        is_official=parent['status']==OFFICIAL_STATUS
        expected=17 if is_official else 2
        if not report.get('full_source_typechecked') or len(report['commands'])!=expected or any(c.get('exit_code')!=0 for c in report['commands']):
            raise ValueError('compile and elaboration must already have succeeded')
        for path,digest in report['source_sha256'].items():
            if sha((out/path).read_bytes())!=digest:raise ValueError('assembled source drift: '+path)
        for name,digest in report['generated_chirrtl_sha256'].items():
            if sha((out/'chirrtl'/name).read_bytes())!=digest:raise ValueError('generated CHIRRTL drift: '+name)
        if is_official:
            defaults,reference=official_resources(out);report.update(defaults)
        else:reference=parent
        report.update(audit(out,reference));report.pop('error',None)
        report['final_auditor_sha256']=sha(Path(__file__).read_bytes());report['audit_only_no_new_java']=True
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
    else:print(run(a.baseline.resolve(),a.out.resolve(),a.cache.resolve() if a.cache else None)['status'])
