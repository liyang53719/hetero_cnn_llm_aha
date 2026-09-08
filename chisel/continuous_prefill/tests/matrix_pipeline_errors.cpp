// SPDX-License-Identifier: Apache-2.0
// Error/drain/reset tests using the production service and real arithmetic.
#define main positive_probe_main
#include "matrix_pipeline.cpp"
#undef main
static void step(Test&t,unsigned ctx,bool clear,bool last,bool finish){
 auto&d=t.d;for(unsigned i=0;i<8;i++)d.io_step_bits_a[i]=0;for(unsigned i=0;i<128;i++)d.io_step_bits_b[i]=0;
 d.io_step_bits_context=ctx;d.io_step_bits_clear=clear;d.io_step_bits_last=last;d.io_step_bits_finish=finish;d.io_step_bits_emit=0;d.io_step_valid=1;t.eval();unsigned limit=0;while(!d.io_step_ready&&limit++<100)t.tick();ck(d.io_step_ready,"step did not accept");t.tick();d.io_step_valid=0;t.eval();
}
int main(int argc,char**argv){try{
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);ck(argc==2,"NEW_OUTPUT");std::filesystem::path out(argv[1]);ck(!std::filesystem::exists(out),"preserve outputs");std::filesystem::create_directories(out);auto obj=std::make_unique<Test>(out);auto&t=*obj;auto&d=t.d;
 for(unsigned mode=0;mode<5;mode++){
  d.io_result_ready=1;d.io_done_ready=0;t.group(mode==0?0:255,101+mode);
  unsigned expected=0;
  if(mode==1)step(t,5,true,true,true);
  if(mode==2){step(t,0,true,false,false);step(t,0,true,true,true);expected=8;}
  if(mode==3){step(t,0,true,false,false);step(t,1,true,false,false);step(t,0,false,true,true);expected=16;}
  if(mode==4){for(unsigned i=0;i<13;i++)step(t,i%5,i<5,false,false);expected=104;d.io_abort=1;t.tick();}
  unsigned wait=0;while(!d.io_done_valid&&wait++<200){ck(!d.io_result_valid,"suppressed partial unexpectedly emitted");t.tick();}
  ck(d.io_done_valid&&d.io_done_bits_error&&d.io_done_bits_tag==101+mode,"failed to close erroneous group");
  ck(d.io_resetRequired&&d.io_acceptedSteps==expected,"incorrect poison/physical issue accounting");
  for(unsigned i=0;i<7;i++){t.tick();ck(d.io_done_valid&&d.io_done_bits_error,"unstable error result");}
  d.io_done_ready=1;t.tick();d.io_done_ready=0;ck(!d.io_group_ready,"new arithmetic after error");
  d.io_abort=0;d.io_step_valid=0;d.reset=1;t.tick(6);d.reset=0;t.tick();
  t.run(255,5,4,false);std::cout<<"PIPELINE_ERROR_RECOVERY_PASS mode="<<mode<<" previous_steps="<<expected<<" recovered_fp32=81920 same_dut=1\n";
  d.reset=1;t.tick(6);d.reset=0;t.tick();
 }
 t.actual.flush();t.reference.flush();ck(t.actual.good()&&t.reference.good(),"evidence write");std::cout<<"PIPELINE_FAILURE_GATE_PASS cases=5 reset_recoveries=5 recovered_fp32="<<t.checked<<" bit_differences=0\n";return 0;
}catch(const std::exception&e){std::cerr<<"PIPELINE_FAILURE_GATE_FAIL: "<<e.what()<<std::endl;return 1;}}
