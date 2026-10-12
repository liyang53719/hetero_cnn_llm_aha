#!/usr/bin/env python3
"""Actual shared Dense/bank/sum/Vector CHIRRTL gate; never RTL or simulation."""
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
OWNER='candidates/qwen2_resident_matrix/transposed_owner/TransposedDenseOwner.scala'
PROFILES=('drain_parent','drain_disabled','drain_enabled','drain_enabled_burst','combined_dense_sum')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj


def audit_source(before,after):
    # Only the constructor and request admission may differ. The physical
    # tile/read/hold/write/ACK/drain/release datapath remains byte-identical.
    suffix='    when(active){\n      // This mode issues no Matrix, A load, prefix restore or tile write.'
    if before.split(suffix,1)[1]!=after.split(suffix,1)[1]:
        raise ValueError('Dense drain changed the physical execution/ACK lifecycle')
    prefix='    when(d.request.fire){'
    oldpre=before.split(prefix,1)[0]
    newpre=after.split(prefix,1)[0]
    newpre=newpre.replace(',enableDenseDrain:Boolean=false) extends Module {',') extends Module {',1)
    newpre=newpre.replace('  require(!enableDenseDrain || enableFfnDrain,"Dense tile drain requires the existing drain port")\n','',1)
    if oldpre!=newpre:
        raise ValueError('Dense drain changed source outside constructor/admission')
    for text in ('j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W))',
                 'j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))',
                 '!j.outputBf16 && !j.materializeDenseOutput', 'j.m<=j.k && j.k<=1536.U',
                 'j.n>0.U && j.n<=j.k', 'j.writeBytes===size && disjoint && workspaceOK'):
        if text not in after:
            raise ValueError('missing complete Dense admission: '+text)
    return dict(physical_execution_ack_lifecycle_unchanged=True,
                change_scope=['default-off constructor flag','request shape and full dtype spans'],
                new_registers_by_source=False,new_payload_by_source=False)


def audit_control_dependencies(fir):
    """Conservative source-CHIRRTL handshake graph; not a full RTL loop proof."""
    text=re.sub(r' @\[[^\]]*\]','',fir)
    modules={m[1]:m[0] for m in re.finditer(r'^  module (\w+) :.*?(?=^  (?:extmodule|module) |\Z)',text,re.M|re.S)}
    chosen=(('DenseKReductionHarness','top'),('TransposedDenseDownOwner','top.dense'),
            ('TransposedDownDenseBanks','top.dense.banks'),('DenseTileSumBridge','top.bridge'),
            ('VectorSiluOwner','top.vector'),('SiluVectorUnit','top.vector.vector'))
    graph={};aliases={};registers=set();token=re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*')
    for name,prefix in chosen:
        body=modules[name]
        registers.update(prefix+'.'+r for r in re.findall(r'^\s*reg(?:reset)? (\w+) :',body,re.M))
        guards=[];last_when={}
        def refs(expr):return {prefix+'.'+x for x in token.findall(expr)}
        for line in body.splitlines()[1:]:
            indent=len(line)-len(line.lstrip());content=line.strip()
            guards=[(i,g) for i,g in guards if i<indent]
            if content.startswith('when '):
                condition=content[5:].rsplit(':',1)[0].strip();last_when[indent]=condition;guards.append((indent,condition))
            elif content.startswith('else :'):
                guards.append((indent,last_when[indent]))
            elif content.startswith('node '):
                lhs,rhs=content[5:].split(' = ',1);graph.setdefault(prefix+'.'+lhs,set()).update(refs(rhs))
            elif content.startswith('connect '):
                lhs,rhs=content[8:].split(', ',1);target=prefix+'.'+lhs
                if any(target==r or target.startswith(r+'.') or target.startswith(r+'[') for r in registers):continue
                graph.setdefault(target,set()).update(refs(rhs))
                if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*',rhs):
                    aliases.setdefault(target,set()).add(prefix+'.'+rhs)
                for _,guard in guards:graph[target].update(refs(guard))
    # CHIRRTL retains this mixed-direction aggregate connect. Expand its
    # actual declared loan protocol fields; otherwise a leaf-only graph would
    # silently omit the most important abort/result path across the borrower.
    if 'connect bridge.io.vector, vector.io.loan' not in modules['DenseKReductionHarness']:
        raise ValueError('expected actual aggregate Vector loan connection')
    to_vector=['abort','request.valid','request.bits.binaryAdd','result.ready']
    to_vector += ['request.bits.'+name+'['+str(i)+']' for name in ('gate','up') for i in range(16)]
    to_bridge=['busy','drained','resetRequired','request.ready','result.valid','result.bits.error']
    to_bridge += ['result.bits.value['+str(i)+']' for i in range(16)]
    for suffix in to_vector:
        graph.setdefault('top.vector.io.loan.'+suffix,set()).add('top.bridge.io.vector.'+suffix)
    for suffix in to_bridge:
        graph.setdefault('top.bridge.io.vector.'+suffix,set()).add('top.vector.io.loan.'+suffix)
    roots=('top.vector.io.loan.abort','top.vector.io.loan.result.valid','top.vector.io.loan.result.ready',
           'top.bridge.io.bankGranted','top.io.sum.ready','top.dense.io.tiles.abort','top.dense.io.tiles.write.valid')
    visited=set();active=[]
    def visit(node):
        if node in active:raise ValueError('control combinational dependency cycle: '+' -> '.join(active[active.index(node):]+[node]))
        if node in visited:return
        active.append(node)
        deps=set(graph.get(node,()))
        if node not in graph:
            # Same-direction payload bundle aliases keep their exact suffix.
            for target,sources in aliases.items():
                if node.startswith(target+'.') or node.startswith(target+'['):
                    suffix=node[len(target):]
                    deps.update(source+suffix for source in sources)
        for dep in deps:visit(dep)
        active.pop();visited.add(node)
    for root in roots:
        if root not in graph:raise ValueError('missing handshake endpoint: '+root)
        visit(root)
    return dict(status='PASS_CONSERVATIVE_REAL_BANK_BRIDGE_LOAN_DEPENDENCIES',audited_roots=roots,
                visited_dependencies=len(visited),full_design_rtl_loop_check=False)


