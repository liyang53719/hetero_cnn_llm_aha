"""Admission/geometry tests; no full reference or native execution."""
import copy
import unittest
from unittest import mock
from . import workload as w
from . import completed as c
from . import builder as b

class WorkloadTests(unittest.TestCase):
    def test_only_integer_cold_m16_m128_are_admitted(self):
        for rows in (16,128):self.assertEqual(w.cold_rows(rows),rows)
        for rows in (True,False,16.0,128.0,'16','128',1,32,0,-16):
            with self.assertRaises(ValueError):w.cold_rows(rows)
        for past in (16,128,1,-1,0.0,False):
            with self.assertRaises(ValueError):w.cold_rows(128,past)

    def test_complete_output_geometry(self):
        for rows,total in ((16,3309568),(128,29229056)):
            sizes=w.output_inventory(rows);shapes=w.output_shapes(rows)
            self.assertEqual(len(sizes),22);self.assertEqual(sum(sizes.values()),total)
            self.assertEqual(shapes['phase_4_q_recipe.f32le'],(1,rows,1536))
            self.assertEqual(shapes['scores.f32le'],(1,12,rows,rows))
            self.assertEqual(shapes['cache_k.f32le'],(1,rows,2,128))
            self.assertEqual(sizes['silu.f32le'],rows*8960*4)
        # Q and scores happen to have equal byte counts at M128; their shapes
        # and named files remain distinct. Equal size never selects a layout.
        self.assertEqual(w.output_inventory(128)['phase_4_q_recipe.f32le'],w.output_inventory(128)['scores.f32le'])
        self.assertNotEqual(w.output_shapes(128)['phase_4_q_recipe.f32le'],w.output_shapes(128)['scores.f32le'])

    def test_inventory_rejects_missing_extra_and_cross_shape(self):
        good={name:dict(bytes=size,sha256='0'*64) for name,size in w.output_inventory(128).items()}
        self.assertEqual(w.validate_sealed_inventory(128,good),w.output_inventory(128))
        wrongs=[]
        missing=copy.deepcopy(good);missing.pop('cache_k.f32le');wrongs.append(missing)
        extra=copy.deepcopy(good);extra['unexpected.f32le']=dict(bytes=4);wrongs.append(extra)
        wrong_size=copy.deepcopy(good);wrong_size['scores.f32le']['bytes']=12*16*16*4;wrongs.append(wrong_size)
        wrongs.append({n:dict(bytes=s) for n,s in w.output_inventory(16).items()})
        for wrong in wrongs:
            with self.assertRaises(ValueError):w.validate_sealed_inventory(128,wrong)

    def inputs(self,rows):
        p=w.INPUT_PINS[rows]
        cold=dict(tokens=rows,past_tokens=0,inputs=dict(past_tokens=0,token_ids=list(range(rows)),
            position_ids=list(range(rows)),intermediate_preloads=0,readonly_sha256=p['readonly_sha256'],input_x_sha256=p['input_x_sha256']))
        readonly=dict(bytes=188043264,intermediate_preloads=0,sha256=p['readonly_sha256'],input_x_sha256=p['input_x_sha256'])
        return cold,readonly

    def test_input_identity_and_no_previous_window(self):
        for rows in (16,128):
            cold,readonly=self.inputs(rows)
            self.assertEqual(w.validate_input_metadata(rows,cold,readonly),w.INPUT_PINS[rows])
        cold,readonly=self.inputs(128)
        wrong=copy.deepcopy(readonly);wrong['input_x_sha256']=w.INPUT_PINS[16]['input_x_sha256']
        with self.assertRaises(ValueError):w.validate_input_metadata(128,cold,wrong)
        for key,value in [('position_ids',list(range(128,256))),('token_ids',list(range(16,144))),('intermediate_preloads',1)]:
            wrong=copy.deepcopy(cold);wrong['inputs'][key]=value
            with self.assertRaises(ValueError):w.validate_input_metadata(128,wrong,readonly)

    def receipts(self,rows):
        result=dict(rows=rows,frozen_sha256='f'*64);prepared=dict(rows=rows,past_tokens=0)
        frozen=dict(rows=rows,past_tokens=0,run_command=['candidate','arena',str(rows),'out','0','empty','empty'],
                    compile_wall_budget_seconds=10,run_wall_budget_seconds=w.RUN_WALL_SECONDS[rows])
        return result,prepared,frozen

    def test_receipt_rows_commands_and_budgets_are_bound(self):
        for rows in (16,128):self.assertEqual(c.receipt_rows(*self.receipts(rows)),rows)
        result,prepared,frozen=self.receipts(128)
        for target,key,value in [('result','rows',16),('prepared','rows',16),('prepared','past_tokens',128),
                                 ('frozen','rows',16),('frozen','run_wall_budget_seconds',90)]:
            values=dict(result=copy.deepcopy(result),prepared=copy.deepcopy(prepared),frozen=copy.deepcopy(frozen))
            values[target][key]=value
            with self.assertRaises(ValueError):c.receipt_rows(**values)
        bad=copy.deepcopy(frozen);bad['run_command'][2]='16'
        with self.assertRaises(ValueError):c.receipt_rows(result,prepared,bad)

    def test_only_exact_historical_m16_can_omit_frozen_rows(self):
        result,prepared,frozen=self.receipts(16);frozen.pop('rows');frozen.pop('past_tokens')
        result['frozen_sha256']=c.EXECUTED_FROZEN_SHA
        self.assertEqual(c.receipt_rows(result,prepared,frozen),16)
        result['frozen_sha256']='f'*64
        with self.assertRaises(ValueError):c.receipt_rows(result,prepared,frozen)
        result,prepared,frozen=self.receipts(128);frozen.pop('rows');result['frozen_sha256']=c.EXECUTED_FROZEN_SHA
        with self.assertRaises(ValueError):c.receipt_rows(result,prepared,frozen)

    def test_actual_summary_snapshot_binding_and_input_metadata(self):
        pin=w.INPUT_PINS[128];policy={'unchanged_gate':True}
        source=dict(summary_path='summary',snapshot_path='snapshot',summary_sha256=pin['summary_sha256'],snapshot_sha256=pin['snapshot_sha256'])
        summary=dict(rows=128,snapshot_sha256=pin['snapshot_sha256'],loaded_inputs={'x':dict(bytes=128*1536*4,sha256=pin['input_x_sha256'])},prelaunch_intermediate_payloads=[])
        snapshot=dict(rows=128,loaded_inputs=copy.deepcopy(summary['loaded_inputs']),prelaunch_intermediate_payloads=[],reference=dict(threshold_policy=policy))
        with mock.patch.object(b,'frozen_json',side_effect=[summary,snapshot]) as read:
            b.verify_actual_source(128,source,policy)
            self.assertEqual(read.call_args_list,[mock.call('summary',pin['summary_sha256']),mock.call('snapshot',pin['snapshot_sha256'])])
        bad_summary=copy.deepcopy(summary);bad_summary['snapshot_sha256']=w.INPUT_PINS[16]['snapshot_sha256']
        with mock.patch.object(b,'frozen_json',return_value=bad_summary) as read:
            with self.assertRaisesRegex(ValueError,'summary/snapshot'):b.verify_actual_source(128,source,policy)
            self.assertEqual(read.call_count,1) # reject binding before parsing snapshot
        for wrong in ('rows','bytes','sha256','preload'):
            bad=copy.deepcopy(snapshot)
            if wrong=='rows':bad['rows']=16
            elif wrong=='preload':bad['prelaunch_intermediate_payloads']=['n0']
            else:bad['loaded_inputs']['x'][wrong]=16*1536*4 if wrong=='bytes' else w.INPUT_PINS[16]['input_x_sha256']
            with mock.patch.object(b,'frozen_json',side_effect=[summary,bad]):
                with self.assertRaises(ValueError):b.verify_actual_source(128,source,policy)
        for key in ('summary_sha256','snapshot_sha256'):
            bad=copy.deepcopy(source);bad[key]='0'*64
            with mock.patch.object(b,'frozen_json') as read:
                with self.assertRaises(ValueError):b.verify_actual_source(128,bad,policy)
                read.assert_not_called()

if __name__=='__main__':unittest.main()
