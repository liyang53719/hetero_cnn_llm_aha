"""Cross-language synthetic NORMAL+BAD_BITS acquisition; never DUT/reference PASS."""
import argparse,hashlib,json,pathlib,struct,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'numeric'))
import moe_score_compare as m
HEADER_SHA='fc029f28224bf07452b36702b6c81f5cd196fd7870e81fe980efce13bffaf9df'
DRIVER_SHA='f4f00dffd348e1822e7fcb5ac59602579d693d7a8d04e221cdd3f0255b56b04c'
def main():
 p=argparse.ArgumentParser();p.add_argument('--producer',type=pathlib.Path,required=True);a=p.parse_args()
 header=a.producer.resolve()/'driver/moe_raw_score_observation.hpp';driver=header.with_name('host_axi_driver_non_dpi.cpp')
 assert hashlib.sha256(header.read_bytes()).hexdigest()==HEADER_SHA
 assert hashlib.sha256(driver.read_bytes()).hexdigest()==DRIVER_SHA
 results=[]
 with tempfile.TemporaryDirectory() as t:
  d=pathlib.Path(t);source=d/'fixture.cpp'
  source.write_text('''#include "moe_raw_score_observation.hpp"
#include <iostream>
int main(int argc,char**argv){
 const bool bad=argc>2;
 const uint32_t inputBad[]={0x7fc00001,0x7f800000,0xff800000,0xbf800000,0x80000000,0x3f800001};
 const uint32_t outputBad[]={0x7fc00002,0x7f800000,0xff800000,0xbf800000,0x80000000,0x3f800001,0,0x3b800001};
 moe_raw_score_observation::Collector c(3);
 for(unsigned token=0;token<128;++token){
  for(unsigned expert=0;expert<256;++expert){moe_raw_score_observation::Beat b;b.transactionId=0;b.ownerSequence=9;b.profile=3;b.token=token;b.expert=expert;b.score=bad&&token==0&&expert<6?inputBad[expert]:0x3b800000;c.capture(b,true,false);}
  for(unsigned rank=0;rank<8;++rank){moe_raw_score_observation::Beat b;b.transactionId=0;b.ownerSequence=9;b.profile=3;b.token=token;b.expert=rank;b.score=bad&&token==0?outputBad[rank]:0x3b800000;b.kind=1;b.rank=rank;b.last=rank==7;c.capture(b,true,false);}
 }
 c.close(true);c.write(argv[1]);
 std::cout<<c.inputMismatches()<<" "<<c.orderMismatches()<<" "<<c.nonfiniteScores()<<" "<<c.negativeScores()<<" "<<c.negativeZeroScores()<<" "<<c.aboveOneScores()<<"\\n";
 return 0;
}
''')
  subprocess.run(['c++','-std=c++17','-O0','-I',str(header.parent),str(source),'-o',str(d/'fixture')],check=True,capture_output=True,timeout=30)
  log='HOST_ROUTER_RAW_SCORE_V1 profile=3 transaction=0 owner=9 values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\nHOST_ROUTER_SELECTED_SCORE_V2 profile=3 transaction=0 owner=9 values=1024 score_bytes=4096 id_bytes=4096 dtype=FP32 index_dtype=UINT32 source=SELECTION_OUTPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\nCOMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=3 synthetic=1\n'
  ids=b''.join(struct.pack('<q',i%8) for i in range(1024));route=b''.join(struct.pack('<Q',(i//8)<<34|(i%8)<<31|(i%8)<<23|i//8) for i in range(1024))
  for mode in ('NORMAL','BAD_BITS'):
   output=d/mode;output.mkdir()
   run=subprocess.run([str(d/'fixture'),str(output)]+(['bad'] if mode=='BAD_BITS' else []),check=True,timeout=10,capture_output=True,text=True)
   counts=dict(zip(('input_score_mismatches','score_order_mismatches','nonfinite_scores','negative_scores','negative_zero_scores','above_one_scores'),map(int,run.stdout.split())))
   result=m.observe(output,log,3,struct.pack('<I',0x3b800000)*32768,route,ids)
   actual=result['actual_selected_output'];assert actual['status']=='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY'
   if mode=='NORMAL':
    assert actual['input_output_score_consistency']['element_mismatches']==0
    assert actual['official_selected_probability_by_rank']['element_mismatches']==0
   else:
    input_words=list(struct.unpack('<6I',(output/'router_selection_scores.fp32.actual.bin').read_bytes()[:24]))
    output_words=list(struct.unpack('<8I',(output/'router_selected_scores.fp32.actual.bin').read_bytes()[:32]))
    assert input_words==[0x7fc00001,0x7f800000,0xff800000,0xbf800000,0x80000000,0x3f800001]
    assert output_words==[0x7fc00002,0x7f800000,0xff800000,0xbf800000,0x80000000,0x3f800001,0,0x3b800001]
    assert counts['input_score_mismatches']==3 and counts['score_order_mismatches']>0 and counts['nonfinite_scores']==6
    diag=actual['input_output_score_consistency'];assert diag['element_mismatches']==3
    assert diag['actual_value_counts']==dict(nan=1,positive_infinity=1,negative_infinity=1,negative_finite=1,negative_zero=1,above_one_finite=1)
    assert diag['nonfinite_pair_count']==3
    assert actual['official_selected_probability_by_rank']['element_mismatches']==8
    assert result['full_probabilities']['element_mismatches']==6
   results.append(dict(mode=mode,cpp_diagnostic_counts=counts,consumer_full_probability_diagnostic=result['full_probabilities'],consumer_actual_output_diagnostic=actual,files=[dict(name=x.name,bytes=x.stat().st_size,sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in sorted(output.iterdir())]))
 print(json.dumps(dict(status='PASS_SYNTHETIC_CPP_COLLECTOR_TO_PYTHON_READER_NORMAL_AND_BAD_BITS_ONLY',actual_hardware_executed=False,official_reference_executed=False,collector_sha256=HEADER_SHA,driver_sha256=DRIVER_SHA,fixtures=results),indent=2))
if __name__=='__main__':main()
