static uint64_t checksum(const std::vector<float>& v,size_t first,size_t count){uint64_t h=1469598103934665603ULL;for(size_t i=first;i<first+count;i++){h^=bits(v[i]);h*=1099511628211ULL;}return h;}
template<class Fn> static void rejected(Fn fn){bool caught=false;try{fn();}catch(const std::runtime_error&){caught=true;}need(caught,"eliminated DDR arithmetic was allowed");}
static void fullCase(unsigned tokens){
  SoftwareRecipe mapped(tokens);OracleRecipe oracle(tokens);
  uint32_t seed=0x137ce921u;
  auto random=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
  for(size_t i=0;i<WRITABLE_START/4;i++)mapped.reference[i]=bf(float(int(random()%129)-64)/128.0f);
  for(int i=0;i<H;i++){mapped.reference[OFF_GAMMA0/4+i]=1.0f;mapped.reference[OFF_GAMMA1/4+i]=1.0f;}
  for(size_t i=0;i<size_t(MAX_TOKENS)*HD/2;i++){mapped.reference[OFF_COS/4+i]=1.0f;mapped.reference[OFF_SIN/4+i]=0.0f;}
  std::copy(mapped.reference.begin(),mapped.reference.begin()+WRITABLE_START/4,oracle.reference.begin());
  const auto input=checksum(mapped.reference,0,WRITABLE_START/4);
  const char* evidence=std::getenv("DATAFLOW_EVIDENCE_DIR");need(evidence,"synthetic evidence destination required");
  std::ofstream fixture(std::filesystem::path(evidence)/("input_fullgraph_m"+std::to_string(tokens)+".f32le"),std::ios::binary);
  fixture.write(reinterpret_cast<const char*>(mapped.reference.data()),WRITABLE_START);need(bool(fixture),"fullgraph fixture save");fixture.close();
  // Four deliberately small K chunks exercise all three save/restore boundaries.
  mapped.downChunk=64;oracle.computeReference();mapped.computeReference();
  size_t values=0;
  for(unsigned phase=0;phase<STAGES.size();phase++){
    const auto& s=STAGES[phase];const size_t count=size_t(tokens)*s.width;
    for(size_t i=0;i<count;i++)need(bits(mapped.observationGet(s.off,i))==bits(oracle.get(s.off,i)),std::string("fullgraph phase mismatch ")+s.name);
    std::ofstream stage(std::filesystem::path(evidence)/("synthetic_m"+std::to_string(tokens)+"_phase_"+std::to_string(phase)+"_"+s.name+".f32le"),std::ios::binary);
    for(size_t i=0;i<count;i++){const float v=mapped.observationGet(s.off,i);stage.write(reinterpret_cast<const char*>(&v),4);}need(bool(stage),"synthetic stage save");
    values+=count;std::cout<<"SYNTHETIC_STAGE_EXACT tokens="<<tokens<<" phase="<<phase<<" name="<<s.name<<" values="<<count<<std::endl;
  }
  need(checksum(mapped.reference,0,WRITABLE_START/4)==input,"wholegraph readonly input changed");
  for(auto off:{OFF_GATE,OFF_UP}){
    for(size_t i=0;i<size_t(MAX_TOKENS)*F;i++)need(bits(mapped.reference[off/4+i])==0x7fc00001u,"eliminated DDR gate/up became tensor backing");
    rejected([&]{mapped.get(off,0);});rejected([&]{mapped.put(off,0,1.0f);});
    rejected([&]{mapped.get(0,off/4);}); // Reject alias addressing too.
  }
  need(mapped.downPublished,"wholegraph consumed unpublished down");
  need(mapped.ffnInputValues==uint64_t(tokens)*H&&mapped.ffnWeightValues==2ULL*H*F&&mapped.ffnActValues==uint64_t(tokens)*F,"wholegraph FFN traffic");
  need(mapped.prefixReadBytes==3*16384&&mapped.prefixWriteBytes==3*16384,"wholegraph three prefix boundaries");
  std::cout<<"SYNTHETIC_FULLGRAPH_EXACT tokens="<<tokens<<" stages=15 values="<<values<<" input_fnv64="<<input
    <<" eliminated_ddr_guard_rejections=6 gate_up_external_bytes=0"<<std::endl;
}
int main(){try{verifyFloatEnvironment();fullCase(16);fullCase(32);fullCase(128);std::cout<<"DATAFLOW_FULLGRAPH_SMALL_PASS runs=3 stages=45 official_shape=0 official_forward=0"<<std::endl;return 0;}
catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
