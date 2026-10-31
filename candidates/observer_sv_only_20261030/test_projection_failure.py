"""Synthetic controlled-failure diagnostics only; no native hardware execution."""
import ast,copy,json,pathlib,sys,tempfile,unittest,shutil
from unittest.mock import patch
import sv_difference_projection as p
import export_metadata as e
import contract as c
import test_projection as f
import test_export_flow as flow
class FailureTests(unittest.TestCase):
 def test_every_literal_need_has_closed_reason(self):
  t=ast.parse(pathlib.Path(p.__file__).read_text());labels={n.args[1].value for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='need'and len(n.args)>1 and isinstance(n.args[1],ast.Constant)}
  self.assertEqual(labels,set(p.REJECTION_CODES));self.assertEqual(len(set(p.REJECTION_CODES.values())),len(labels))
  for label in labels:
   p.reset_diagnostic()
   try:p.need(False,label)
   except p.ProjectionRejected as ex:
    result=p.failure_record(ex);self.assertEqual(result['reason_code'],p.REJECTION_CODES[label]);self.assertFalse(result['numerical_pass']);self.assertNotIn('exception',result)
 def test_exception_text_never_exported(self):
  for ex in [ValueError('SECRET_/path'),OSError('SECRET_/path'),KeyError('SECRET_/path'),TypeError('SECRET_/path'),ImportError('SECRET_/path'),MemoryError('SECRET_/path')]:
   p.reset_diagnostic();r=p.failure_record(ex);self.assertNotIn('SECRET',json.dumps(r));self.assertIsNone(r['module']);self.assertIsNone(r['kind']);self.assertTrue(all(x is None for x in r['progress'].values()))
 def test_actual_rejection_has_safe_progress(self):
  name=p.MODULES[0];data=f.fixture(name).replace(b'input [31:0] io_tiles_response_bits_key_identity',b'input [30:0] io_tiles_response_bits_key_identity');p.reset_diagnostic()
  try:p.projected_hash(data,name,True)
  except p.ProjectionRejected as ex:r=p.failure_record(ex)
  self.assertEqual(r['phase'],'PROJECT_MODULE');self.assertEqual(r['module'],name);self.assertEqual(r['kind'],'new');self.assertEqual(r['reason_code'],p.REJECTION_CODES['exact key port direction/width']);self.assertEqual(r['progress']['normalized_module_bytes'],len(data));self.assertEqual(r['progress']['removed_ports'],0)
 def test_failure_projector_rejects_extra_or_unsafe_fields(self):
  p.reset_diagnostic();r=p.failure_record(ValueError('x'))
  changes=[('reason_code','arbitrary secret'),('module','secret'),('kind','third'),('phase','private'),('numerical_pass',True),('projection_source_sha256','0'*64),('remaining_bytes_compared',True),('secret','payload')]
  for k,v in changes:
   bad=copy.deepcopy(r);bad[k]=v
   with self.assertRaises(ValueError):p.project_failure(bad)
  for k,v in [('removed_ports',True),('removed_assignments',17),('normalized_module_bytes',-1),('projected_normalized_sha256','private')]:
   bad=copy.deepcopy(r);bad['progress'][k]=v
   with self.assertRaises(ValueError):p.project_failure(bad)
 def test_cli_native1_writes_bounded_record_no_exception_text(self):
  with tempfile.TemporaryDirectory()as td:
   out=pathlib.Path(td)/'proof.json';argv=['projection','--old-sv','missing','--new-sv','missing','--old-metadata','missing','--new-metadata','missing','--materialization','missing','--output',str(out)]
   with patch.object(sys,'argv',argv),patch.object(p,'prove',side_effect=ValueError('SECRET_/path')):self.assertEqual(p.main(),1)
   r=json.loads(out.read_text());self.assertEqual(r['reason_code'],'UNCLASSIFIED_VALUE_ERROR');self.assertLessEqual(out.stat().st_size,65536);self.assertNotIn('SECRET',out.read_text())

 def test_comparison_retains_actual_unequal_hashes_and_counts(self):
  name=p.MODULES[0];p.reset_diagnostic()
  old=p.projected_hash(f.fixture(name,False),name,False)
  new=p.projected_hash(f.fixture(name,True,change='wire added_nonprojected_logic;'),name,True)
  p.diagnostic_context('COMPARE_MODULE',name);p.diagnostic_comparison({'old':old,'new':new})
  try:p.need(old['projected_normalized_sha256']==new['projected_normalized_sha256'],'nonprojected normalized SV byte difference: reject')
  except p.ProjectionRejected as ex:r=p.failure_record(ex)
  self.assertFalse(r['comparison']['projected_sha256_equal']);self.assertFalse(r['comparison']['projected_bytes_equal']);self.assertEqual(r['comparison']['old']['removed_ports'],0);self.assertEqual(r['comparison']['new']['removed_ports'],8)
  bad=copy.deepcopy(r);bad['comparison']['projected_sha256_equal']=True
  with self.assertRaises(ValueError):p.project_failure(bad)
 def test_unknown_byte_and_deleted_port_line_locations(self):
  name=p.MODULES[0];data=f.fixture(name).replace(b'input clock',b'input clock\x01');p.reset_diagnostic()
  try:p.projected_hash(data,name,True)
  except p.ProjectionRejected as ex:r=p.failure_record(ex)
  self.assertEqual(r['progress']['lexical_byte_offset'],data.index(b'\x01'));self.assertIsNone(r['progress']['line_number'])
  data=f.fixture(name).replace(b'input [31:0] io_tiles_response_bits_key_identity',b'input [30:0] io_tiles_response_bits_key_identity');p.reset_diagnostic()
  try:p.projected_hash(data,name,True)
  except p.ProjectionRejected as ex:r=p.failure_record(ex)
  self.assertEqual(r['progress']['line_number'],4);self.assertEqual(r['progress']['lexical_byte_offset'],data.index(b'input [30:0]'))
 def test_partial_completed_old_row_survives_new_side_failure_context(self):
  name=p.MODULES[0];p.reset_diagnostic();old=p.projected_hash(f.fixture(name,False),name,False);p.diagnostic_comparison({'old':old});p.diagnostic_context('NORMALIZE_MODULE',name,'new');r=p.failure_record(ValueError('private'))
  self.assertIsNotNone(r['comparison']['old']);self.assertIsNone(r['comparison']['new']);self.assertIsNone(r['comparison']['projected_sha256_equal']);p.diagnostic_context('NORMALIZE_MODULE',p.MODULES[1],'old');self.assertIsNone(p.DIAGNOSTIC['comparison']['old'])
 def test_first_line_overflow_and_saturated_diagnostics_keep_reason(self):
  p.reset_diagnostic();p.diagnostic_context('PROJECT_MODULE',p.MODULES[0],'old');p.diagnostic_progress(line_number=1500001)
  try:p.need(False,'module line-object memory bound')
  except p.ProjectionRejected as ex:r=p.failure_record(ex)
  self.assertEqual(r['progress']['line_number'],1500001);self.assertEqual(r['saturated_fields'],[])
  p.diagnostic_progress(line_number=1500002,lexical_byte_offset=96*1024**2+1,normalized_module_bytes=512*1024**2+1);r=p.failure_record(p.ProjectionRejected(p.REJECTION_CODES['module line-object memory bound']))
  self.assertEqual(r['saturated_fields'],['lexical_byte_offset','line_number','normalized_module_bytes']);self.assertTrue(all(r['progress'][k]is None for k in r['saturated_fields']));self.assertEqual(r['reason_code'],p.REJECTION_CODES['module line-object memory bound'])
 def test_normalization_mismatch_is_explicit_not_discarded(self):
  p.reset_diagnostic();p.diagnostic_context('NORMALIZE_MODULE',p.MODULES[0],'new');p.diagnostic_progress(normalized_module_sha256='0'*64,normalized_module_bytes=19)
  r=p.failure_record(p.ProjectionRejected(p.REJECTION_CODES['same actual module fingerprint']))
  self.assertFalse(r['normalized_module_matches_expected']);self.assertEqual(r['progress']['normalized_module_sha256'],'0'*64)
  bad=copy.deepcopy(r);bad['normalized_module_matches_expected']=True
  with self.assertRaises(ValueError):p.project_failure(bad)

