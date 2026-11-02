"""Pure host synthetic IEEE words, never Verilator/RTL/model. Baseline print comparison."""
import hashlib,json,pathlib,resource,shutil,subprocess,tempfile,unittest
P=pathlib.Path;HERE=P(__file__).resolve().parent
SOURCE=HERE/'source'if (HERE/'source/readonly_first_fault.hpp').exists()else HERE
RECORD=SOURCE/'TERMINAL_FINITE_RECORD_SCHEMA.json'if (SOURCE/'TERMINAL_FINITE_RECORD_SCHEMA.json').exists()else SOURCE.parents[2]/'candidates/model_candidate_build_20261101/TERMINAL_FINITE_RECORD_SCHEMA.json'
LEGACY_HEADER='#pragma once\n#include "readonly_first_fault_access.hpp"\n#include <cstdint>\n#include <cstdio>\n\n// Host-only diagnostic: no model writes, eval, clock step, or exception handling.\n// The separately validated generated accessor reads exactly the fixed schema.\nnamespace readonly_first_fault {\nstatic_assert(readonly_first_fault_access::field_count == 114, "fixed probe cardinality");\nstruct Sample {\n    std::uint64_t cycle=0, active_cycle=0, completions=0;\n    readonly_first_fault_access::Values values{};\n};\nclass Collector {\n    Sample previous{};\n    bool previous_valid=false, emitted=false;\n    static void print_sample(const char* slot, bool valid, const Sample& s) noexcept {\n        std::printf("HOST_FIRST_FAULT_SLOT_V1 slot=%s valid=%u cycle=%llu active_cycle=%llu completions=%llu values=", slot, unsigned(valid),\n                    static_cast<unsigned long long>(s.cycle), static_cast<unsigned long long>(s.active_cycle), static_cast<unsigned long long>(s.completions));\n        for (std::size_t i=0; i<s.values.size(); ++i)\n            std::printf(i ? ",%llu" : "%llu", static_cast<unsigned long long>(s.values[i]));\n        std::printf("\\n");\n    }\npublic:\n    void observe(const VHostBlockTopV4& top, std::uint64_t cycle,\n                 std::uint64_t active_cycle, std::uint64_t completions,\n                 bool reset_required) noexcept {\n        const Sample current{cycle, active_cycle, completions,\n                             readonly_first_fault_access::capture(top)};\n        if (reset_required) {\n            if (!emitted) {\n                emitted=true;\n                std::printf("HOST_FIRST_FAULT_V1 schema_sha256=%s fields=114 extra_eval=0 extra_clock=0\\n", readonly_first_fault_access::schema_sha256);\n                print_sample("previous_healthy", previous_valid, previous);\n                print_sample("current_fault", true, current);\n                std::fflush(stdout);\n            }\n        } else {\n            previous=current;\n            previous_valid=true;\n        }\n    }\n};\n}\n'
LEGACY_SHA='16c9a400a1e74dae2135c8ac6b6e40fa98e7b349d2777956279734c0f87cb818'
NEW_BLOCK_SHA='95e9b1b738e530af5b6db8122237f7c4326bc023b0d226efa79f7da4ebb97beb'
ACCESS=r'''#pragma once
#include <array>
#include <cstdint>
struct VHostBlockTopV4 {std::uint64_t io_pc=1; std::array<std::uint64_t,114> control{}; std::array<std::uint32_t,4096> payload{};};
inline std::uint64_t control_reads=0,word_reads=0;
namespace readonly_first_fault_access {constexpr std::size_t field_count=114; using Values=std::array<std::uint64_t,114>; constexpr const char* schema_sha256="75088081cf6c3425eba9af3b44c78244f8c62697b4390f992ad63e21f16c7de4"; inline Values capture(const VHostBlockTopV4& t)noexcept{++control_reads;return t.control;}}
'''
WORDS=r'''#pragma once
namespace readonly_terminal_finite_access {constexpr std::size_t word_count=4096;constexpr const char* schema_sha256="SYNTHETIC_ACCESSOR_NOT_ACTUAL_ROOT_DECLARATIONS"; inline std::uint32_t word(const VHostBlockTopV4& t,std::size_t i)noexcept{++word_reads;return t.payload[i];}}
'''
MAIN=r'''#include "subject.hpp"
#include <cstring>
#include <limits>
int main(int argc,char**argv){const char* which=argv[1];
#ifndef BASELINE
 if(!std::strcmp(which,"max")){readonly_first_fault::TerminalSummary s;s.valid=true;
 MAX_ASSIGN
 s.mapping=2;s.first_kind=3;s.first_region=3;readonly_first_fault::print_terminal_summary(s,UINT64_MAX,UINT64_MAX);return 0;}
#endif
 VHostBlockTopV4 t;t.control[103]=160;t.control[107]=0;t.control[108]=1;t.control[109]=1;t.control[110]=0;t.control[111]=1;
 readonly_first_fault::Collector c;std::uint64_t completions=1;
 if(!std::strcmp(which,"mixed")){t.payload[0]=0x7fc00001;t.payload[128]=0x7f800000;t.payload[2048]=0xffc00001;t.payload[4095]=0xff800000;}
 if(!std::strcmp(which,"finite_extremes")){t.payload[0]=0x7f7fffff;t.payload[1]=0xff7fffff;t.payload[2]=0x00800000;t.payload[3]=0x00000001;t.payload[4]=0x80000000;t.payload[5]=0x3f800000;}
 if(!std::strcmp(which,"upper"))t.payload[128]=0x7f800001;
 if(!std::strcmp(which,"no_pc"))t.io_pc=0;
 if(!std::strcmp(which,"no_completion"))completions=0;
 if(!std::strcmp(which,"no_status"))t.control[107]=1;
 if(!std::strcmp(which,"no_ready"))t.control[108]=0;
 if(!std::strcmp(which,"no_valid"))t.control[109]=0;
 if(!std::strcmp(which,"unsupported")){t.control[103]=1;t.payload[17]=0x7f800000;}
 if(!std::strcmp(which,"last_window")){t.control[103]=1440;t.control[110]=2;t.payload[4095]=0xff800000;}
 if(!std::strcmp(which,"bad_context")){t.control[103]=1440;t.control[110]=3;t.payload[4095]=0xff800000;}
 if(!std::strcmp(which,"error_last")){t.control[111]=0;t.control[112]=1;t.payload[7]=0x7fc00001;}
 if(std::strcmp(which,"empty"))c.observe(t,11,7,completions,false);
 if(!std::strcmp(which,"later_fault"))t.io_pc=2;
 t.payload.fill(0x7f800000);t.control[110]=1;t.control[107]=1;
 c.observe(t,12,8,completions,true);c.observe(t,13,9,completions,true);
 std::printf("HOST_TEST_COUNTS control=%llu words=%llu\n",(unsigned long long)control_reads,(unsigned long long)word_reads);
}
'''
def caps():
 resource.setrlimit(resource.RLIMIT_AS,(512<<20,512<<20));resource.setrlimit(resource.RLIMIT_CPU,(15,15))
