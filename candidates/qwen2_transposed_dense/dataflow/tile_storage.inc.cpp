      // Three existing-A SRAM regions. Each slot is 160 words/bank = 81920 B.
      // Fixed reservation retains the complete M128xK1536 BF16 input in words
      // [0,768), regardless of the smaller synthetic shape used by small tests.
      bool tilePoisoned=false;
      void tileCheck(bool ok,const char* message){if(tilePoisoned||!ok){tilePoisoned=true;need(false,message);}}
      struct TileTag {int ng=-1,cols=0,rows=0; unsigned stored=0,read=0; bool live=false,complete=false;} tileTags[3];
      uint64_t tileStores[3]={},tileReads[3]={}; // observational counters only
      static unsigned tileWord(int slot,int m,int n){
        need(slot>=0&&slot<3&&m>=0&&m<128&&n>=0&&n<160,"FFN tile bounds");
        return 768+slot*160+(m/16)*20+n/8;
      }
      uint16_t* tileCell(int slot,int m,int n){return &a[m%16][tileWord(slot,m,n)][2*(n%8)];}
      void beginTile(int slot,int ng,int cols,unsigned tokens){
        tileCheck(slot>=0&&slot<3&&!tileTags[slot].live&&cols>0&&cols<=160&&tokens>0&&tokens<=128,"FFN tile early reuse");
        tileTags[slot]={ng,cols,int(tokens),0,0,true,false};
        for(int m=0;m<128;m++)for(int n=0;n<160;n++){
          auto* c=tileCell(slot,m,n);c[0]=1;c[1]=0x7fc0;
        }
      }
      void putTile(int slot,int ng,int m,int n,float value){
        tileCheck(slot>=0&&slot<3,"FFN slot bounds/poison");auto& t=tileTags[slot];
        tileCheck(t.live&&!t.complete&&t.ng==ng&&m>=0&&m<t.rows&&n>=0&&n<t.cols&&std::isfinite(value),"FFN tile producer identity/value");
        auto* c=tileCell(slot,m,n);tileCheck((uint32_t(c[0])|(uint32_t(c[1])<<16))==0x7fc00001u,"FFN duplicate physical producer write");
        const auto u=bits(value);c[0]=uint16_t(u);c[1]=uint16_t(u>>16);t.stored++;tileStores[slot]++;
      }
      void sealTile(int slot,unsigned tokens){
        tileCheck(slot>=0&&slot<3,"FFN slot bounds/poison");auto& t=tileTags[slot];tileCheck(t.live&&!t.complete&&tokens==unsigned(t.rows)&&t.stored==tokens*unsigned(t.cols),"FFN incomplete tile producer");t.complete=true;
      }
      float getTile(int slot,int ng,int m,int n){
        tileCheck(slot>=0&&slot<3,"FFN slot bounds/poison");auto& t=tileTags[slot];tileCheck(t.live&&t.complete&&t.ng==ng&&m>=0&&m<t.rows&&n>=0&&n<t.cols&&t.read==unsigned(m*t.cols+n),"FFN stale/unready tile consumer");
        const auto* c=tileCell(slot,m,n);const float v=fp(uint32_t(c[0])|(uint32_t(c[1])<<16));
        tileCheck(std::isfinite(v),"FFN unwritten physical SRAM read");t.read++;tileReads[slot]++;return v;
      }
      void releaseTile(int slot,unsigned tokens){
        tileCheck(slot>=0&&slot<3,"FFN slot bounds/poison");auto& t=tileTags[slot];tileCheck(t.live&&t.complete&&tokens==unsigned(t.rows)&&t.read==tokens*unsigned(t.cols),"FFN early release before consumer drain");t.live=false;
      }
