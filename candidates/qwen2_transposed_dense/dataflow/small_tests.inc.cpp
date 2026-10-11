static unsigned rejections=0;
template<class F> static void reject(const char* name,F f){bool caught=false;try{f();}catch(const std::runtime_error&){caught=true;}need(caught,std::string("missed rejection: ")+name);rejections++;}
static uint64_t digest(const std::vector<float>& v,size_t a,size_t n){uint64_t h=1469598103934665603ULL;for(size_t i=a;i<a+n;i++){h^=bits(v[i]);h*=1099511628211ULL;}return h;}
static void writePrefix(PrefixTransport& p,unsigned ctx,unsigned end,unsigned marker){
  p.beginWrite(p.jobGeneration,17,ctx,end);
  for(unsigned b=0;b<256;b++){
    for(unsigned j=0;j<16;j++)p.payload[j]=bits(float(marker+b*16+j));
    p.writeBeat(p.jobGeneration,17,ctx,end,p.address(ctx,b),b);
  }
  p.acknowledge(p.jobGeneration,17,ctx,end,true);
}
static PrefixTransport saved(){PrefixTransport p(17,2,allocateJobGeneration());p.startSweep(16);writePrefix(p,0,16,1000);writePrefix(p,1,16,20000);p.finishSweep();return p;}
static void faultCases(){
  auto checkPoison=[](PrefixTransport& p){need(p.poisoned,"active protocol fault did not poison");reject("resume poisoned prefix",[&]{p.reusable();});};
  {auto p=saved();reject("stale prefix",[&]{p.beginRead(p.jobGeneration,17,0,15);});checkPoison(p);}
  {auto p=saved();reject("wrong owner",[&]{p.beginRead(p.jobGeneration,18,0,16);});checkPoison(p);}
  {auto p=saved();p.beginRead(p.jobGeneration,17,0,16);reject("aliased address",[&]{p.readBeat(p.jobGeneration,17,0,16,p.address(1,0),0);});checkPoison(p);}
  {auto p=saved();p.beginRead(p.jobGeneration,17,0,16);reject("skipped restore beat",[&]{p.readBeat(p.jobGeneration,17,0,16,p.address(0,1),1);});checkPoison(p);}
  {auto p=saved();p.beginRead(p.jobGeneration,17,0,16);p.readBeat(p.jobGeneration,17,0,16,p.address(0,0),0);p.consumed();reject("duplicate restore beat",[&]{p.readBeat(p.jobGeneration,17,0,16,p.address(0,0),0);});checkPoison(p);}
  {auto p=saved();p.beginRead(p.jobGeneration,17,0,16);p.readBeat(p.jobGeneration,17,0,16,p.address(0,0),0);reject("seed hold overwrite",[&]{p.readBeat(p.jobGeneration,17,0,16,p.address(0,1),1);});checkPoison(p);}
  {auto p=saved();p.beginRead(p.jobGeneration,17,0,16);p.readBeat(p.jobGeneration,17,0,16,p.address(0,0),0);p.consumed();reject("partial seed reuse",[&]{p.reusable();});checkPoison(p);}
  {PrefixTransport p(17,1,allocateJobGeneration());reject("uncommitted sentinel",[&]{p.beginRead(p.jobGeneration,17,0,16);});checkPoison(p);}
  {auto p=saved();p.memory[0]=PrefixTransport::sentinel;p.beginRead(p.jobGeneration,17,0,16);reject("physical unwritten sentinel",[&]{p.readBeat(p.jobGeneration,17,0,16,p.address(0,0),0);});checkPoison(p);}
  {PrefixTransport p(17,1,allocateJobGeneration());p.startSweep(16);p.beginWrite(p.jobGeneration,17,0,16);reject("early context reuse",[&]{p.reusable();});checkPoison(p);}
  {PrefixTransport p(17,1,allocateJobGeneration());p.startSweep(16);p.beginWrite(p.jobGeneration,17,0,16);reject("incomplete write ACK",[&]{p.acknowledge(p.jobGeneration,17,0,16,true);});checkPoison(p);}
  {PrefixTransport p(17,1,allocateJobGeneration());p.startSweep(16);p.beginWrite(p.jobGeneration,17,0,16);
    for(unsigned b=0;b<256;b++){for(auto& x:p.payload)x=bits(1.0f);p.writeBeat(p.jobGeneration,17,0,16,p.address(0,b),b);}
    reject("failed ACK",[&]{p.acknowledge(p.jobGeneration,17,0,16,false);});checkPoison(p);
    PrefixTransport reset(17,1,allocateJobGeneration());need(reset.jobGeneration!=p.jobGeneration,"reset did not change job identity");reset.startSweep(16);reset.beginWrite(reset.jobGeneration,17,0,16);
    for(unsigned b=0;b<256;b++){for(auto& x:reset.payload)x=bits(2.0f);reset.writeBeat(reset.jobGeneration,17,0,16,reset.address(0,b),b);}
    reject("delayed old-job ACK",[&]{reset.acknowledge(p.jobGeneration,17,0,16,true);});checkPoison(reset);}
  {PrefixTransport p(17,2,allocateJobGeneration());p.startSweep(16);writePrefix(p,0,16,1);reject("missing context ACK",[&]{p.finishSweep();});checkPoison(p);}
  {PrefixTransport p(17,1,allocateJobGeneration());p.startSweep(16);writePrefix(p,0,16,1);reject("duplicate ACK",[&]{p.acknowledge(p.jobGeneration,17,0,16,true);});checkPoison(p);}
  {auto p=saved();p.startSweep(32);reject("overwrite without restoring",[&]{p.beginWrite(p.jobGeneration,17,0,32);});checkPoison(p);}
  {Publication p(8960,2,100);reject("early K final",[&]{p.begin(7680,0,1);});need(p.poisoned,"publication fault not sticky");reject("publish after fault",[&]{p.publish();});}
  {Publication p(8960,2,100);p.begin(8960,0,1);reject("reuse before final ACK",[&]{p.begin(8960,1,1);});}
  {Publication p(8960,2,100);p.begin(8960,0,1);p.wrote(100,0,0);reject("failed final ACK",[&]{p.ack(100,0,false);});reject("failed final publish",[&]{p.publish();});}
  {Publication p(8960,2,100);p.begin(8960,0,1);p.wrote(100,p.acked,0);p.ack(100,p.acked,true);reject("missing terminal ACK",[&]{p.publish();});}
  {Publication p(8960,2,100);p.begin(8960,0,1);p.wrote(100,p.acked,0);p.ack(100,p.acked,true);p.begin(8960,1,1);p.wrote(100,p.acked,0);p.ack(100,p.acked,true);p.publish();need(p.published,"complete publication absent");}
  {Publication p(8960,1,100);p.begin(8960,0,2);p.wrote(100,0,0);reject("partial final output ACK",[&]{p.ack(100,0,true);});}
  {Publication p(8960,1,100);p.begin(8960,0,1);p.wrote(100,0,0);reject("old final output ACK",[&]{p.ack(99,0,true);});}
  {PrefixTransport p(17,1,allocateJobGeneration());p.startSweep(16);p.beginWrite(p.jobGeneration,17,0,16);
    reject("old-job prefix write beat",[&]{p.writeBeat(p.jobGeneration-1,17,0,16,p.address(0,0),0);});checkPoison(p);}
  std::cout<<"PROTOCOL_FAULTS rejected="<<rejections<<" sticky_poison=1 job_generation=1 rtl_fault_drain=0"<<std::endl;
}
static void physicalPrefix(){
  auto p=std::make_unique<DataflowPhysical>();PrefixTransport d(17,2,allocateJobGeneration());
  for(unsigned s=0;s<8;s++)for(unsigned r=0;r<16;r++)for(unsigned c=0;c<32;c++)p->finalValue[s][r][c]=float(100000+s*10000+r*100+c);
  d.startSweep(16);
  for(unsigned ctx=0;ctx<2;ctx++){
    d.beginWrite(d.jobGeneration,17,ctx,16);
    for(unsigned b=0;b<256;b++){for(unsigned j=0;j<16;j++)d.payload[j]=bits(Harness::physicalFlat(p->finalValue,b*16+j)+float(ctx));d.writeBeat(d.jobGeneration,17,ctx,16,d.address(ctx,b),b);}
    d.acknowledge(d.jobGeneration,17,ctx,16,true);
  }
  d.finishSweep();unsigned checked=0;
  for(unsigned ctx=0;ctx<2;ctx++)for(unsigned s=0;s<8;s++)for(unsigned r=0;r<16;r++)for(unsigned c=0;c<32;c++){
    const uint64_t addr=PrefixTransport::base+ctx*16384+r*1024+(s*32+c)*4;
    need(d.memory.at((addr-PrefixTransport::base)/4)==bits(float(100000+s*10000+r*100+c+ctx)),"DDR physical row/slice/column mismatch");checked++;
  }
  d.memory[7]=bits(-123.5f); // Independent address mutation must change the restore.
  d.beginRead(d.jobGeneration,17,0,16);
  for(unsigned b=0;b<256;b++){
    d.readBeat(d.jobGeneration,17,0,16,d.address(0,b),b);
    for(unsigned j=0;j<16;j++)Harness::physicalFlat(p->accum[0],b*16+j)=fp(d.payload[j]);d.consumed();
  }
  d.reusable();need(bits(p->accum[0][0][0][7])==bits(-123.5f),"restore did not read actual address-indexed DDR");
  std::cout<<"PREFIX_LAYOUT exact_addresses="<<checked<<" external_mutation_observed=1 seed_payload_bytes=64"<<std::endl;
}
static void allContexts(){
  PrefixTransport p(17,48,allocateJobGeneration());p.startSweep(2560);
  for(unsigned ctx=0;ctx<48;ctx++)writePrefix(p,ctx,2560,ctx*10000+1);
  need(p.ackBitmap==((1ULL<<48)-1),"48-bit ACK bitmap");p.finishSweep();
  for(unsigned ctx=0;ctx<48;ctx++){
    p.beginRead(p.jobGeneration,17,ctx,2560);
    for(unsigned b=0;b<256;b++){
      p.readBeat(p.jobGeneration,17,ctx,2560,p.address(ctx,b),b);
      for(unsigned j=0;j<16;j++)need(p.payload[j]==bits(float(ctx*10000+1+b*16+j)),"48-context restore value");p.consumed();
    }
  }
  p.reusable();need(p.readBitmap==((1ULL<<48)-1)&&p.address(47,255)+64==PrefixTransport::base+786432,"last prefix byte/bitmap");
  PrefixTransport missing(17,48,allocateJobGeneration());missing.startSweep(2560);
  for(unsigned ctx=0;ctx<47;ctx++)writePrefix(missing,ctx,2560,ctx+1);
  reject("missing context47 ACK",[&]{missing.finishSweep();});need(missing.poisoned,"last ACK fault poison");
  std::cout<<"PREFIX_ALL_CONTEXTS contexts=48 beat_addresses=12288 values=196608 high_bitmap_bits=16 missing_last_ack_rejected=1"<<std::endl;
}
static void tileFaults(){
  const unsigned before=rejections;
  auto p=std::make_unique<DataflowPhysical>();
  p->beginTile(0,0,16,16);
  reject("unready FFN consumer",[&]{p->getTile(0,0,0,0);});need(p->tilePoisoned,"FFN fault not sticky");
  reject("FFN resume",[&]{p->putTile(0,0,0,0,1.0f);});
  p=std::make_unique<DataflowPhysical>();p->beginTile(0,0,16,16);
  reject("FFN early slot reuse",[&]{p->beginTile(0,160,16,16);});
  p=std::make_unique<DataflowPhysical>();p->beginTile(0,0,16,16);p->putTile(0,0,0,0,1.0f);
  reject("FFN duplicate address write",[&]{p->putTile(0,0,0,0,1.0f);});
  p=std::make_unique<DataflowPhysical>();p->beginTile(0,0,16,16);
  reject("FFN incomplete seal",[&]{p->sealTile(0,16);});
  p=std::make_unique<DataflowPhysical>();p->beginTile(0,0,16,16);
  reject("FFN padded producer substitution",[&]{p->putTile(0,0,16,0,1.0f);});
  auto complete=[&](){p=std::make_unique<DataflowPhysical>();p->beginTile(0,0,16,16);
    for(int m=0;m<16;m++)for(int n=0;n<16;n++)p->putTile(0,0,m,n,float(m*16+n));p->sealTile(0,16);};
  complete();reject("FFN stale group",[&]{p->getTile(0,160,0,0);});
  complete();reject("FFN early release",[&]{p->releaseTile(0,16);});
  complete();p->getTile(0,0,0,0);reject("FFN duplicate consumer",[&]{p->getTile(0,0,0,0);});
  complete();reject("FFN skipped consumer",[&]{p->getTile(0,0,0,1);});
  std::cout<<"FFN_LIFECYCLE_FAULTS rejected="<<rejections-before<<" sticky_poison=1"<<std::endl;
}
static void oneDown(int M,int K,int N,int chunk,int pattern,bool bias){
  const size_t wi=size_t(M)*K,bi=wi+size_t(K)*N,oi=bi+N;
  Harness src(M,oi+size_t(M)*N);uint32_t seed=0x52d78a31u;
  auto random=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
  for(int m=0;m<M;m++)for(int k=0;k<K;k++){
    float x=fp(0x3f000000u+(random()&0x007fffffu));if(random()&1)x=-x;
    if(pattern==1)x=k==K-1?fp(0x80010000u):0.0f;
    if(pattern==2)x=k==0?fp(52u<<23):0.0f;
    if(pattern==3)x=1.0f;
    if(pattern==4)x=(k&1)?fp(0x80000000u):0.0f;
    src.reference[size_t(m)*K+k]=x;
  }
  for(int k=0;k<K;k++)for(int n=0;n<N;n++){
    float x=bf(float(int(random()%257)-128)/128.0f);
    if(pattern==1)x=k==K-1?fp(0x00010000u):0.0f;
    if(pattern==2)x=k==0?fp(53u<<23):0.0f;
    if(pattern==3)x=k==0?16777216.0f:(k==1?1.0f:(k==2?-16777216.0f:0.0f));
    if(pattern==4)x=(n&1)?-1.0f:1.0f;
    src.reference[wi+size_t(k)*N+n]=x;
  }
  for(int n=0;n<N;n++)src.reference[bi+n]=(pattern==1||pattern==4)?fp(0x80000000u):(pattern==2?0.0f:(pattern==3?1.0f:fp(0x35800000u+uint32_t(n))));
  const char* evidence=std::getenv("DATAFLOW_EVIDENCE_DIR");need(evidence,"synthetic evidence destination required");
  const std::string file="input_down_m"+std::to_string(M)+"_k"+std::to_string(K)+"_n"+std::to_string(N)+"_pattern"+std::to_string(pattern)+".f32le";
  std::ofstream fixture(std::filesystem::path(evidence)/file,std::ios::binary);fixture.write(reinterpret_cast<const char*>(src.reference.data()),oi*4);need(bool(fixture),"synthetic fixture save");fixture.close();
  Harness oracle=src,mapped=src;
  oracle.dense(0,wi*4,oi*4,K,N,bias?int64_t(bi*4):-1);
  mapped.dataflowDown(0,wi*4,oi*4,K,N,bias?int64_t(bi*4):-1,chunk);
  for(size_t i=0;i<size_t(M)*N;i++){
    need(bits(mapped.reference[oi+i])==bits(oracle.reference[oi+i]),"down v0 bit mismatch");
    if(pattern==1)need(bits(mapped.reference[oi+i])==0x80000000u,"negative zero lost");
    if(pattern==2)need(bits(mapped.reference[oi+i])==1u,"subnormal lost");
    if(pattern==3)need(bits(mapped.reference[oi+i])==bits(bias?1.0f:0.0f),"K/bias order changed");
  }
  need(digest(src.reference,0,oi)==digest(mapped.reference,0,oi),"down modified input");
  std::cout<<"DOWN_BIT_EXACT m="<<M<<" k="<<K<<" n="<<N<<" chunk="<<chunk<<" pattern="<<pattern<<" bias="<<bias
    <<" values="<<M*N<<" input_fnv64="<<digest(src.reference,0,oi)<<" output_fnv64="<<digest(mapped.reference,oi,size_t(M)*N)<<std::endl;
}
static void tileConsumer(){
  auto p=std::make_unique<DataflowPhysical>();Harness h(128,128*160);
  for(int m=0;m<128;m++)for(int k=0;k<1536;k++)p->cell(m,k)=uint16_t(0x3f80+(m+k)%64);
  // Full physical A occupancy, all banks/rows and last tile columns. Actual
  // matrix producers are separately exercised in the synthetic whole graph.
  for(int slot=0;slot<2;slot++){
    p->beginTile(slot,0,160,128);
    for(int m=0;m<128;m++)for(int n=0;n<160;n++)p->putTile(slot,0,m,n,slot?2.0f:-0.5f);
    p->sealTile(slot,128);
  }
  const int m=113,n=151;auto* cell=p->tileCell(0,m,n);const auto u=bits(-1.5f);cell[0]=uint16_t(u);cell[1]=uint16_t(u>>16);
  h.consumeFfnTiles(*p,0,160,0,160);
  float g=-1.5f,e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);
  need(bits(h.get(0,m*160+n))==bits(mul(mul(sig,g),2.0f)),"FFN consumer bypassed physical producer writes");
  for(int m=0;m<128;m++)for(int k=0;k<1536;k++)need(p->cell(m,k)==uint16_t(0x3f80+(m+k)%64),"FFN SRAM slots clobbered retained A");
  for(int slot=0;slot<3;slot++)need(p->tileReads[slot]==20480&&p->tileStores[slot]==20480,"tile consumer physical traffic");
  std::cout<<"FFN_CONSUMER physical_mutation_observed=1 physical_values=61440 retained_a_halfwords=196608"<<std::endl;
}
static void domainErrors(){
  unsigned rejectedCount=0;const int M=16,K=32,N=32;const size_t wi=M*K,bi=wi+K*N,oi=bi+N;
  for(unsigned kind=0;kind<9;kind++){
    Harness h(M,oi+M*N);for(size_t i=0;i<oi;i++)h.reference[i]=1.0f;
    if(kind==0)h.reference[0]=fp(0x7fc00042u);
    if(kind==1)h.reference[0]=fp(0x7f800000u);
    if(kind==2)h.reference[wi]=fp(0xff800000u);
    if(kind==3)h.reference[wi]=fp(0x7fc00043u);
    if(kind==4)h.reference[0]=fp(0x7f7fffffu);
    if(kind==5)h.reference[wi]=fp(0x3f800001u);
    if(kind==6){h.reference[0]=fp(0x7f7f0000u);h.reference[wi]=fp(0x7f7f0000u);}
    if(kind==7)h.reference[bi]=fp(0x7f800000u);
    if(kind==8){h.reference[wi]=fp(0x7f7f0000u);h.reference[bi]=fp(0x7f7fffffu);}
    reject("down domain/nonfinite",[&]{h.dataflowDown(0,wi*4,oi*4,K,N,bi*4,16);});need(!h.downPublished,"domain fault published final");rejectedCount++;
  }
  std::cout<<"DOMAIN_ERRORS rejected="<<rejectedCount<<" unpublished=1 per_step_hardware_flags=0"<<std::endl;
}
int main(){try{
  verifyFloatEnvironment();physicalPrefix();faultCases();allContexts();tileConsumer();tileFaults();domainErrors();
  oneDown(16,16,16,16,0,false);oneDown(32,32,32,16,0,true);
  oneDown(16,272,160,80,0,true);oneDown(32,272,192,80,0,true);
  oneDown(128,272,192,80,0,true);oneDown(16,8960,32,2560,0,false);
  for(int pattern=1;pattern<=4;pattern++)oneDown(pattern&1?16:32,64,48,16,pattern,true);
  std::cout<<"DATAFLOW_SMALL_PASS cases=10 official_forward=0 official_m16=0 official_m128=0"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
