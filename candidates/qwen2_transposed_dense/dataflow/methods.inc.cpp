  // Observer-only full-tensor copies. get() rejects these eliminated DDR ranges.
  std::vector<float> observerGate,observerUp;
  int downChunk=2560;
  uint64_t prefixReadBytes=0,prefixWriteBytes=0,ffnTileReadBytes=0,ffnTileWriteBytes=0;
  uint64_t ffnInputValues=0,ffnWeightValues=0,ffnActValues=0;
  bool downPublished=false;
  void observe(unsigned slot,size_t index,float v){
    auto& observer=slot?observerUp:observerGate;
    if(observer.empty())observer.assign(size_t(tokens)*F,fp(0x7fc00001u));
    need(index<observer.size()&&bits(observer[index])==0x7fc00001u,"duplicate observer write");observer[index]=v;
  }
  float observationGet(uint64_t off,size_t i)const{
    if(off==OFF_GATE)return observerGate.at(i);
    if(off==OFF_UP)return observerUp.at(i);
    return get(off,i);
  }
  void loadDataflowA(DataflowPhysical& p,uint64_t in,int K,int base,int depth){
    const bool rmw=true;
@@LOAD_A@@
  }
  void clearDataflowContexts(DataflowPhysical& p,int count){
    need(p.metaCount==0&&p.fifoCount==0&&p.finalCount==0,"dataflow reuse before drain");
    need(count>0&&count<=5,"five context limit");p.contextPeak=std::max(p.contextPeak,unsigned(count));
    for(int ctx=0;ctx<count;ctx++)for(auto& slice:p.accum[ctx])for(auto& row:slice)for(auto& x:row)x=0.0f;
  }
  void computeDataflowTile(DataflowPhysical& p,uint64_t w,int K,int N,int ng,int columns,int ab,int ad,int aBase){
    const int count=(columns+31)/32;
@@ISSUE_K@@
  }
  void captureDataflow(DataflowPhysical& p,int ctx){
    need(p.metaCount==0&&p.fifoCount==0&&p.finalCount==0,"dataflow capture before drain");
    std::memcpy(p.result[0],p.accum[ctx],sizeof(p.accum[ctx]));p.fifoCount=1;p.fifoPeak=1;
    std::memcpy(p.finalValue,p.result[0],sizeof(p.finalValue));p.fifoCount=0;p.finalCount=1;p.finalPeak=1;p.captures++;
  }
  static float& physicalFlat(float (&tile)[8][16][32],unsigned index){
    // DDR physical row-major [16][256], not C++ [slice][row][column] order.
    unsigned row=index/256,column=index%256;return tile[column/32][row][column%32];
  }
  void dataflowDown(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias=-1,int chunk=2560){
    need(tokens>0&&tokens<=128&&tokens%16==0&&K>0&&K%16==0&&N>0&&N%16==0&&N<=1536&&
      chunk>0&&chunk<=2560&&chunk%16==0,"down dataflow shape");
    auto storage=std::make_unique<DataflowPhysical>();auto& p=*storage;
    const uint64_t job=allocateJobGeneration();PrefixTransport ddr(17,(N+31)/32,job);Publication publication(K,(N+31)/32,job);
    downPublished=false;
    for(int ab=0;ab<K;ab+=chunk){
      const int ad=std::min(chunk,K-ab),end=ab+ad;const bool terminal=end==K;
      loadDataflowA(p,in,K,ab,ad);
      if(!terminal)ddr.startSweep(end);
      for(int ng=0;ng<N;ng+=160){
        const int cols=std::min(160,N-ng),count=(cols+31)/32;
        ddr.reusable();clearDataflowContexts(p,count);
        if(ab)for(int ctx=0;ctx<count;ctx++){
          const unsigned tile=ng/32+ctx;ddr.beginRead(job,17,tile,ab);
          for(unsigned beat=0;beat<256;beat++){
          ddr.readBeat(job,17,tile,ab,ddr.address(tile,beat),beat);
          for(unsigned j=0;j<16;j++)physicalFlat(p.accum[ctx],beat*16+j)=fp(ddr.payload[j]);
          ddr.consumed();
          }
          ddr.reusable();
        }
        computeDataflowTile(p,w,K,N,ng,cols,ab,ad,ab);
        for(int ctx=0;ctx<count;ctx++){
          captureDataflow(p,ctx);const unsigned tile=ng/32+ctx;
          if(!terminal){
            ddr.beginWrite(job,17,tile,end);
            for(unsigned beat=0;beat<256;beat++){
              for(unsigned j=0;j<16;j++){
                float v=physicalFlat(p.finalValue,beat*16+j);need(std::isfinite(v),"nonfinite prefix save");ddr.payload[j]=bits(v);
              }
              ddr.writeBeat(job,17,tile,end,ddr.address(tile,beat),beat);
            }
            ddr.acknowledge(job,17,tile,end,true);ddr.reusable();
          }else{
            publication.begin(end,tile,tokens*std::min(32,cols-ctx*32));unsigned written=0;
            for(int m=0;m<int(tokens);m++)for(int n=0;n<32&&ctx*32+n<cols;n++){
              const float v=p.finalValue[(n/16)*4+m/32][n%16][m%32];
              need(std::isfinite(v),"nonfinite down terminal accumulator");
              const int column=ng+ctx*32+n;const float emitted=bias>=0?add(v,get(bias,column)):v;
              need(std::isfinite(emitted),"nonfinite down terminal bias");const size_t ix=size_t(m)*N+column;
              need(bits(get(out,ix))==0x7fc00001u,"duplicate down final output");put(out,ix,emitted);publication.wrote(job,tile,written++);p.outValues++;
            }
            publication.ack(job,tile,true);
          }
          p.finalCount=0;
        }
      }
      if(!terminal)ddr.finishSweep();
    }
    publication.publish();downPublished=publication.published;
    prefixReadBytes=ddr.readBytes;prefixWriteBytes=ddr.writeBytes;
    need(p.aValues==uint64_t(tokens)*K&&p.wValues==uint64_t(K)*N&&p.outValues==uint64_t(tokens)*N,"down transport counts");
    const uint64_t expected=uint64_t((K+chunk-1)/chunk-1)*((N+31)/32)*16384;
    need(ddr.readBytes==expected&&ddr.writeBytes==expected,"down prefix byte accounting");
    need(p.issues==uint64_t(K)*((N+31)/32)&&p.metaCount==0&&p.fifoCount==0&&p.finalCount==0,"down issue/drain accounting");
    std::cout<<"DATAFLOW_DOWN m="<<tokens<<" k="<<K<<" n="<<N<<" chunk="<<chunk
      <<" a_values="<<p.aValues<<" w_values="<<p.wValues<<" prefix_read_bytes="<<ddr.readBytes
      <<" prefix_write_bytes="<<ddr.writeBytes<<" prefix_acks="<<ddr.ackCount<<" final_acks="<<publication.acked
      <<" issues="<<p.issues<<" published="<<downPublished<<std::endl;
  }
  void consumeFfnTiles(DataflowPhysical& p,int ng,int cols,uint64_t out,int width){
    p.beginTile(2,ng,cols,tokens);
    for(int m=0;m<int(tokens);m++)for(int n=0;n<cols;n++){
      // Exact original SiLU recipe, with only operand storage changed.
      float g=p.getTile(0,ng,m,n),e=expneg(g),sig=1.0f/add(1.0f,e);
      sig=mul(sig,std::signbit(g)?e:1.0f);
      p.putTile(2,ng,m,n,mul(mul(sig,g),p.getTile(1,ng,m,n)));
    }
    p.sealTile(2,tokens);p.releaseTile(0,tokens);p.releaseTile(1,tokens);
    // Serial SRAM read -> genuine act DDR write. No gate/up DDR operands exist.
    const uint64_t job=allocateJobGeneration();Publication tileOutput(1,1,job);tileOutput.begin(1,0,tokens*cols);
    for(int m=0;m<int(tokens);m++)for(int n=0;n<cols;n++){
      const size_t i=size_t(m)*width+ng+n;
      need(bits(get(out,i))==0x7fc00001u,"duplicate act output");put(out,i,p.getTile(2,ng,m,n));tileOutput.wrote(job,0,m*cols+n);ffnActValues++;
    }
    tileOutput.ack(job,0,true);tileOutput.publish();p.releaseTile(2,tokens);
  }
  void tiledFFN(){
    need(H<=1536&&H%16==0&&F>0&&F%16==0&&tokens%16==0,"FFN retained input capacity");
    auto storage=std::make_unique<DataflowPhysical>();auto& p=*storage;
    loadDataflowA(p,OFF_N1,H,0,H);
    for(int ng=0;ng<F;ng+=160){
      const int cols=std::min(160,F-ng),count=(cols+31)/32;
      for(int slot=0;slot<2;slot++){
        p.beginTile(slot,ng,cols,tokens);clearDataflowContexts(p,count);
        computeDataflowTile(p,slot?OFF_WU:OFF_WG,H,F,ng,cols,0,H,0);
        for(int ctx=0;ctx<count;ctx++){
          captureDataflow(p,ctx);
          for(int m=0;m<int(tokens);m++)for(int n=0;n<32&&ctx*32+n<cols;n++){
            const float v=p.finalValue[(n/16)*4+m/32][n%16][m%32];
            p.putTile(slot,ng,m,ctx*32+n,v);observe(slot,size_t(m)*F+ng+ctx*32+n,v);
          }
          p.finalCount=0;
        }
        p.sealTile(slot,tokens);
      }
      consumeFfnTiles(p,ng,cols,OFF_ACT,F);
    }
    ffnInputValues=p.aValues;ffnWeightValues=p.wValues;
    for(int slot=0;slot<3;slot++){
      need(p.tileStores[slot]==uint64_t(tokens)*F&&p.tileReads[slot]==uint64_t(tokens)*F&&!p.tileTags[slot].live,"FFN complete physical store/read accounting");
      ffnTileReadBytes+=p.tileReads[slot]*4;ffnTileWriteBytes+=p.tileStores[slot]*4;
    }
    need(p.aValues==uint64_t(tokens)*H&&p.wValues==uint64_t(2)*H*F&&ffnActValues==uint64_t(tokens)*F,"FFN external transport counts");
    std::cout<<"DATAFLOW_FFN m="<<tokens<<" k="<<H<<" n="<<F<<" input_values="<<p.aValues
      <<" weight_values="<<p.wValues<<" act_values="<<ffnActValues<<" tile_read_bytes="<<ffnTileReadBytes
      <<" tile_write_bytes="<<ffnTileWriteBytes<<" gate_up_arithmetic_ddr_reads=0 a_reserved_bytes=638976 b_bytes=81920"<<std::endl;
  }
