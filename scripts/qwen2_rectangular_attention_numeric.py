"""Numerical storage implementation for the opt-in resident software runner.

No executable hardware, new arithmetic policy, or timing estimate lives here.
Only the fixed SRAM arrays and already budgeted Matrix registers hold panels.
"""

CPP_SUPPORT = r'''
struct RectangularAttentionStorage {
  // The resident Dense owner has returned before this owner is constructed.
  // These are the SAME bank capacities, not additional simultaneously live SRAM.
  uint16_t ac[16][1024][16], b[16][512][16];
  float accumulator[5][16][256], resultFIFO[2][16][256], finalValue[16][256];
  struct Object {int base, rows, columns, bytes, rowWords; bool inB;};
  Object object[6]; // q, k, v, score, prob, partial_or_pv_capture
  struct Tag {bool live=false; int context=-1, index=-1, stripe=-1; bool emit=false;};
  Tag metadata[8], fifoTag[2]; // tags only: no numerical payload
  bool contextLive[5]={}, finalLive=false;
  int partialStripe[5]={-1,-1,-1,-1,-1}, scoreStripe=-1;
  unsigned capturedRows=0, fifoHead=0, fifoCount=0, pending=0, liveContexts=0;
  unsigned contextHigh=0, metadataHigh=0, fifoHigh=0, partialHigh=0, captureHigh=0;
  int columns=0, phase=-1, head=-1, kv=-1, qbase=-1, kbase=-1, usedAWords=0;
  uint64_t reads[6]={}, writes[6]={}; // scalar physical-memory element accesses
  uint64_t externalQ=0, externalKV=0, externalD=0, poisonWrites=0;
  uint64_t issues=0, returns=0, captures=0, groups=0, useful=0, executed=0;
  uint64_t qkIssues=0, pvIssues=0, partialStores=0, stripeAdds=0, rowCaptures=0;
  uint64_t gatherWords=0, scalarAdds=0, scalarMuls=0, scalarExps=0, scalarDivs=0;
  static float poison(){return fp(0x7fc00001u);}
  explicit RectangularAttentionStorage(unsigned tokens){
    need(tokens>0 && tokens<=128,"rectangular Attention token capacity");
    for(auto& bank:ac)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
    for(auto& bank:b)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
    for(auto& ctx:accumulator)for(auto& row:ctx)for(auto& x:row)x=poison();
    for(auto& entry:resultFIFO)for(auto& row:entry)for(auto& x:row)x=poison();
    for(auto& row:finalValue)for(auto& x:row)x=poison();
    int base=0;
    for(int i=0;i<5;i++){
      const int rows=(i==1||i==2)?int(tokens):16;
      const int cols=i<3?128:int(tokens), bytes=i<3?2:4;
      const int rowWords=(cols*bytes+31)/32;
      object[i]={base,rows,cols,bytes,rowWords,false};
      base+=(rows+15)/16*rowWords;
    }
    object[5]={0,80,256,4,32,true};usedAWords=base;
    need(base<=1024 && 5*32<=512,"rectangular Attention SRAM partition overflow");
  }
  uint16_t* cell(int id,int row,int col){
    need(id>=0 && id<6,"rectangular scratch object");const auto& o=object[id];
    need(row>=0 && row<o.rows && col>=0 && col<o.columns,"rectangular scratch tensor bounds");
    const int bank=row%16, word=o.base+(row/16)*o.rowWords+col*o.bytes/32;
    const int lane=(col*o.bytes%32)/2, depth=o.inB?512:1024;
    const size_t address=(size_t(bank)*depth+word)*32+lane*2;
    need(word>=0 && word<depth && address+o.bytes<=size_t(16*depth*32) &&
         (o.bytes!=4 || address%4==0),"rectangular physical address/alignment");
    // This unique bank/word/lane index is the numerical storage identity.
    return o.inB?&b[bank][word][lane]:&ac[bank][word][lane];
  }
  void put16(int id,int row,int col,float value){
    need(id<3 && std::isfinite(value) && bits(value)==bits(bf(value)),"rectangular nonfinite BF16 load");
    *cell(id,row,col)=uint16_t(bits(value)>>16);writes[id]++;
  }
  float get16(int id,int row,int col){
    need(id<3,"rectangular BF16 object");float value=fp(uint32_t(*cell(id,row,col))<<16);
    need(std::isfinite(value),"rectangular uninitialized BF16 operand");reads[id]++;return value;
  }
  void put32(int id,int row,int col,float value){
    need(id>=3,"rectangular FP32 object");auto* p=cell(id,row,col);uint32_t u=bits(value);
    p[0]=uint16_t(u);p[1]=uint16_t(u>>16);writes[id]++;
  }
  float get32(int id,int row,int col){
    need(id>=3,"rectangular FP32 object");auto* p=cell(id,row,col);
    float value=fp(uint32_t(p[0])|(uint32_t(p[1])<<16));
    need(std::isfinite(value),"rectangular uninitialized or nonfinite FP32 operand");reads[id]++;return value;
  }
  void poisonObject(int id){
    const auto& o=object[id];for(int row=0;row<o.rows;row++)for(int col=0;col<o.columns;col++){
      auto* p=cell(id,row,col);p[0]=1;p[1]=0x7fc0;poisonWrites++;
    }
  }
  void begin(int kind,int h,int kh,int qb,int kb,int cols){
    need(phase==-1 && pending==0 && liveContexts==0 && fifoCount==0 && !finalLive,
         "rectangular group reuse before result drain");
    for(int tag:partialStripe)need(tag==-1,"rectangular partial reuse before ordered reduction");
    need(capturedRows==0,"rectangular capture reuse before output drain");
    need(kind>=0 && kind<=1 && cols>0 && cols<=256,"rectangular group shape");
    phase=kind;head=h;kv=kh;qbase=qb;kbase=kb;columns=cols;groups++;
  }
  void start(int context){
    need(phase>=0 && context>=0 && context<5 && !contextLive[context],"rectangular context ownership");
    contextLive[context]=true;liveContexts++;contextHigh=std::max(contextHigh,liveContexts);
    for(auto& row:accumulator[context])for(int col=0;col<columns;col++)row[col]=0.0f;
  }
  void issue(int context,int index,int stripe,bool emit){
    need(context>=0 && context<5 && contextLive[context] && !metadata[context].live && pending<8,
         "rectangular issue before return or metadata overflow");
    metadata[context]={true,context,index,stripe,emit};pending++;metadataHigh=std::max(metadataHigh,pending);issues++;
  }
  void returned(int context,int index,int stripe,bool emit){
    need(context>=0 && context<5,"rectangular return context");auto& tag=metadata[context];
    need(tag.live && tag.context==context && tag.index==index && tag.stripe==stripe && tag.emit==emit,
         "rectangular stale return identity");
    tag.live=false;pending--;returns++;
    if(emit){
      need(fifoCount<2 && !finalLive,"rectangular result overflow or undrained final value");
      const unsigned tail=(fifoHead+fifoCount)%2;fifoTag[tail]={true,context,index,stripe,true};
      for(int row=0;row<16;row++)for(int col=0;col<columns;col++)resultFIFO[tail][row][col]=accumulator[context][row][col];
      fifoCount++;fifoHigh=std::max(fifoHigh,fifoCount);
    }
  }
  void drain(int context,int index,int stripe){
    need(fifoCount>0 && !finalLive,"rectangular result drain without return");auto& tag=fifoTag[fifoHead];
    need(tag.live && tag.context==context && tag.index==index && tag.stripe==stripe,"rectangular FIFO identity");
    for(int row=0;row<16;row++)for(int col=0;col<columns;col++){
      finalValue[row][col]=resultFIFO[fifoHead][row][col];resultFIFO[fifoHead][row][col]=poison();
    }
    tag.live=false;fifoHead=(fifoHead+1)%2;fifoCount--;finalLive=true;captures++;
  }
  void releaseFinal(){
    need(finalLive,"rectangular final value duplicate release");
    for(auto& row:finalValue)for(int col=0;col<columns;col++)row[col]=poison();finalLive=false;
  }
  void end(){
    need(phase>=0 && pending==0 && fifoCount==0 && !finalLive,"rectangular group ends before drain");
    for(int tag:partialStripe)need(tag==-1,"rectangular group ends before partial reduction");
    for(int ctx=0;ctx<5;ctx++)if(contextLive[ctx]){
      for(auto& row:accumulator[ctx])for(int col=0;col<columns;col++)row[col]=poison();contextLive[ctx]=false;
    }
    liveContexts=0;phase=-1;
  }
};
static_assert(sizeof(RectangularAttentionStorage::ac)==524288 && sizeof(RectangularAttentionStorage::b)==262144,
              "rectangular Attention scratch must be exactly 768 KiB");
static_assert(sizeof(RectangularAttentionStorage::accumulator)==5*16*256*4 &&
              sizeof(RectangularAttentionStorage::resultFIFO)==2*16*256*4 &&
              sizeof(RectangularAttentionStorage::finalValue)==16*256*4,
              "rectangular Attention register capacities changed");
'''

