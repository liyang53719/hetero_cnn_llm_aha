"""Cold diagnostic projection tests; no capture or numerical execution."""
from pathlib import Path
import unittest
from . import failure_diagnostic as D

ROOT = Path('/explicit/reviewed/root')


def caught(source, filename):
    namespace = {}
    try:
        exec(compile(source, filename, 'exec'), namespace)
    except BaseException as error:
        return error
    raise AssertionError('synthetic failure missing')


class DiagnosticTests(unittest.TestCase):
    def test_every_approved_source_is_projected(self):
        for relative,label in D.MODULES.items():
            with self.subTest(module=label):
                error=caught("raise ValueError('secret')",str(ROOT/relative))
                result=D.project(error,'WORKER',ROOT)
                self.assertEqual(result,dict(schema=1,status='CI_REFERENCE_FAILURE',origin='WORKER',
                    error='VALUE_ERROR',module=label,line=1))

    def test_need_and_require_frames_are_skipped(self):
        for helper in ('need','require'):
            source=f"def {helper}():\n    raise ValueError('private')\ndef approved_call():\n    {helper}()\napproved_call()\n"
            error=caught(source,str(ROOT/'candidates/qwen2_fullblock_ci_reference/recipe.py'))
            self.assertEqual(D.project(error,'SUPERVISOR',ROOT)['line'],4)

    def test_external_filename_and_alias_are_other(self):
        for filename in ('/private/secrets.py',str(ROOT)+'/../root/candidates/qwen2_fullblock_ci_reference/recipe.py'):
            result=D.project(caught("raise KeyError('secret')",filename),'WORKER',ROOT)
            self.assertEqual((result['module'],result['line']),('OTHER',0))

    def test_exception_text_and_custom_traceback_lookup_never_used(self):
        class Malicious(ValueError):
            def __str__(self):raise AssertionError('str invoked')
            def __repr__(self):raise AssertionError('repr invoked')
            def __getattribute__(self,name):
                if name in ('args','__traceback__'):raise AssertionError('custom lookup invoked')
                return super().__getattribute__(name)
        result=D.project(Malicious(),'WORKER',ROOT)
        self.assertEqual(result['error'],'VALUE_ERROR')
        self.assertEqual(result['module'],'OTHER')

    def test_unknown_exception_is_other(self):
        self.assertEqual(D.project(BaseException(),'WORKER',ROOT)['error'],'OTHER')

    def test_checked_rejects_unknown_fields_and_wrong_types(self):
        valid=D.project(ValueError(),'WORKER',ROOT)
        invalid=[{**valid,'extra':'secret'},{k:v for k,v in valid.items() if k!='line'}]
        for key,value in [('schema',True),('status',None),('origin',[]),('error',{}),('module',0),
                          ('line',True),('line',-1),('line',100001),('line',1),('origin','OTHER')]:
            invalid.append({**valid,key:value})
        invalid += [{**valid,'module':'CI_RECIPE'}, {**valid,'module':'/secret/path','line':3}]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(ValueError):D.checked(value)
        self.assertEqual(D.checked(valid),valid)
        self.assertIsNot(D.checked(valid),valid)

    def test_root_and_origin_must_be_explicit_canonical_values(self):
        for root in ('relative','/a/../b','/a//b','/',None):
            with self.subTest(root=root),self.assertRaises((ValueError,TypeError)):
                D.project(ValueError(),'WORKER',root)
        with self.assertRaises(ValueError):D.project(ValueError(),'private-origin',ROOT)
        with self.assertRaises(TypeError):D.project('secret','WORKER',ROOT)

if __name__=='__main__':unittest.main()
