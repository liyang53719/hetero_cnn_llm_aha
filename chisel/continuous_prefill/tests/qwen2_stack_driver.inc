// SPDX-License-Identifier: Apache-2.0
// DDR service only. Golden values are compared, never returned to the DUT.
struct Pending {bool write;uint64_t address,tag,mask;std::array<uint32_t,16> data;unsigned delay;};
class StackSim {
 public:
  VQwen2LayerStack d;
  unsigned tokens;
  uint64_t weights=0,rope=STACK_WEIGHT_BYTES*STACK_LAYERS;
  uint64_t hiddenA=rope+STACK_ROPE_BYTES,hiddenB=hiddenA+STACK_HIDDEN_BYTES;
  uint64_t scratch=hiddenB+STACK_HIDDEN_BYTES,total=scratch+STACK_SCRATCH_BYTES;
  std::vector<uint32_t> mem;
  std::vector<uint8_t> produced;
  std::vector<std::array<std::vector<float>,15>> expected;
  std::optional<Pending> pending;
  uint32_t rng=0x53719;
  uint64_t cycles=0,checked=0,previousBytes=0,writes=0,reads=0;
  unsigned commits=0,layers=0;
  explicit StackSim(unsigned n):tokens(n),mem(total/4,0x7fc00001u),produced(total/4,0),expected(STACK_LAYERS){
    d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_result_ready=0;d.io_memory_ready=0;d.io_response_valid=0;
    for(int i=0;i<5;i++){d.clock=0;d.eval();d.clock=1;d.eval();}d.clock=0;d.reset=0;d.eval();
  }
  uint32_t random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  uint64_t input(unsigned l)const{return l%2?hiddenB:hiddenA;}
  uint64_t output(unsigned l)const{return l%2?hiddenA:hiddenB;}
  uint64_t mapped(uint64_t offset,unsigned l)const{
    if(offset<OFF_COS)return weights+l*STACK_WEIGHT_BYTES+offset;
    if(offset<OFF_X)return rope+offset-OFF_COS;
    if(offset<WRITABLE_START)return input(l)+offset-OFF_X;
    if(offset>=OFF_Y)return output(l)+offset-OFF_Y;
    return scratch+offset-WRITABLE_START;
  }
  void load(){
    std::vector<float> previous;
    for(unsigned l=0;l<STACK_LAYERS;l++){
      NumericalReference ref(tokens,l*19);
      ref.initialize(1);
      if(l){for(size_t i=0;i<previous.size();i++)ref.set(OFF_X,i,previous[i]);ref.computeReference();}
      for(uint64_t p=0;p<STACK_WEIGHT_BYTES/4;p++)mem.at((weights+l*STACK_WEIGHT_BYTES)/4+p)=bits(ref.reference.at(p));
      if(!l){
        for(uint64_t p=0;p<STACK_ROPE_BYTES/4;p++)mem.at(rope/4+p)=bits(ref.reference.at(OFF_COS/4+p));
        for(size_t p=0;p<size_t(tokens)*H;p++)mem.at(hiddenA/4+p)=bits(ref.get(OFF_X,p));
      }
      for(unsigned phase=0;phase<15;phase++){
        const auto&s=STAGES[phase];const auto begin=ref.reference.begin()+s.off/4;
        expected[l][phase].assign(begin,begin+size_t(tokens)*s.width);
      }
      previous=expected[l][14];
    }
  }
  void compare(unsigned l,unsigned phase){
    need(l<STACK_LAYERS&&phase<15&&commits==l*15+phase,"stage order");
    need(!pending,"stage before write response");
    const auto&s=STAGES[phase];const auto address=mapped(s.off,l);
    const auto&want=expected[l][phase];
    for(size_t i=0;i<want.size();i++){
      need(produced.at(address/4+i),"unproduced intermediate");
      if(mem.at(address/4+i)!=bits(want[i])){
        std::cerr<<"MISMATCH layer="<<l<<" phase="<<phase<<" element="<<i<<" actual="<<std::hex<<mem.at(address/4+i)<<" expected="<<bits(want[i])<<std::dec<<"\n";
        throw std::runtime_error("numerical mismatch");
      }
    }
    checked+=want.size();commits++;
    std::cout<<"STACK_STAGE_CHECK layer="<<l<<" phase="<<phase<<" values="<<want.size()<<" bit_diffs=0 cycle="<<cycles<<std::endl;
  }
  void tick(){
    d.clock=0;d.io_memory_ready=!pending&&random()%5!=0;d.io_response_valid=pending&&pending->delay==0;
    if(pending){d.io_response_bits_tag=pending->tag;d.io_response_bits_error=0;for(int i=0;i<16;i++)d.io_response_bits_data[i]=pending->data[i];}
    d.eval();
    const bool req=d.io_memory_valid&&d.io_memory_ready,rsp=d.io_response_valid&&d.io_response_ready;
    const bool stage=d.io_stageCommit,layer=d.io_layerCommit;
    const unsigned l=d.io_layer,p=d.io_committedPhase;
    std::optional<Pending> next;
    if(req){
      Pending v{};v.write=d.io_memory_bits_write;v.address=d.io_memory_bits_address;v.tag=d.io_memory_bits_tag;v.mask=d.io_memory_bits_mask;v.delay=random()%4+1;
      need(v.address%64==0&&v.address+64<=total,"memory bound/alignment");
      if(v.write){
        need((v.address>=scratch&&v.address+64<=total)||(v.address>=output(l)&&v.address+64<=output(l)+STACK_HIDDEN_BYTES),"write to readonly/input region");
        for(int i=0;i<16;i++)v.data[i]=d.io_memory_bits_data[i];
      }else{
        for(int i=0;i<16;i++){
          uint64_t a=v.address+i*4;
          if(a>=scratch||(a>=input(l)&&a<input(l)+uint64_t(tokens)*H*4&&l>0))need(produced.at(a/4),"read unproduced scratch/previous layer");
          v.data[i]=mem.at(a/4);
        }
        reads+=64;
        if(l&&v.address>=input(l)&&v.address<input(l)+uint64_t(tokens)*H*4)previousBytes+=64;
      }
      next=v;
    }
    d.clock=1;d.eval();cycles++;
    if(rsp){
      if(pending->write){
        for(int i=0;i<64;i++)if((pending->mask>>i)&1){
          const auto ix=(pending->address+i)/4;const auto shift=(i%4)*8;
          mem.at(ix)=(mem.at(ix)&~(255u<<shift))|(((pending->data[i/4]>>shift)&255u)<<shift);
          produced.at(ix)=1;writes++;
        }
      }
      pending.reset();
    }else if(pending&&pending->delay)pending->delay--;
    if(next){need(!pending,"more than one memory transaction");pending=next;}
    if(stage)compare(l,p);
    if(layer){need(commits==(layers+1)*15,"layer before all stage commits");layers++;}
  }
  void run(){
    d.io_launch_bits_weights=weights;d.io_launch_bits_weightStride=STACK_WEIGHT_BYTES;d.io_launch_bits_rope=rope;d.io_launch_bits_scratch=scratch;
    d.io_launch_bits_hiddenA=hiddenA;d.io_launch_bits_hiddenB=hiddenB;d.io_launch_bits_limit=total;
    d.io_launch_bits_tokens=tokens;d.io_launch_bits_layers=STACK_LAYERS;d.io_launch_bits_epoch=31;
    d.io_launch_valid=1;do{tick();}while(!d.io_launch_ready&&cycles<2);d.io_launch_valid=0;
    while(!d.io_result_valid&&cycles<50000000000ULL)tick();
    need(d.io_result_valid&&d.io_result_bits_status==0,"stack failed/timeout");need(!d.io_resetRequired,"unexpected reset required");
    need(layers==STACK_LAYERS&&commits==STACK_LAYERS*15&&!pending,"incomplete stack");
    need(d.io_result_bits_output==output(STACK_LAYERS-1),"output arena parity");
    if(STACK_LAYERS>1)need(previousBytes>0,"no previous-layer payload consumed");
    std::cout<<"CONTINUOUS_QWEN2_STACK_PASS tokens="<<tokens<<" hidden="<<H<<" ffn="<<F<<" layers="<<layers<<" stages="<<commits<<" checked_fp32="<<checked<<" bit_diffs=0 previous_layer_read_bytes="<<previousBytes<<" cycles="<<cycles<<" macs="<<d.io_result_bits_usefulMacs<<" executed_macs="<<d.io_result_bits_executedMacs<<" host_intermediate_writes=0 synthetic_weights=true canonical_512_array=0"<<std::endl;
  }
};
int main(int argc,char**argv){try{Verilated::commandArgs(argc,argv);std::fesetround(FE_TONEAREST);unsigned n=argc>1?std::stoul(argv[1]):17;need(n>0&&n<=MAX_TOKENS,"token bound");StackSim sim(n);sim.load();sim.run();return 0;}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
