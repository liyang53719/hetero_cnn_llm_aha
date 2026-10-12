  static void reference_qkv_pair_dot16(const float* activation,const float* weights,
      int K,int N,int column,const int* blocks,size_t count,float* sums){
    need(K>0 && N>=16 && N%16==0 && column>=0 && column+16<=N,
         "QKV reference dot shape");
    int covered=0;
    for(size_t block=0;block<count;block++){
      need(blocks[block]>0 && blocks[block]%2==0 && blocks[block]<=K-covered,
           "QKV reference even block coverage");
      covered+=blocks[block];
    }
    need(count==2 && covered==K,"QKV reference requires two explicit complete blocks");
    int begin=0;
    for(size_t block=0;block<count;block++){
      float partial[16]={};
      for(int issue=0;issue<blocks[block];issue++){
        const int k=begin+(issue^1);
        const float* row=weights+size_t(k)*N+column;
        for(int lane=0;lane<16;lane++)
          partial[lane]=std::fma(activation[k],bf(row[lane]),partial[lane]);
      }
      for(int lane=0;lane<16;lane++)
        sums[lane]=block==0?partial[lane]:add(partial[lane],sums[lane]);
      begin+=blocks[block];
    }
  }