class Host(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=P(cls.tmp.name);fields='cycle active_cycle pc completions ng context result_last result_error words finite nan positive_infinity negative_infinity effective_words padding_words unknown_region_words nonfinite_effective nonfinite_padding nonfinite_unknown_region first_nonfinite_index'.split();main=MAIN.replace('MAX_ASSIGN',''.join('s.'+k+'=UINT64_MAX;'for k in fields))
  for name,header in [('new',(SOURCE/'readonly_first_fault.hpp').read_bytes()),('old',LEGACY_HEADER.encode())]:
   r=cls.root/name;r.mkdir();(r/'subject.hpp').write_bytes(header);(r/'readonly_first_fault_access.hpp').write_text(ACCESS);(r/'readonly_terminal_finite_access.hpp').write_text(WORDS);(r/'main.cpp').write_text(main)
   cmd=['g++','-std=c++17','-O0','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(r/'main.cpp'),'-o',str(r/'test')]+(['-DBASELINE']if name=='old'else[])
   subprocess.run(cmd,check=True,capture_output=True,timeout=20,preexec_fn=caps)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,which,baseline=False):return subprocess.check_output([str(self.root/('old'if baseline else'new')/'test'),which],timeout=5,preexec_fn=caps).decode()
 def summary(self,which):
  out=self.run_case(which);lines=[x for x in out.splitlines()if x.startswith('HOST_TERMINAL_FINITE_SUMMARY_V1 ')];self.assertEqual(len(lines),1);self.assertLess(len(lines[0])+1,1024);return dict(v.split('=',1)for v in lines[0].split()[1:]),out
 def test_mixed_ieee_counts_and_no_fault_payload_rescan(self):
  s,out=self.summary('mixed');self.assertEqual([int(s[k])for k in('words','finite','nan','positive_infinity','negative_infinity','nonfinite_effective')],[4096,4092,2,1,1,4]);self.assertEqual(s['first_nonfinite_index'],'0');self.assertEqual(s['first_nonfinite_kind'],'NAN');self.assertIn('words=4096\n',out);self.assertEqual(s['context'],'0')
 def test_finite_extremes_subnormal_and_signed_zero(self):
  s,_=self.summary('finite_extremes');self.assertEqual((s['finite'],s['nan'],s['positive_infinity'],s['negative_infinity']),('4096','0','0','0'));self.assertEqual((s['first_nonfinite_index'],s['first_nonfinite_kind'],s['first_nonfinite_region']),('4096','NONE','NONE'))
 def test_upper_half_is_effective(self):
  s,_=self.summary('upper');self.assertEqual(s['first_nonfinite_index'],'128');self.assertEqual(s['first_nonfinite_region'],'EFFECTIVE');self.assertEqual(s['effective_words'],'4096');self.assertEqual(s['padding_words'],'0')
 def test_no_scan_outside_healthy_handshake_pc_scope(self):
  for case in('empty','no_pc','no_completion','no_status','no_ready','no_valid'):
   with self.subTest(case=case):
    s,out=self.summary(case);self.assertEqual(s['sample_valid'],'0');self.assertEqual(s['accepted_samples'],'0');self.assertEqual(s['words'],'0');self.assertEqual(s['finite'],'0');self.assertEqual(s['first_nonfinite_index'],'4096');self.assertEqual(s['first_nonfinite_kind'],'NONE');self.assertEqual(s['mapping'],'NONE');self.assertIn('words=0\n',out)
 def test_supported_and_unsupported_mapping(self):
  s,_=self.summary('last_window');self.assertEqual(s['effective_words'],'4096');self.assertEqual(s['first_nonfinite_region'],'EFFECTIVE')
  for case in('unsupported','bad_context'):
   s,_=self.summary(case);self.assertEqual(s['mapping'],'UNSUPPORTED_MAPPING');self.assertEqual(s['unknown_region_words'],'4096');self.assertEqual(s['nonfinite_unknown_region'],'1');self.assertEqual(s['first_nonfinite_region'],'UNKNOWN')
 def test_last_error_are_not_masked(self):
  s,_=self.summary('error_last');self.assertEqual((s['result_last'],s['result_error'],s['nan']),('0','1','1'))
 def test_later_pc_fault_does_not_relabel_sample(self):
  s,out=self.summary('later_fault');self.assertEqual((s['pc'],s['completions'],s['fault_pc'],s['fault_at_target_pc']),('1','1','2','0'));self.assertEqual(s['finite'],'4096');self.assertIn('words=4096\n',out)
 def test_old_three_lines_exact_order_and_capture_count(self):
  for case in('mixed','empty','unsupported'):
   new=self.run_case(case).splitlines();old=self.run_case(case,True).splitlines();newold=[x for x in new if x.startswith('HOST_FIRST_FAULT')];oldold=[x for x in old if x.startswith('HOST_FIRST_FAULT')];self.assertEqual(newold,oldold);self.assertEqual(len(newold),3);self.assertEqual(new[:3],old[:3]);self.assertEqual(new[-1].split()[1],old[-1].split()[1])
 def test_max_uint64_stdout_bounded(self):
  out=self.run_case('max');self.assertLess(len(out.encode()),1024);self.assertEqual(len(out.splitlines()),1)
 def test_complete_physical_map_bijection(self):
  pairs={(c%128,160+16*(c//128)+r)for r in range(16)for c in range(256)};self.assertEqual(pairs,{(m,n)for m in range(128)for n in range(160,192)});self.assertEqual(len(pairs),4096)
class Source(unittest.TestCase):
 def test_exact_original_header_inverse(self):
  s=(SOURCE/'readonly_first_fault.hpp').read_text();self.assertEqual(hashlib.sha256(LEGACY_HEADER.encode()).hexdigest(),LEGACY_SHA);a=s.index('// Independent bounded summary;');b=s.index('class Collector {',a);block=s[a:b];self.assertEqual(hashlib.sha256(block.encode()).hexdigest(),NEW_BLOCK_SHA);self.assertEqual(s.count(block),1);s=s.replace(block,'')
  edits=[('#include "readonly_terminal_finite_access.hpp"\n',''),('    TerminalSummary terminal{};\n    std::uint64_t terminal_samples=0;\n',''),('                print_terminal_summary(terminal,terminal_samples,top.io_pc);\n',''),('            if (top.io_pc==1 && completions==1 && current.values[107]==0 && current.values[108]!=0 && current.values[109]!=0) {\n                terminal=classify_terminal(top,current,top.io_pc);\n                ++terminal_samples;\n            }\n','')]
  for old,new in edits:self.assertEqual(s.count(old),1);s=s.replace(old,new)
  self.assertEqual(hashlib.sha256(s.encode()).hexdigest(),LEGACY_SHA);self.assertEqual(s.encode(),LEGACY_HEADER.encode())
 def test_schema_digest_exact(self):
  h=hashlib.sha256(RECORD.read_bytes()).hexdigest();self.assertIn('"'+h+'"',(SOURCE/'readonly_first_fault.hpp').read_text())
if __name__=='__main__':unittest.main()