def failure_fixture(d):
 work,canonical=flow.setup_fixture(d);(work/'COMPLETE.json').unlink();repo=d
 mat=repo/'candidates/ci_frontend_materialization_r2_20261029';pipe=repo/'candidates/ci_frontend_pipeline_r2_20261029';mat.mkdir(parents=True);pipe.mkdir(parents=True)
 original=pathlib.Path(e.__file__).resolve().parents[1]
 for src,dst in [(original/'ci_frontend_materialization_r2_20261029/sv_comment_only_identity.py',mat/'sv_comment_only_identity.py'),(original/'ci_frontend_pipeline_r2_20261029/frontend_observation_metadata.py',pipe/'frontend_observation_metadata.py')]:shutil.copyfile(src,dst)
 pins={str((c.D/'sv_difference_projection.py').resolve()):c.sha(c.D/'sv_difference_projection.py'),str((pipe/'frontend_observation_metadata.py').resolve()):p.COLLECTOR_SHA}
 identities={};svs={};metadata={}
 for side in ('old','new'):
  sv=work/(side+'_emit_sv')/'compiled-host/HostBlockTopV4.sv';svs[side]=sv;meta=work/(side+'_svscan')/'sv-identity.json';metadata[side]=meta
  rows=[dict(module=name,normalized_sha256=p.MOD_NORMALIZED[side][name])for name in p.MODULES]+[dict(module='fixture'+str(i),normalized_sha256='1'*64)for i in range(90)]
  doc=dict(schema='OBSERVED_FRONTEND_SV_V1',status='OBSERVED_UNREVIEWED_NOT_ACCEPTED',numerical_pass=False,scanner_sha256=p.SCANNER,normalized_sha256=p.FULL[side],raw_sha256=c.sha(sv),bytes=sv.stat().st_size,modules=rows);meta.write_text(json.dumps(doc))
  receipt=meta.parent/'RESULT.json';r=json.loads(receipt.read_text());r['argv']=[sys.executable,'-B',str(pipe/'frontend_observation_metadata.py'),'--observe-sv',str(sv),'--materialization',str(mat),'--output',meta.name];receipt.write_text(json.dumps(r))
  identities[side]=dict(bytes=sv.stat().st_size,raw_sha256=c.sha(sv),normalized_sha256=p.FULL[side],metadata_sha256=c.sha(meta),scan_receipt_sha256=c.sha(receipt))
 receipt=work/'projection/RESULT.json';r=json.loads(receipt.read_text());r.update(native_exit=1,argv=[sys.executable,'-B',str(c.D/'sv_difference_projection.py'),'--old-sv',str(svs['old']),'--new-sv',str(svs['new']),'--old-metadata',str(metadata['old']),'--new-metadata',str(metadata['new']),'--materialization',str(mat),'--output','proof.json']);receipt.write_text(json.dumps(r))
 p.reset_diagnostic();p.diagnostic_context('PROJECT_MODULE',p.MODULES[0],'new');p.DIAGNOSTIC['full_sv']=identities
 proof=p.failure_record(p.ProjectionRejected(p.REJECTION_CODES['exact complete added key ports']));(work/'projection/proof.json').write_text(json.dumps(proof))
 saved=[]
 for n,_,_ in c.STAGES:
  row=e.stage_row(n,work/n/'RESULT.json',n!='projection');saved.append({k:row[k]for k in ('name','native_exit','elapsed_seconds','observed_peak_rss','strict_complete','error_count','result_sha256')})
 (work/'STAGES.json').write_text(json.dumps(saved));return work,canonical,pins