ATTENTION_BODY = r'''
    need(tokens>0 && tokens<=128 && HD>=32 && HD<=128 && HD%32==0 &&
         HEADS>0 && HEADS<=12 && KVHEADS>0 && HEADS%KVHEADS==0,
         "rectangular Attention shape outside bounded storage");
    auto storage=std::make_unique<RectangularAttentionStorage>(tokens);auto& p=*storage;
    const int headsPerKV=HEADS/KVHEADS;
    for(int kh=0;kh<KVHEADS;kh++){
      // Materialize actual outputs of this model's Dense/RoPE stages.
      for(unsigned key=0;key<tokens;key++)for(int j=0;j<HD;j++){
        p.put16(1,key,j,bf(get(OFF_K,size_t(key)*KV+kh*HD+j)));
        p.put16(2,key,j,bf(get(OFF_V,size_t(key)*KV+kh*HD+j)));p.externalKV+=2;
      }
      for(int h=kh*headsPerKV;h<(kh+1)*headsPerKV;h++)for(unsigned qb=0;qb<tokens;qb+=16){
        const int rows=std::min(16,int(tokens-qb)), keys=qb+rows;
        p.poisonObject(3);p.poisonObject(4);p.scoreStripe=-1;
        for(int row=0;row<rows;row++)for(int j=0;j<HD;j++){
          p.put16(0,row,j,bf(get(OFF_Q,size_t(qb+row)*H+h*HD+j)));p.externalQ++;
        }
        // Padded Q rows, keys beyond tokens, and inactive causal lanes are
        // distinct. Padded inputs use +0 without reading poison; future real
        // keys execute, but can never enter the scalar reduction/softmax.
        for(int kb=0;kb<keys;kb+=256){
          const int cols=((std::min(256,keys-kb)+31)/32)*32;
          for(int sb=0;sb<16;sb+=5){
            const int count=std::min(5,16-sb);p.begin(0,h,kh,qb,kb,cols);
            for(int ctx=0;ctx<count;ctx++)p.start(ctx);
            for(int step=0;step<HD/16;step++){
              const bool last=step==HD/16-1;
              for(int ctx=0;ctx<count;ctx++){
                const int stripe=sb+ctx,j=stripe+16*step;p.issue(ctx,j,stripe,last);
                for(int row=0;row<16;row++){
                  const float av=row<rows?p.get16(0,row,j):0.0f;
                  for(int col=0;col<cols;col++){
                    const float bv=kb+col<int(tokens)?p.get16(1,kb+col,j):0.0f;
                    p.accumulator[ctx][row][col]=std::fma(av,bv,p.accumulator[ctx][row][col]);
                    if(row<rows && kb+col<=int(qb)+row)p.useful++;
                  }
                }
                p.qkIssues++;p.executed+=uint64_t(16)*cols;
                p.gatherWords+=rows+std::min(cols,int(tokens)-kb);
              }
              for(int ctx=0;ctx<count;ctx++){
                const int stripe=sb+ctx,j=stripe+16*step;p.returned(ctx,j,stripe,last);
                if(last){
                  p.drain(ctx,j,stripe);need(p.partialStripe[ctx]==-1,"rectangular partial slot occupied");
                  for(int row=0;row<16;row++)for(int col=0;col<cols;col++){
                    const float value=p.finalValue[row][col];
                    if(row<rows && kb+col<=int(qb)+row)need(std::isfinite(value),"rectangular nonfinite causal QK partial");
                    p.put32(5,ctx*16+row,col,value);
                  }
                  p.partialStripe[ctx]=stripe;p.partialStores++;p.partialHigh=std::max(p.partialHigh,unsigned(ctx+1));
                  p.releaseFinal();
                }
              }
            }
            for(int ctx=0;ctx<count;ctx++){
              const int stripe=sb+ctx;
              need(p.partialStripe[ctx]==stripe && p.scoreStripe==stripe-1,"rectangular stripe reduction order/owner");
              for(int row=0;row<rows;row++)for(int col=0;kb+col<=int(qb)+row && col<cols;col++){
                const float prior=stripe==0?0.0f:p.get32(3,row,kb+col);
                const float value=add(prior,p.get32(5,ctx*16+row,col));
                need(std::isfinite(value),"rectangular nonfinite stripe reduction");p.put32(3,row,kb+col,value);
                p.stripeAdds++;p.scalarAdds++;
              }
              p.scoreStripe=stripe;p.partialStripe[ctx]=-1;
            }
            p.end();
          }
        }
        need(p.scoreStripe==15,"rectangular incomplete QK stripes");
        for(int row=0;row<rows;row++){
          float maximum=-INFINITY;
          for(int key=0;key<=int(qb)+row;key++){
            const float value=mul(p.get32(3,row,key),float(1.0/std::sqrt(double(HD))));
            need(std::isfinite(value),"rectangular nonfinite score");p.put32(3,row,key,value);maximum=std::max(maximum,value);p.scalarMuls++;
          }
          float sum=0;
          for(int key=0;key<=int(qb)+row;key++){
            const float value=expneg(add(p.get32(3,row,key),-maximum));
            p.put32(4,row,key,value);sum=add(sum,value);p.scalarAdds+=2;p.scalarExps++;
          }
          const float inv=1.0f/sum;need(std::isfinite(inv),"rectangular nonfinite reciprocal");p.scalarDivs++;
          for(int key=0;key<=int(qb)+row;key++){
            const float value=mul(p.get32(4,row,key),inv);
            need(std::isfinite(value),"rectangular nonfinite probability");p.put32(4,row,key,value);p.scalarMuls++;
          }
        }
        // B slot zero aliases PV capture only AFTER all QK partials drain.
        p.begin(1,h,kh,qb,0,HD);p.poisonObject(5);p.start(0);
        for(int key=0;key<keys;key++){
          const int finalRow=key-int(qb);const bool emit=finalRow>=0 && finalRow<rows;
          p.issue(0,key,-1,emit);int validRows=0;
          for(int row=0;row<16;row++){
            const bool valid=row<rows && key<=int(qb)+row;
            const float av=valid?bf(p.get32(4,row,key)):0.0f;validRows+=valid;
            for(int col=0;col<HD;col++){
              p.accumulator[0][row][col]=std::fma(av,p.get16(2,key,col),p.accumulator[0][row][col]);
              if(valid)p.useful++;
            }
          }
          p.pvIssues++;p.executed+=16*HD;p.gatherWords+=validRows+HD/16;p.returned(0,key,-1,emit);
          if(emit){
            p.drain(0,key,-1);need(!(p.capturedRows&(1u<<finalRow)),"rectangular duplicate causal row capture");
            for(int col=0;col<HD;col++){
              const float value=p.finalValue[finalRow][col];need(std::isfinite(value),"rectangular nonfinite PV capture");
              p.put32(5,finalRow,col,value);
            }
            p.capturedRows|=1u<<finalRow;p.captureHigh=std::max(p.captureHigh,unsigned(finalRow+1));p.rowCaptures++;p.releaseFinal();
          }
        }
        p.end();need(p.capturedRows==((1u<<rows)-1),"rectangular missing causal row capture");
        for(int row=0;row<rows;row++)for(int col=0;col<HD;col++){
          const size_t ix=size_t(qb+row)*H+h*HD+col;
          need(bits(get(OFF_ATT,ix))==0x7fc00001u,"rectangular output overwritten before capture drain");
          put(OFF_ATT,ix,p.get32(5,row,col));p.externalD++;
        }
        p.capturedRows=0;
      }
    }
    need(p.pending==0 && p.fifoCount==0 && !p.finalLive && p.liveContexts==0 && p.capturedRows==0,
         "rectangular final drain incomplete");
    std::cout<<"RESIDENT_ATTENTION tokens="<<tokens<<" heads="<<HEADS<<" kv_heads="<<KVHEADS<<" head_dim="<<HD
      <<" scratch_bytes="<<(sizeof(p.ac)+sizeof(p.b))<<" used_a_bytes="<<p.usedAWords*512<<" used_b_bytes="<<5*16384
      <<" contexts_peak="<<p.contextHigh<<" metadata_peak="<<p.metadataHigh<<" fifo_peak="<<p.fifoHigh<<" final_peak=1"
      <<" partial_slots_peak="<<p.partialHigh<<" captured_rows_peak="<<p.captureHigh
      <<" external_q_fp32_bytes="<<p.externalQ*4<<" external_kv_fp32_bytes="<<p.externalKV*4<<" external_d_fp32_bytes="<<p.externalD*4
      <<" qkv_bf16_store_bytes="<<(p.writes[0]+p.writes[1]+p.writes[2])*2
      <<" numeric_q_bf16_read_bytes="<<p.reads[0]*2<<" numeric_k_bf16_read_bytes="<<p.reads[1]*2<<" numeric_v_bf16_read_bytes="<<p.reads[2]*2
      <<" score_fp32_read_bytes="<<p.reads[3]*4<<" score_fp32_store_bytes="<<p.writes[3]*4
      <<" probability_fp32_read_bytes="<<p.reads[4]*4<<" probability_fp32_store_bytes="<<p.writes[4]*4
      <<" b_fp32_read_bytes="<<p.reads[5]*4<<" b_fp32_store_bytes="<<p.writes[5]*4
      <<" event_gather_bank_read_bytes="<<p.gatherWords*32
      <<" qk_wide_issues="<<p.qkIssues<<" pv_wide_issues="<<p.pvIssues<<" wide_issues="<<p.issues<<" matrix_returns="<<p.returns
      <<" useful_macs="<<p.useful<<" executed_macs="<<p.executed<<" groups="<<p.groups<<" result_captures="<<p.captures
      <<" partial_stores="<<p.partialStores<<" ordered_stripe_adds="<<p.stripeAdds<<" pv_row_captures="<<p.rowCaptures
      <<" scalar_add_requests="<<p.scalarAdds<<" scalar_mul_requests="<<p.scalarMuls<<" scalar_exp_requests="<<p.scalarExps<<" scalar_div_requests="<<p.scalarDivs
      <<" status=DIAGNOSTIC_NOT_ACCEPTED"<<std::endl;
'''


