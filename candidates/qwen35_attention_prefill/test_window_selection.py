"""Cold-only selection/fixture controls, not owner arithmetic or capture evidence."""
from copy import deepcopy
from pathlib import Path
import json
import struct
import tempfile
import unittest
from unittest.mock import patch

from . import input_fixture as f, run_fullblock as runner
from .norm_rope import fixture as nr
from .test_input_fixture import metadata


class WindowSelectionTests(unittest.TestCase):
    def manifest(self, rows=128):
        return dict(query_tokens=rows, cases=[dict(name='cold'+str(rows)), dict(name='carried'+str(rows))])

    def test_default_keeps_original_two_ordered_windows(self):
        for rows in (16, 128):
            manifest = self.manifest(rows)
            self.assertEqual(f.select_windows(manifest), tuple(manifest['cases']))
            self.assertEqual(f.requested_case_names(rows), ('cold'+str(rows), 'carried'+str(rows)))

    def test_cold_only_requires_full_capture_but_selects_one_case(self):
        manifest = self.manifest()
        before = deepcopy(manifest)
        self.assertEqual(f.select_windows(manifest, ('cold',)), (manifest['cases'][0],))
        self.assertEqual(manifest, before)
        manifest['cases'].pop()
        with self.assertRaises(ValueError):
            f.select_windows(manifest, ('cold',))

    def test_empty_duplicate_unknown_carried_only_and_non_tuple_rejected(self):
        for windows in ((), ('cold','cold'), ('carried',), ('carried','cold'), ('unknown',),
                        ['cold'], 'cold', None, (True,)):
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                f.select_windows(self.manifest(), windows)
        for rows in (True, 0, 1, 129):
            with self.assertRaises(ValueError):
                f.requested_case_names(rows, ('cold',))

    def test_reversed_duplicate_or_extra_capture_cases_rejected(self):
        for names in (('carried128','cold128'), ('cold128','cold128'),
                      ('cold128','carried128','extra')):
            manifest = dict(query_tokens=128,cases=[dict(name=n) for n in names])
            with self.assertRaises(ValueError):
                f.select_windows(manifest, ('cold',))

    def test_default_and_cold_trig_tables_keep_exact_position_layout(self):
        for rows in (16,128):
            cold = dict(cos=struct.pack('<H',0x3f80)*(rows*64),sin=bytes(rows*128))
            carry = dict(cos=struct.pack('<H',0x4000)*(rows*64),sin=bytes(rows*128))
            pair, default = nr.build_trig_table({'cold'+str(rows):cold,'carried'+str(rows):carry}, rows)
            only, scope = nr.build_trig_table({'cold'+str(rows):cold}, rows, windows=('cold',))
            self.assertEqual(pair[:128*128], only[:128*128])
            self.assertEqual(only[128*128:],bytes(128*128))
            self.assertEqual(default['captured_position_spans'],[[0,rows],[128,128+rows]])
            self.assertEqual(default['zero_filled_unread_spans'],[] if rows==128 else [[16,128],[144,256]])
            self.assertEqual(scope['captured_position_spans'],[[0,rows]])
            self.assertEqual(scope['zero_filled_unread_spans'],[[rows,256]])
            with self.assertRaises(ValueError):
                nr.build_trig_table({'cold'+str(rows):cold,'carried'+str(rows):carry},rows,windows=('cold',))

    def test_loader_preserves_whole_capture_seal_and_reads_only_selected_hidden(self):
        # Deliberate metadata controls. Real capture validation is not claimed.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'capture';directory.mkdir();payload_dir=root/'payload';payload_dir.mkdir()
            params=json.loads((f.ROOT/'candidates/qwen35_attention_prefill/projection_profile.json').read_text())
            profile=root/'candidates/qwen35_attention_prefill/projection_profile.json';profile.parent.mkdir(parents=True);profile.write_text(json.dumps(params))
            manifest,payload=metadata()
            environment={k:v for k,v in params['backend'].items() if k not in ('torch','transformers','framework_revision')}
            environment.update(variant='baseline',eval=True,inference=True,packages={k:params['backend'][k] for k in ('torch','transformers')})
            manifest.update(environment=environment,framework_revision=params['backend']['framework_revision'],source_files={},runtime_files={},case_identity='metadata_test_only')
            (payload_dir/'manifest.json').write_text(json.dumps(payload));(directory/'manifest.json').write_text(json.dumps(manifest))
            weights={name:b'weight' for name in f.WEIGHTS.values()}
            with patch.object(f.capture,'validate_manifest') as seal, patch.object(f.capture,'recover_tensor_journal',return_value={'tensors':manifest['tensors'],'ignored_unterminated_tail_bytes':0}), patch('heteronpu.pinned_block_payload.load_payload',return_value=(payload,weights)), patch.object(f,'read_tensor',return_value=bytes(16*2048)) as read:
                _,_,inputs,identity=f.load_fixture(directory,payload_dir,root,windows=('cold',))
                seal.assert_called_once_with(manifest,directory)
                self.assertEqual(list(inputs),['cold16']);self.assertEqual(read.call_count,1)
                self.assertEqual(read.call_args.args[2],'cold16.hidden')
                self.assertTrue(identity['complete_capture_seal_validated'])
                self.assertEqual(identity['selected_case_names'],['cold16'])

    def test_invalid_selection_is_rejected_before_output_or_fixture_work(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(runner.fixture,'load_fixture') as load:
            output=Path(tmp)/'fresh'
            with self.assertRaises(ValueError):
                runner.run('capture','payload',output,budget_seconds=60,windows=('carried',))
            load.assert_not_called();self.assertFalse(output.exists())

    def test_cli_default_and_cold_only_keep_distinct_requested_windows(self):
        for flag,windows,status in (([],('cold','carried'),'PASS_COMPLETE_CHAIN_COMPUTED_GATES_ONLY'),(['--cold-only'],('cold',),'PASS_COLD_CHAIN_COMPUTED_GATES_ONLY')):
            with patch.object(runner.sys,'argv',['run_fullblock','--capture','cap','--payload','pay','--out','fresh','--budget-seconds','60',*flag]),patch.object(runner,'run',return_value=dict(status=status,elapsed_seconds=1,terminal_count=19)) as run:
                with self.assertRaises(SystemExit) as result:
                    runner.main()
                self.assertEqual(result.exception.code,0)
                self.assertEqual(run.call_args.kwargs,dict(budget_seconds=60,windows=windows))


class SelectedComparisonTests(unittest.TestCase):
    def compare(self, cases, *, result=True, clock=(1, 2)):
        values = {case['name']: object() for case in cases}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'compare_case', return_value={'all_computed_stages_pass':result}) as compare, patch.object(runner.time, 'monotonic', side_effect=clock):
            actual = runner.compare_selected_windows(cases, {}, 'capture', Path(tmp), values, values, values, started=0, budget_seconds=10)
            return actual, [call.args[0]['name'] for call in compare.call_args_list]

    def test_cold_only_compares_cold_and_does_not_hide_its_failure(self):
        cases=({'name':'cold128'},)
        result,names=self.compare(cases,result=False)
        self.assertEqual(names,['cold128'])
        self.assertFalse(result['cold128']['all_computed_stages_pass'])

    def test_default_comparison_preserves_cold_then_carried_order(self):
        result,names=self.compare(({'name':'cold128'},{'name':'carried128'}),clock=(1,2,3,4))
        self.assertEqual(names,['cold128','carried128'])
        self.assertEqual(list(result),names)

    def test_empty_extra_or_missing_actual_comparison_domains_rejected(self):
        for cases,values in (((),{}),(({'name':'cold128'},),{}),
                            (({'name':'cold128'},),{'cold128':1,'carried128':2})):
            with self.assertRaises(ValueError),patch.object(runner,'compare_case') as compare:
                runner.compare_selected_windows(cases,{},'capture',Path('unused'),values,values,values,started=0,budget_seconds=10)
            compare.assert_not_called()

    def test_comparison_cannot_reset_or_overrun_original_clock(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            self.compare(({'name':'cold128'},),clock=(1,11))