class FailureExportTests(unittest.TestCase):
 def execute(self,d,w,canonical,pins):
  actual=e.sha
  args=['export','--repo',str(d),'--work',str(w),'--identity',str(d/'identity.json'),'--job-start',str(d/'clock.json'),'--output',str(d/'output')]
  with patch.object(e,'closure',return_value=pins),patch.object(e,'sha',side_effect=lambda path:canonical.get(str(path),actual(path))),patch.object(sys,'argv',args):e.main()
  return json.loads((d/'output/sv-only-summary.json').read_text()),json.loads((d/'output/sv-only-proof.json').read_text())
 def test_bound_native1_exports_failure_not_pass(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can,pins=failure_fixture(d);s,r=self.execute(d,w,can,pins);self.assertEqual(s['status'],'TWO_MODULE_PROJECTION_FAILED_BOUND_DIAGNOSTIC');self.assertEqual(r['schema'],'EXACT_TWO_MODULE_KEY_PROJECTION_FAILED_V1');self.assertFalse(s['numerical_pass']);self.assertFalse(s['stages'][-1]['strict_complete']);self.assertEqual(s['stages'][-1]['native_exit'],1)
 def test_missing_failure_proof_unavailable(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can,pins=failure_fixture(d);(w/'projection/proof.json').unlink();s,r=self.execute(d,w,can,pins);self.assertEqual(r['schema'],'SV_ONLY_PROOF_UNAVAILABLE_V1')
 def test_unbound_receipts_inputs_and_cleanup_fail_closed(self):
  for change in ('cleanup','native','prior','argv','source','input','collector','failurehash'):
   with self.subTest(change=change),tempfile.TemporaryDirectory()as td:
    d=pathlib.Path(td);w,can,pins=failure_fixture(d)
    if change=='source':pins[str((c.D/'sv_difference_projection.py').resolve())]='0'*64
    elif change=='input':(w/'old_emit_sv/compiled-host/HostBlockTopV4.sv').write_bytes(b'MUTATED')
    elif change=='failurehash':
     q=w/'projection/proof.json';r=json.loads(q.read_text());r['full_sv']['old']['metadata_sha256']='0'*64;q.write_text(json.dumps(r))
    else:
     q=w/('old_svscan'if change in ('prior','collector')else'projection')/'RESULT.json';r=json.loads(q.read_text())
     if change=='cleanup':r['log_capture']['pipe_eof_observed']=False
     elif change in ('native','prior'):r['native_exit']=2
     else:r['argv'][2]='/not-reviewed.py'
     q.write_text(json.dumps(r))
    s,r=self.execute(d,w,can,pins);self.assertEqual(r['schema'],'SV_ONLY_PROOF_UNAVAILABLE_V1');self.assertFalse(s['numerical_pass'])
 def test_early_child_unknown_inputs_preserved_external_binding_separate(self):
  for code in ('MISSING_FIELD',p.REJECTION_CODES['original exact scanner source']):
   with self.subTest(code=code),tempfile.TemporaryDirectory()as td:
    d=pathlib.Path(td);w,can,pins=failure_fixture(d);p.reset_diagnostic();p.diagnostic_context('INPUT_BINDING',kind='old');r=p.failure_record(p.ProjectionRejected(code));(w/'projection/proof.json').write_text(json.dumps(r))
    s,r=self.execute(d,w,can,pins);self.assertEqual(s['status'],'TWO_MODULE_PROJECTION_FAILED_BOUND_DIAGNOSTIC');self.assertEqual(r['full_sv'],{'old':None,'new':None});self.assertEqual(s['exporter_bound_inputs']['scope'],'EXPORTER_REVERIFIED_INPUTS_NOT_CHILD_OBSERVATIONS');self.assertEqual(set(s['exporter_bound_inputs']['inputs']),{'old','new'})
 def test_actual_mismatch_progress_exported_not_changed_to_expected(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can,pins=failure_fixture(d);full=json.loads((w/'projection/proof.json').read_text())['full_sv'];p.reset_diagnostic();p.diagnostic_context('NORMALIZE_MODULE',p.MODULES[0],'new');p.DIAGNOSTIC['full_sv']=full;p.diagnostic_progress(normalized_module_sha256='0'*64,normalized_module_bytes=19);r=p.failure_record(p.ProjectionRejected(p.REJECTION_CODES['same actual module fingerprint']));(w/'projection/proof.json').write_text(json.dumps(r));s,r=self.execute(d,w,can,pins)
   self.assertEqual(s['status'],'TWO_MODULE_PROJECTION_FAILED_BOUND_DIAGNOSTIC');self.assertFalse(r['normalized_module_matches_expected']);self.assertEqual(r['progress']['normalized_module_sha256'],'0'*64)
if __name__=='__main__':unittest.main()