def expected(tokens, layout, attention_model):
    """Check executed counters, with public event geometry for padded columns."""
    h, kv, hd = layout['heads'], layout['kv_heads'], layout['head_dim']
    tiles = list(attention_model.qk_tiles(tokens))
    qtiles = len(tiles)
    pairs = h*tokens*(tokens+1)//2
    qk = h*qtiles*hd
    pv = h*sum(t['qbase']+t['rows'] for t in tiles)
    partial = h*sum(16*16*t['columns'] for t in tiles)
    scratch = attention_model.scratch_layout(tokens, 5)
    return dict(tokens=tokens, heads=h, kv_heads=kv, head_dim=hd,
        scratch_bytes=768*1024, used_a_bytes=scratch['used_a_bytes'], used_b_bytes=scratch['used_b_bytes'],
        contexts_peak=5, metadata_peak=5, fifo_peak=1, final_peak=1,
        partial_slots_peak=5, captured_rows_peak=min(16,tokens),
        external_q_fp32_bytes=h*tokens*hd*4, external_kv_fp32_bytes=2*kv*tokens*hd*4,
        external_d_fp32_bytes=h*tokens*hd*4, qkv_bf16_store_bytes=(h+2*kv)*tokens*hd*2,
        numeric_q_bf16_read_bytes=h*tokens*hd*2,
        numeric_k_bf16_read_bytes=h*sum(16*min(t['columns'],tokens)*hd*2 for t in tiles),
        numeric_v_bf16_read_bytes=pv*16*hd*2,
        score_fp32_read_bytes=pairs*17*4, score_fp32_store_bytes=pairs*17*4,
        probability_fp32_read_bytes=pairs*2*4, probability_fp32_store_bytes=pairs*2*4,
        b_fp32_read_bytes=(pairs*16+h*tokens*hd)*4,
        b_fp32_store_bytes=(partial+h*tokens*hd)*4,
        event_gather_bank_read_bytes=(h*sum((t['rows']+min(t['columns'],tokens))*hd for t in tiles)+pairs+pv*(hd//16))*32,
        qk_wide_issues=qk, pv_wide_issues=pv, wide_issues=qk+pv, matrix_returns=qk+pv,
        useful_macs=2*pairs*hd,
        executed_macs=h*sum(16*t['columns']*hd for t in tiles)+pv*16*hd,
        groups=h*qtiles*5, result_captures=h*qtiles*16+h*tokens,
        partial_stores=h*qtiles*16, ordered_stripe_adds=pairs*16, pv_row_captures=h*tokens,
        scalar_add_requests=pairs*18, scalar_mul_requests=pairs*2,
        scalar_exp_requests=pairs, scalar_div_requests=h*tokens, status='DIAGNOSTIC_NOT_ACCEPTED')
