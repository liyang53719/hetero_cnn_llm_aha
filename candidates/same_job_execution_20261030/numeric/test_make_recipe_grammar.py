"""Synthetic grammar and actual retained build metadata; no Make/compiler/ELF execution."""
import pathlib,json,unittest,importlib.util,copy,hashlib
import driver_dependency_proof as d
P=pathlib.Path;ROOT=P(__file__).resolve().parent.parent
class Grammar(unittest.TestCase):
 def setUp(self):
  self.driver='/reviewed/driver.cpp';self.line='\t$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<'
 def host(self,line=None):return 'driver.o: '+self.driver+' \n'+(line if line is not None else self.line)+'\n\n# original comment\nnext: input\n\tother-command\n'
 def test_actual_double_space_and_equivalent_separator(self):
  for line in (self.line,self.line.replace('  -c',' -c'),self.line.replace('  -c','\t-c'),self.line+' \t'):
   self.assertEqual(d.verify_driver_compile_recipe(self.host(line),'driver',self.driver)['tokens'],list(d.COMPILE_RECIPE_TOKENS))
 def test_extra_shell_or_flags(self):
  for tail in ('; echo bad',' && true',' | cat',' # comment',' -O3',' $(EXTRA)','\\','\v'):
   with self.subTest(tail=tail),self.assertRaises(ValueError):d.verify_driver_compile_recipe(self.host(self.line+tail),'driver',self.driver)
 def test_token_change(self):
  for old,new in (('$(CXX)','$(CC)'),('-c','-E'),('$<','$^'),('$(OPT_FAST)','$(OPT_SLOW)')):
   with self.assertRaises(ValueError):d.verify_driver_compile_recipe(self.host(self.line.replace(old,new)),'driver',self.driver)
 def test_non_ascii_or_cr(self):
  for text in (self.host().replace('  -c','\u00a0-c'),self.host().replace('\n','\r\n')):
   with self.assertRaises(ValueError):d.verify_driver_compile_recipe(text,'driver',self.driver)
 def test_wrong_target_or_extra_dependency(self):
  for text in (self.host().replace('/reviewed/driver.cpp','/other/driver.cpp'),self.host().replace('driver.cpp \n','driver.cpp extra.h\n')):
   with self.assertRaises(ValueError):d.verify_driver_compile_recipe(text,'driver',self.driver)
 def test_duplicate_and_second_recipe(self):
  for text in (self.host()+self.host(),self.host().replace('\n\n#','\n\tsecond\n\n#'),self.host().replace('# original comment','# original comment\n\tsecond')):
   with self.assertRaises(ValueError):d.verify_driver_compile_recipe(text,'driver',self.driver)
 def test_no_tab_prefix(self):
  with self.assertRaises(ValueError):d.verify_driver_compile_recipe(self.host(self.line.replace('\t',' ',1)),'driver',self.driver)
 def test_producer_old_verifier_separate(self):
  p=P(__file__).resolve().parents[2]/'ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py'

  self.assertEqual(d.sha(p),d.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA);self.assertNotEqual(d.sha(d.__file__),d.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA)
  self.assertEqual(d.PRODUCER_DEPENDENCY_CAPTURE_SHA,"80186b8c5727eeb9054b9e5b284fb27ba6baa7388f491d4ba996409086daa5f4")
if __name__=='__main__':unittest.main()
