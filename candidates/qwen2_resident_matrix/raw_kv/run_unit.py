#!/usr/bin/env python3
"""Bounded bank-only Chisel/frontend/Verilator unit runner. Never full Matrix.

Uses the existing continuous-prefill CI tool versions in an isolated project.
Invoking this runner DOES compile/elaborate and simulate bank RTL.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_resident_matrix.raw_kv.check_source import check, TARGET
from candidates.qwen2_resident_matrix.raw_kv.stimuli import generate


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run_group(args, *, cwd, env, log, timeout, grace=5):
    """Terminate the whole child session on timeout, SIGTERM or interruption."""
    old=signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):raise InterruptedError('runner received SIGTERM')
    signal.signal(signal.SIGTERM,interrupted)
    proc=None
    try:
        proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:return proc.wait(timeout=timeout)
        except BaseException:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
            # Parent can exit before a TERM-resistant descendant. Kill its group too.
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            raise
    finally:signal.signal(signal.SIGTERM,old)


def memory_audit(text):
    memories=re.findall(r'^\s*smem (\w+) : UInt<256>\s*\[(\d+)\]',text,re.M)
    if len(memories)!=32 or sorted(int(d) for _,d in memories)!=[160]*16+[1376]*16:
        raise ValueError('actual CHIRRTL bank geometry mismatch')
    if len(re.findall(r'^\s*(?:s|c)mem ',text,re.M))!=32:raise ValueError('extra memory')
    for name,_ in memories:
        for kind in ('read','write'):
            if len(re.findall(r'^\s*'+kind+r' mport \w+ = '+re.escape(name)+r'\[',text,re.M))!=1:
                raise ValueError('actual CHIRRTL port mismatch')
    return {'memories':32,'a_banks':16,'a_depth':1376,'b_banks':16,'b_depth':160,'width':256,'read_ports_per_bank':1,'write_ports_per_bank':1}


def run(out):
    if out.exists():raise ValueError('fresh output required')
    out.mkdir(parents=True);project=out/'project';project.mkdir();evidence=out/'evidence';evidence.mkdir()
    start=time.monotonic();summary={'status':'STARTED','scope':'actual bank RTL only; no Matrix, owner, HardFloat or performance test','stages':[]}
    def save():(evidence/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    def command(name,args,budget):
        remaining=600-(time.monotonic()-start)
        if remaining<=0:raise TimeoutError('total 600s runner budget')
        t=time.monotonic();entry={'name':name,'budget_seconds':min(budget,int(remaining))};summary['stages'].append(entry);save()
        with (out/(name+'.log')).open('w') as log:
            try:rc=run_group(args,cwd=project,env=env,log=log,timeout=min(budget,remaining))
            except BaseException as error:
                entry.update(status='TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'INTERRUPTED',seconds=time.monotonic()-t);save();raise
        entry.update(status='PASS' if rc==0 else 'FAIL',exit_code=rc,seconds=time.monotonic()-t);save()
        if rc:raise RuntimeError(name+' failed; local log retained')
    env=dict(os.environ,RAW_KV_STIMULI=str(out/'stimuli.tsv'),MAKEFLAGS='-j1 VM_PARALLEL_BUILDS=0',
             JVM_OPTS='-Xmx2G -Xss4M -XX:ActiveProcessorCount=2',SBT_OPTS='-Dsbt.supershell=false -Dsbt.color=false -Dsbt.task.cpus=2')
    try:
        check()
        source=project/'src/main/scala';source.mkdir(parents=True);target=source/'TransposedDenseBanks.scala'
        # Compose the entire existing bank file, not a memory surrogate.
        target.write_bytes((ROOT/TARGET).read_bytes())
        tmp=project/TARGET;tmp.parent.mkdir(parents=True);tmp.write_bytes(target.read_bytes())
        for name in ['transposed_down/owner_down.patch','ffn_tiles/tile_ports.patch','raw_kv/raw_kv_port.patch']:
            patch=(HERE.parent/name).read_text();head='--- a/'+TARGET+'\n'
            section=head+patch.split(head)[1].split('\n--- a/')[0]+'\n'
            subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=section,text=True,cwd=project,check=True,capture_output=True,timeout=10)
        target.write_bytes(tmp.read_bytes())
        test=project/'src/test/scala';test.mkdir(parents=True);(test/'RawKvUnit.scala').write_bytes((HERE/'RawKvUnit.scala').read_bytes())
        (project/'project').mkdir();(project/'project/build.properties').write_text('sbt.version=1.10.2\n')
        (project/'build.sbt').write_text('''ThisBuild / scalaVersion := "2.13.16"
libraryDependencies ++= Seq("org.chipsalliance" %% "chisel" % "6.7.0", "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test, "org.scalatest" %% "scalatest" % "3.2.19" % Test)
addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full)
scalacOptions += "-language:reflectiveCalls"
Test / parallelExecution := false
lazy val writeDependencyPaths = taskKey[Unit]("Local dependency audit input")
writeDependencyPaths := IO.write(file("dependency-paths.txt"), (Test / externalDependencyClasspath).value.files.filter(_.getName.endsWith(".jar")).map(_.getAbsolutePath).mkString("\\n"))
''')
        summary['stimulus']=generate(out/'stimuli.tsv')
        frozen_stimulus=digest(out/'stimuli.tsv')
        source_paths=[target,test/'RawKvUnit.scala',HERE/'stimuli.py',HERE/'model.py',HERE/'raw_kv_port.patch',HERE/'run_unit.py',HERE/'check_source.py',HERE/'source_pins.json',HERE.parent/'transposed_down/model.py']+[project/'build.sbt',project/'project/build.properties',ROOT/'chisel/rope_hardware_oracle/maven-lock.json']
        workflow=ROOT/'.github/workflows/raw-kv-bank-unit.yml'
        if workflow.exists():source_paths.append(workflow)
        source_hashes={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p.relative_to(out)):digest(p) for p in source_paths}
        (evidence/'source-sha256.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
        command('dependencies',['sbt','update','writeDependencyPaths'],120)
        lock=json.loads((ROOT/'chisel/rope_hardware_oracle/maven-lock.json').read_text())['artifacts']
        locked={Path(k).name:v for k,v in lock.items() if k.endswith('.jar')}
        deps=[]
        for line in (project/'dependency-paths.txt').read_text().splitlines():
            p=Path(line);sha=digest(p)
            if p.name in locked and locked[p.name]!=sha:raise ValueError('locked dependency digest mismatch: '+p.name)
            deps.append({'jar':p.name,'sha256':sha,'existing_lock_match':p.name in locked})
        (evidence/'dependency-sha256.json').write_text(json.dumps(deps,indent=2)+'\n')
        command('compile',['sbt','Test / compile'],120)
        command('elaborate',['sbt','Test / runMain heteronpu.continuous.RawKvElaborate '+str(out/'chirrtl')],60)
        summary['frontend']={}
        for tiles in (0,1):
            for raw in (0,1):
                name=f'banks_tiles{tiles}_raw{raw}';p=out/'chirrtl'/(name+'.fir');text=p.read_text()
                summary['frontend'][name]=memory_audit(text)
                has_port=bool(re.search(r'rawKv\s*:',text))
                if has_port!=bool(raw):raise ValueError('optional port presence mismatch')
        save()
        if digest(out/'stimuli.tsv')!=frozen_stimulus:raise ValueError('stimulus changed before RTL')
        command('bank_rtl_unit',['sbt','testOnly heteronpu.continuous.RawKvUnit'],240)
        log=(out/'bank_rtl_unit.log').read_text()
        if not re.search(r'Total number of tests run: 3\b',log) or 'All tests passed' not in log:raise ValueError('missing exact three-test result')
        rtl=sorted((project/'test_run_dir').rglob('*.sv'))+sorted((project/'test_run_dir').rglob('*.v'))
        if not rtl:raise ValueError('no generated RTL')
        (evidence/'rtl-sha256.json').write_text(json.dumps({str(p.relative_to(project)):digest(p) for p in rtl},indent=2)+'\n')
        if digest(out/'stimuli.tsv')!=frozen_stimulus:raise ValueError('stimulus changed during RTL')
        for p in source_paths:
            if digest(p)!=source_hashes[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p.relative_to(out))]:raise ValueError('source changed during run')
        summary.update(status='PASS_BANK_UNIT_ONLY',hardware_performance_measured=False)
    except Exception as e:
        summary.update(status='FAIL',error=str(e));raise
    finally:
        # Preserve hashes even if compilation/simulation failed after RTL emission.
        rtl=sorted((project/'test_run_dir').rglob('*.sv'))+sorted((project/'test_run_dir').rglob('*.v'))
        if rtl:
            (evidence/'rtl-sha256.json').write_text(json.dumps({str(p.relative_to(project)):digest(p) for p in rtl},indent=2)+'\n')
        summary['wall_seconds']=time.monotonic()-start;save()
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    print(json.dumps(run(p.parse_args().out.resolve()),indent=2))
