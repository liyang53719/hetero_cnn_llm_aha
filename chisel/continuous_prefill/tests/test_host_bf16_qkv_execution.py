"""Validator adversarial tests using explicit mocked driver artifacts, never RTL."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import host_bf16_qkv_execution as execution
import pack_host_bf16_qkv_fixture as pack
import test_host_bf16_qkv_fixture as fixtures


class HostQkvExecutionTests(unittest.TestCase):
    def setUp(self):
        self.source=fixtures.HostQkvFixtureTests(); self.source.setUp()
        self.fixture=self.source.base/'fixture'
        pack.pack_fixture(self.fixture,token_base=127,phase='carried',session=self.source.session)
        self.layout,self.specs=execution._layout(self.fixture)

    def tearDown(self):self.source.tearDown()

    def fake_artifacts(self,mode='pass'):
        """Unit-only native-valued output bytes; no numerical acceptance claim."""
        output=self.source.base/('mock_'+mode); output.mkdir()
        log=self.source.base/(mode+'.log'); lines=[]; cycle=0
        def event(kind,**fields):
            self.assertEqual(set(fields),set(execution.SCHEMA[kind].split()))
            lines.append(execution.PREFIX+kind+' '+' '.join(key+'='+str(value) for key,value in fields.items()))
        modes=[mode,'pass'] if mode=='reset-recovery' else [mode]
        for run,selected in enumerate(modes):
            directory=output if run==0 else output/'recovery'; directory.mkdir(exist_ok=True)
            memory=execution._initial(self.fixture,self.layout,self.specs,selected)
            references={}
            for role,spec in zip(pack.ROLES,self.specs):
                native=(self.fixture/('native_'+role+'.bf16le')).read_bytes()
                start=self.layout['first']*spec['n']*2; references[role]=native[start:start+spec['bytes']]
                (directory/('reference_'+role+'.bf16le')).write_bytes(references[role])
            failed=1 if selected=='output-alias' else 0 if selected=='reset-recovery' else 2
            successful=3 if selected=='pass' else failed; completions=3 if selected=='pass' else failed+1
            ack_total=0; accepted_total=0
            event('BEGIN',run=run,mode=selected,commands=3,epoch=9+run)
            for pc in range(completions):
                spec=self.specs[pc]; role=pack.ROLES[pc]; ok=pc<successful; ack=0
                if ok or selected=='last-write-error':
                    for address in range(spec['begin'],spec['end'],1024):
                        size=min(1024,spec['end']-address); final=int(address+size==spec['end']); cycle+=1
                        event('WRITE_REQUEST',run=run,pc=pc,cycle=cycle,address=address,bytes=size,final=final)
                        cycle+=64; error=int(selected=='last-write-error' and pc==2 and final)
                        event('WRITE_ACK',run=run,pc=pc,cycle=cycle,address=address,bytes=size,error=error,final=final)
                        accepted_total+=size
                        if not error:
                            offset=address-self.layout['base']; source=address-spec['begin']
                            memory[offset:offset+size]=references[role][source:source+size]; ack+=size; ack_total+=size
                status=0 if ok else 9 if selected=='output-alias' else 3
                for _ in range(11):
                    cycle+=1; event('COMPLETION_HOLD',run=run,pc=pc,cycle=cycle,word=pc|2<<29|status<<32|(pc+1)<<40)
                cycle+=1
                event('COMMAND',run=run,cycle=cycle,role=role,pc=pc,status=status,signal=pc+1,write_ack_bytes=ack,published=int(ok),previous_outputs_preserved=1,guards_unchanged=1)
                (directory/('writable_after_command'+str(pc)+'.bin')).write_bytes(memory[self.layout['scratch']-self.layout['base']:])
            (directory/'ddr_after.bin').write_bytes(memory)
            for role,spec in zip(pack.ROLES,self.specs):
                offset=spec['begin']-self.layout['base']; actual=memory[offset:offset+spec['bytes']]
                (directory/('actual_'+role+'.bf16le')).write_bytes(actual)
            published=sum(spec['bytes'] for spec in self.specs[:successful]); metadata=22*completions
            if selected=='pass':
                for stage,elements in (('q_content',2048),('q_gate',2048),('k',512),('v',512)):
                    event('NATIVE',run=run,stage=stage,elements=elements,bit_differences=0,max_abs=0,mean_abs=0,gate='PASS')
                event('PASS',run=run,scope='PROJECTION_ONLY',commands=3,tokens=1,token_base=127,checked_bf16=5120,
                    canonical_bit_differences=0,independent_terminal_checked=0,native_operator_gate='PASS',cycles=cycle,
                    write_ack_bytes=ack_total,metadata_reads=metadata,logical_matrix_engines=1,physical_matrix_slices=8,
                    idma_instances=1,unchanged_guards=1,prior_outputs_preserved=1,delayed_final_ack_commands=3,
                    completion_backpressure_commands=3,norm_supported=0,rope_supported=0,full_block_supported=0)
            else:
                event('FAULT_PASS',run=run,mode=selected,failed_pc=failed,status=status,successful_commands=successful,
                    write_ack_bytes=ack_total,published_bytes=published,failed_command_published_bytes=0,previous_outputs_preserved=1,guards_unchanged=1)
            event('END',run=run,status=0 if selected=='pass' else status,result_epoch=9+run,result_pc=completions-1,
                completions=completions,successful=successful,
                issued_jobs=1 if selected=='output-alias' else completions,metadata_reads=metadata,read_beats=metadata,
                read_ack_beats=metadata,write_beats=accepted_total//64,write_ack_beats=accepted_total//64,
                published_bytes=published,reset_required=int(selected!='pass'))
        if mode=='reset-recovery':event('RESET_RECOVERY_PASS',same_dut=1,unchanged_input_constants=1,expected_output_injection=0,commands=3)
        log.write_text('\n'.join(lines)+'\n')
        return output,log

    def verify(self,output,log,mode='pass'):
        return execution.verify_execution(self.fixture,output,log,mode,session=self.source.session)

    def test_all_modes_verify_raw_memory_and_source_failures(self):
        for mode in execution.MODES:
            with self.subTest(mode=mode):
                output,log=self.fake_artifacts(mode); result=self.verify(output,log,mode)
                self.assertEqual(result['status'],'PASS_C_ONLY_HOST_QKV_ARTIFACT_DIAGNOSTIC')
                self.assertFalse(result['actual_dut_identity_verified'])
                self.assertFalse(result['numerical_acceptance_eligible'])
                self.assertFalse(result['native_full_block_failures']['baseline']['gate_pass'])
                self.assertEqual(result['runs'][-1]['successful_commands'],3 if mode in ('pass','reset-recovery') else 1 if mode=='output-alias' else 2)

    def test_unknown_duplicate_missing_command_and_early_ack_rejected(self):
        output,log=self.fake_artifacts(); original=log.read_text(); rows=original.splitlines()
        command=next(line for line in rows if line.startswith(execution.PREFIX+'COMMAND '))
        mutations=[original+execution.PREFIX+'INVENTED pass=1\n',original.replace(command,command+'\n'+command),original.replace(command+'\n',''),
                   original.replace('result_epoch=9','result_epoch=10'),original.replace('result_pc=2','result_pc=1')]
        first_hold={}; repeated=[]
        for line in rows:
            if line.startswith(execution.PREFIX+'COMPLETION_HOLD '):
                fields=dict(part.split('=') for part in line.split()[1:]); key=fields['pc']
                first_hold.setdefault(key,line); line=first_hold[key]
            repeated.append(line)
        mutations.append('\n'.join(repeated)+'\n')
        first_request=next(i for i,line in enumerate(rows) if line.startswith(execution.PREFIX+'WRITE_REQUEST ') and 'final=1' in line)
        req_cycle=int(dict(part.split('=') for part in rows[first_request].split()[1:])['cycle'])
        ack=rows[first_request+1]; tokens=ack.split(); tokens=[('cycle='+str(req_cycle+1)) if value.startswith('cycle=') else value for value in tokens]
        mutations.append(original.replace(ack,' '.join(tokens)))
        # Move publication before the final ACK; raw snapshots alone must not hide this.
        mutations.append(original.replace(command+'\n','').replace(ack,command+'\n'+ack))
        for changed in mutations:
            log.write_text(changed)
            with self.assertRaises(ValueError):self.verify(output,log)

    def test_final_and_intermediate_physical_corruption_rejected(self):
        output,log=self.fake_artifacts()
        for filename,offset in (('ddr_after.bin',self.layout['aa']-self.layout['base']),
                                ('writable_after_command2.bin',self.specs[0]['begin']-self.layout['scratch']),
                                ('writable_after_command1.bin',0)):
            with self.subTest(filename=filename):
                path=output/filename; original=path.read_bytes(); changed=bytearray(original); changed[offset]^=1; path.write_bytes(changed)
                with self.assertRaises(ValueError):self.verify(output,log)
                path.write_bytes(original)

    def test_missing_role_and_false_native_metric_rejected(self):
        output,log=self.fake_artifacts(); original=log.read_text()
        log.write_text(original.replace('stage=q_gate elements=2048 bit_differences=0 max_abs=0','stage=q_gate elements=2048 bit_differences=0 max_abs=0.01'))
        with self.assertRaises(ValueError):self.verify(output,log)
        log.write_text(original)
        path=output/'actual_k.bf16le'; raw=path.read_bytes(); changed=bytearray(raw); changed[0]^=1; path.write_bytes(changed)
        with self.assertRaises(ValueError):self.verify(output,log)

    def test_actual_gate_blocks_missing_independent_terminals_before_dut_work(self):
        with patch.object(execution,'_build_identity') as identity,patch.object(execution.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'BLOCKED_INDEPENDENT_TERMINALS_REQUIRED'):
                execution.run_case(self.source.base/'not_a_build',self.fixture,session=self.source.session)
            identity.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
