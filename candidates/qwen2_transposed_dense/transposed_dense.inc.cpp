  // MODEL ONLY. Physical coordinates are slice, weight-row, activation-column.
  // Calls the same strict host fma as v0, with its two finite operands swapped.
  void transposed(uint64_t in,uint64_t w,uint64_t out,int K,int N,int64_t bias,
                  bool rmw,int aChunk=2560) {
    need(tokens>0&&tokens<=128&&tokens%16==0&&K>0&&K%16==0&&N>0&&N%16==0,
         "transposed shape");
    need(aChunk>0&&aChunk<=2752&&aChunk%16==0,"activation chunk");
    struct Physical {
      uint16_t a[16][1376][16], b[16][160][16];
      float accum[5][8][16][32], result[2][8][16][32], finalValue[8][16][32];
      // Actual one-beat staging, not a second tile/accumulator payload cache.
      uint16_t held[16];
      // Host bookkeeping for the eight-entry capacity; not a bit-level ABI or
      // protocol/backpressure proof of the production context/last/finish/emit.
      struct Metadata { int context; bool live; } metadata[8]{};
      unsigned metaCount=0,fifoCount=0,finalCount=0;
      unsigned contextPeak=0,metaPeak=0,fifoPeak=0,finalPeak=0;
      uint64_t aValues=0,wValues=0,issues=0,captures=0,outValues=0;
      uint64_t aReadWords=0,aWriteWords=0,refillPhases=0,swappedFmas=0;
      Physical() {
        for(auto& bank:a)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
        for(auto& bank:b)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
      }
      uint16_t& cell(int m,int k) {
        int mt=m/16,bank=(k%16)^mt,word=(k/16)*8+mt,lane=m%16;
        need(m>=0&&m<128&&k>=0&&k<2752&&bank<16&&word<1376,"A address");
        return a[bank][word][lane];
      }
      uint16_t& weight(int half,int depth,int n) {
        need(half>=0&&half<2&&depth>=0&&depth<128&&n>=0&&n<160,"B address");
        const int linear=half*1280+depth*10+n/16;
        return b[linear%16][linear/16][n%16];
      }
      float value(uint16_t x) {
        need((x&0x7f80)!=0x7f80,"uninitialized/nonfinite operand");
        return fp(uint32_t(x)<<16);
      }
    };
    static_assert(sizeof(Physical::a)==704512&&sizeof(Physical::b)==81920,"existing 688/80 KiB scratch");
    static_assert(sizeof(Physical::accum)==81920&&sizeof(Physical::result)==32768&&
                  sizeof(Physical::finalValue)==16384,"fixed register payloads");
    auto physical=std::make_unique<Physical>();auto& p=*physical;
    const bool full=K<=aChunk;
    auto loadA=[&](int base,int depth) {
      // FP32 token-major DDR: every beat contains one row and 16 consecutive K.
      // Native BF16 ingress is separately counted in the Python port proof.
      for(unsigned m=0;m<tokens;m++)for(int d=0;d<depth;d+=16) {
        for(int j=0;j<16;j++) {
          const float source=get(in,size_t(m)*K+base+d+j),converted=bf(source);
          need(std::isfinite(source)&&std::isfinite(converted),"nonfinite A conversion");
          p.held[j]=uint16_t(bits(converted)>>16);p.aValues++;
        }
        const int word=(d/16)*8+m/16,lane=m%16;
        if(rmw) {
          // Read phase: all 16 independent 1R ports, same word address.
          // This local array represents their synchronous output wires during
          // the immediately following write phase, NOT a persistent buffer.
          uint16_t response[16][16];
          for(int bank=0;bank<16;bank++)for(int l=0;l<16;l++)response[bank][l]=p.a[bank][word][l];
          p.aReadWords+=16;
          // First row-lane of each M16 tile initializes the full destination
          // word. Never rely on power-up SRAM bits or old-owner validity.
          if(lane==0)for(auto& wordResponse:response)for(auto& x:wordResponse)x=0;
          // Write phase consumes that response without a stall. A real stalled
          // implementation needs an additional 4096-bit response-hold register.
          for(int bank=0;bank<16;bank++) {
            response[bank][lane]=p.held[bank^(m/16)];
            for(int l=0;l<16;l++)p.a[bank][word][l]=response[bank][l];
          }
          p.refillPhases+=3; // accept+hold, synchronous read, merged full-word write
        } else {
          for(int j=0;j<16;j++)p.cell(m,d+j)=p.held[j];
          p.refillPhases+=2; // accept+hold, sixteen masked 16-bit writes
        }
        p.aWriteWords+=16;
      }
      // Check every payload after a complete refill, including preserved lanes.
      for(unsigned m=0;m<tokens;m++)for(int d=0;d<depth;d++)
        need(bits(p.value(p.cell(m,d)))==bits(bf(get(in,size_t(m)*K+base+d))),"scatter/RMW corruption");
    };
    if(full)loadA(0,K);
    for(int ng=0;ng<N;ng+=160) {
      const int columns=std::min(160,N-ng),count=(columns+31)/32;
      p.contextPeak=std::max(p.contextPeak,unsigned(count));
      need(p.metaCount==0&&p.fifoCount==0&&p.finalCount==0,"reuse before drain");
      for(int ctx=0;ctx<count;ctx++)for(auto& slice:p.accum[ctx])for(auto& row:slice)for(auto& x:row)x=0.0f;
      // All five contexts retain the exact prefix across *every* A/B refill.
      // The conservative model never overlaps loading and matrix issue.
      for(int ab=0;ab<K;ab+=aChunk) {
        const int ad=std::min(aChunk,K-ab);
        if(!full)loadA(ab,ad);
        for(int kb=ab;kb<ab+ad;kb+=128) {
          const int depth=std::min(128,ab+ad-kb),half=(kb/128)%2;
          for(int d=0;d<depth;d++)for(int n=0;n<columns;n++) {
            const float v=get(w,size_t(kb+d)*N+ng+n);
            need(std::isfinite(v)&&bits(v)==bits(bf(v)),"weight outside exact finite BF16 domain");
            p.weight(half,d,n)=uint16_t(bits(v)>>16);p.wValues++;
          }
          for(int d=0;d<depth;d++)for(int ctx=0;ctx<count;ctx++) {
            const int k=kb+d;
            need(p.metaCount==0,"serial metadata occupancy");
            p.metadata[0]={ctx,true};p.metaCount=1;p.metaPeak=1;
            for(int slice=0;slice<8;slice++)for(int r=0;r<16;r++)for(int c=0;c<32;c++) {
              const int n=ctx*32+(slice/4)*16+r,m=(slice%4)*32+c;
              const float av=m<int(tokens)?p.value(p.cell(m,full?k:k-ab)):0.0f;
              const float wv=n<columns?p.value(p.weight(half,d,n)):0.0f;
              // Finite-domain multiplication is symmetric, but order of K,
              // +0 initialization, retained FP32 prefix and bias are unchanged.
              p.accum[ctx][slice][r][c]=std::fma(wv,av,p.accum[ctx][slice][r][c]);
              p.swappedFmas++;
            }
            p.metadata[0].live=false;p.metaCount=0;p.issues++;
          }
        }
      }
      for(int ctx=0;ctx<count;ctx++) {
        need(p.fifoCount==0&&p.finalCount==0,"result storage overflow");
        std::memcpy(p.result[0],p.accum[ctx],sizeof(p.accum[ctx]));p.fifoCount=1;p.fifoPeak=1;
        std::memcpy(p.finalValue,p.result[0],sizeof(p.finalValue));p.fifoCount=0;p.finalCount=1;p.finalPeak=1;
        for(int m=0;m<int(tokens);m++)for(int j=0;j<32&&ctx*32+j<columns;j++) {
          const int slice=(j/16)*4+m/32,r=j%16,c=m%32,n=ng+ctx*32+j;
          const float v=p.finalValue[slice][r][c];
          need(std::isfinite(v),"nonfinite terminal accumulator");
          const float emitted=bias>=0?add(v,get(bias,n)):v;
          need(std::isfinite(emitted),"nonfinite terminal bias/output");
          const size_t ix=size_t(m)*N+n;
          need(bits(get(out,ix))==0x7fc00001u,"duplicate final output");
          put(out,ix,emitted);p.outValues++;
        }
        p.captures++;p.finalCount=0;
      }
    }
    need(p.aValues==uint64_t(tokens)*K*(full?1:(N+159)/160)&&p.wValues==uint64_t(K)*N&&
         p.outValues==uint64_t(tokens)*N,"external transport counts");
    need(p.issues==uint64_t(K)*((N+31)/32)&&p.captures==uint64_t((N+31)/32),"issue/capture counts");
    need(p.contextPeak<=5&&p.metaPeak<=8&&p.fifoPeak<=2&&p.finalPeak==1&&
         p.metaCount==0&&p.fifoCount==0&&p.finalCount==0,"fixed storage lifetime");
    std::cout<<"TRANSPOSED_CASE m="<<tokens<<" k="<<K<<" n="<<N<<" rmw="<<rmw
      <<" a_chunk="<<aChunk<<" a_values="<<p.aValues<<" w_values="<<p.wValues
      <<" issues="<<p.issues<<" swapped_fmas="<<p.swappedFmas<<" captures="<<p.captures
      <<" a_read_words="<<p.aReadWords<<" a_write_words="<<p.aWriteWords
      <<" refill_phases="<<p.refillPhases<<" context_peak="<<p.contextPeak
      <<" meta_peak="<<p.metaPeak<<" fifo_peak="<<p.fifoPeak<<" final_peak="<<p.finalPeak<<std::endl;
  }