def audit(out):
    report={}
    helper=module('dense_drain_normalizer',ROOT/'scripts/check_matrix_interface_candidate.py')
    official=module('dense_drain_inventory',TASK.parent/'official_bf16/check_frontend.py')
    regs=module('dense_drain_register_inventory',TASK.parent/'transposed_host/check_frontend.py')
    bank=module('dense_drain_bank_audit',TASK.parent/'ffn_window/check_frontend.py')
    norm={p:official.normalized((out/'chirrtl'/(p+'.fir')).read_text(),helper) for p in PROFILES}
    report['disabled_ir_equal']=norm['drain_parent']==norm['drain_disabled']
    if not report['disabled_ir_equal']:
        import difflib
        (out/'disabled.diff').write_text(''.join(difflib.unified_diff(norm['drain_parent'].splitlines(True),norm['drain_disabled'].splitlines(True))))
        raise ValueError('Dense drain disabled IR changed')
    inventories={p:official.resource_inventory(f,regs) for p,f in norm.items()}
    baseline_inv=inventories['drain_disabled']
    report['owner_resource_checks']={}
    for profile in ('drain_enabled','drain_enabled_burst'):
        inv=inventories[profile]
        for key in ('registers_by_module','memories_by_module','instances_by_module'):
            if inv[key]!=baseline_inv[key]:raise ValueError('Dense drain resource drift: '+profile+'/'+key)
        report['owner_resource_checks'][profile]=dict(new_register_bits=0,new_payload_buffers=0,new_memories=0,
                                                    banks=bank.memory_audit(norm[profile],allow_operand_queue=True))
    combo=inventories['combined_dense_sum'];report['combined_resources']=combo
    report['combined_bank_audit']=bank.memory_audit(norm['combined_dense_sum'],allow_operand_queue=True)
    counts={}
    def walk(name):
        counts[name]=counts.get(name,0)+1
        for child in combo['instances_by_module'][name].values():walk(child)
    walk('DenseKReductionHarness')
    for name,n in (('TransposedDenseDownOwner',1),('TransposedDownDenseBanks',1),('DenseTileSumBridge',1),('VectorSiluOwner',1),('SiluVectorUnit',1),('BlockScalarFloat',16)):
        if sum(count for cls,count in counts.items() if re.fullmatch(re.escape(name)+r'(?:_\d+)?',cls))!=n:
            raise ValueError('combined resource multiplicity: '+name)
    if any('Matrix' in name and not name.startswith('Queue') for name in counts):
        raise ValueError('unexpected Matrix array elaboration')
    if combo['registers_by_module']['TransposedDenseDownOwner']['finalValue']['bits']!=131072:raise ValueError('existing finalValue changed')
    if combo['registers_by_module']['DenseTileSumBridge']['lhs']['bits']!=512:raise ValueError('bounded sum lhs hold changed')
    report['combined_instance_counts']=counts
    report['combined_control_dependencies']=audit_control_dependencies(norm['combined_dense_sum'])
    needle='connect io.vector.abort, loanAbort'
    if norm['combined_dense_sum'].count(needle)!=1:
        raise ValueError('missing unique real loan abort assignment')
    try:
        audit_control_dependencies(norm['combined_dense_sum'].replace(needle,'connect io.vector.abort, bad'))
    except ValueError as exc:
        if 'cycle' not in str(exc):raise
        report['negative_abort_feedback_probe_rejected']=True
    else:
        raise ValueError('dependency auditor missed arithmetic-error abort feedback')
    report['status']='PASS_DENSE_DRAIN_AND_REAL_SHARED_BANK_SUM_FRONTEND_ONLY'
    return report


