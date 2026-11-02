import unittest,hashlib,re
from pathlib import Path
D=Path(__file__).resolve().parent
class Delta(unittest.TestCase):
    def test_exact_original_body_inverse(self):
        s=(D/'Public21DownOwnerEmitOnly.scala').read_text();self.assertEqual(hashlib.sha256(s.encode()).hexdigest(),'efaa8e39cfcfb6abf9ca27568d2f2fe365d9de17dd62491c9ecc802ef63691f1');self.assertEqual(s.count('    } catch {'),1)
        prefix=s.split('    } catch {')[0]
        fixed=['    var phase="ENTRY"\n','    try {\n']+[f'    phase="{p}"\n' for p in ('VALIDATE_OUTPUT','ELABORATE','LOWER','TOP_INFO','HARNESS','SV','COMPLETE')]
        for line in fixed:self.assertEqual(prefix.count(line),1);prefix=prefix.replace(line,'')
        lines=prefix.splitlines(keepends=True)
        additions=[l for l in lines if 'println(' in l and any(x in l for x in ('B_EMIT_ONLY_AFTER_ELAB','B_EMIT_ONLY_AFTER_LOW','B_EMIT_ONLY_AFTER_INFO'))]
        self.assertEqual(len(additions),3)
        for line in additions:prefix=prefix.replace(line,'')
        relative_lines=['    val relativeTarget=out.relativeTo(os.pwd).toString\n','    require((os.pwd/os.RelPath(relativeTarget))==out,"relative target must resolve to original output")\n']
        for line in relative_lines:self.assertEqual(prefix.count(line),1);prefix=prefix.replace(line,'')
        self.assertEqual(prefix.count('TargetDirAnnotation(relativeTarget)'),1)
        prefix=prefix.replace('TargetDirAnnotation(relativeTarget)','TargetDirAnnotation(out.toString)')
        restored=prefix+'  }\n}\n' 
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'9ab18d22131bf40b156d77b3c4173652cb3386ec3db26afac670d175f8d47ade')
    def test_same_narrow_relative_target_in_both_entries(self):
        for name in ('Public21DownOwnerEmitOnly.scala','Public21EmitApiProbe.scala'):
            s=(D/name).read_text()
            self.assertEqual(s.count('val relativeTarget=out.relativeTo(os.pwd).toString'),1)
            self.assertEqual(s.count('require((os.pwd/os.RelPath(relativeTarget))==out,'),1)
            self.assertEqual(s.count('TargetDirAnnotation(relativeTarget)'),1)
            self.assertNotIn('TargetDirAnnotation(out.toString)',s)
            self.assertNotIn('chdir',s)
    def test_fixed_failure_domain(self):
        s=(D/'Public21DownOwnerEmitOnly.scala').read_text();helper=s.split('object BEmitPhaseDiagnostics {')[1]
        for bad in ('getMessage','toString','getClass','getCause'):self.assertNotIn(bad,helper)
        self.assertIn('.take(8)',helper);self.assertIn('f.getLineNumber>0',helper);self.assertIn('sources.contains(f.getFileName)',helper)
        self.assertEqual(re.findall(r'=>"([A-Z_]+)"',helper),['ILLEGAL_ARGUMENT','ASSERTION_ERROR','OUT_OF_MEMORY','LINKAGE_ERROR','OTHER'])
        self.assertIn('        throw error',s)
    def test_probe_real_api_no_backend(self):
        s=(D/'Public21EmitApiProbe.scala').read_text()
        for op in ('Compiler.elaborate(', 'Compiler.toLowFirrtl(', 'TopmoduleInfo(', 'VerilatorCppJNAHarnessGenerator.codeGen(', 'Compiler.lowFirrtlToSystemVerilog('):self.assertEqual(s.count(op),1)
        self.assertIn('BoringUtils.addSource(child.observedRegister',s);self.assertIn('BoringUtils.addSink(sink',s)
        for bad in ('runVerilator(', 'createContext(', 'compileAndLoadJNAClass(', 'TransposedDenseDownOwner', 'MatrixPipeline'):self.assertNotIn(bad,s)
if __name__=='__main__':unittest.main()