def run(baseline,out):
    if out.exists():raise ValueError('use fresh evidence directory')
    parent=json.loads((baseline/'summary.json').read_text())
    if parent['status']!='PASS_K_WINDOW_OWNER_FRONTEND_ONLY':raise ValueError('verified K-window baseline required')
    for p,d in parent['source_sha256'].items():
        if sha((baseline/p).read_bytes())!=d:raise ValueError('baseline source changed: '+p)
    out.mkdir(parents=True);start=time.monotonic()
    report=dict(status='STARTED',commands=[],baseline=str(baseline),baseline_sha256=sha((baseline/'summary.json').read_bytes()),
                rtl_generated=False,hardware_arithmetic_executed=False,production_host_coordinator_connected=False)
    def save():(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def command(argv,log):
        entry=dict(argv=argv,log=log,status='RUNNING');report['commands'].append(entry);save()
        with (out/log).open('w') as f:result=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        entry.update(status='FINISHED',exit_code=result.returncode);save()
        if result.returncode:raise RuntimeError('failed: '+log)
    try:
        source=out/'source';shutil.copytree(baseline/'source',source)
        before=(source/OWNER).read_text()
        body='class DenseDrainParent'+before.split('class TransposedDenseDownOwner',1)[1]
        body=body.replace(' extends Module {',' extends Module {\n  override def desiredName = "TransposedDenseDownOwner"',1)
        base=source/'DenseDrainParent.scala';base.write_text('package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'+body)
        for patch in ('dense_drain.patch','vector_add.patch'):
            subprocess.run(['git','apply','--check',str(TASK/patch)],cwd=source,check=True)
            subprocess.run(['git','apply',str(TASK/patch)],cwd=source,check=True)
        report['source_audit']=audit_source(before,(source/OWNER).read_text())
        additions=[base]
        for name in ('DenseTileSumBridge.scala','DenseDrainElaboration.scala'):
            path=source/name;shutil.copyfile(TASK/name,path);additions.append(path)
        argv=[a.replace(str(baseline),str(out)) for a in parent['commands'][0]['argv']]
        argv += [str(p) for p in additions]
        (out/'classes').mkdir()
        report['source_sha256']={str(p.relative_to(out)):sha(p.read_bytes()) for p in sorted(source.rglob('*.scala'))}
        report['tooling_sha256']={n:sha((TASK/n).read_bytes()) for n in ('dense_drain.patch','vector_add.patch','DenseTileSumBridge.scala','DenseDrainElaboration.scala','check_dense_drain_frontend.py')}
        command(argv,'compile.log');report['full_source_typechecked']=True
        cp=argv[argv.index('-cp')+1]
        java=['java','-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',str(out/'classes')+':'+cp,
              'heteronpu.continuous.DenseDrainElaboration',str(out/'chirrtl')]
        for profile in PROFILES:command(java+[profile],profile+'.log')
        report['generated_chirrtl_sha256']={p.name:sha(p.read_bytes()) for p in sorted((out/'chirrtl').glob('*.fir'))}
        save()
        report.update(audit(out))
    except Exception as exc:
        report.update(status='FAILED',error=str(exc));raise
    finally:
        report['wall_seconds']=time.monotonic()-start;save()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--audit-existing',action='store_true')
    a=p.parse_args()
    if a.audit_existing:
        out=a.out.resolve();report=json.loads((out/'summary.json').read_text())
        if not report.get('full_source_typechecked') or len(report['commands'])!=len(PROFILES)+1 or any(c.get('exit_code')!=0 for c in report['commands']):
            raise ValueError('all compile/elaboration commands must already have succeeded')
        for name,digest in report['source_sha256'].items():
            if sha((out/name).read_bytes())!=digest:raise ValueError('assembled source drift: '+name)
        current_ir={p.name:sha(p.read_bytes()) for p in sorted((out/'chirrtl').glob('*.fir'))}
        if report.get('generated_chirrtl_sha256',current_ir)!=current_ir:
            raise ValueError('generated CHIRRTL changed since elaboration receipt')
        report['generated_chirrtl_sha256']=current_ir
        report.update(audit(out));report.pop('error',None)
        report['final_auditor_sha256']=sha(Path(__file__).read_bytes())
        report['audit_only_no_new_java']=True
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report['status'])
    else:
        print(run(a.baseline.resolve(),a.out.resolve())['status'])
