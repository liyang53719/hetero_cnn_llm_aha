// Test-only AXI burst service. No numerical operators or oracle injection.
 void stepBurst(){
   d.clock=0;d.io_completion_ready=random()%4!=0;
   d.io_axi_ar_ready=!pending.valid&&!aw.valid&&!w.valid&&random()%4!=0;
   d.io_axi_aw_ready=!pending.valid&&!aw.valid&&random()%3!=0;d.io_axi_w_ready=!pending.valid&&collectedWrites.size()<16&&random()%4!=0;
   d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
   d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=pending.remaining==1;d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=pending.error?2:0;
   for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];d.eval();
   bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
   bool ack=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready),cf=d.io_completion_valid&&d.io_completion_ready;
   Beat a,b,c;
   if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.id=d.io_axi_ar_bits_id;c.total=c.remaining=d.io_axi_ar_bits_len+1;
     check(c.total<=OWNER_WEIGHT_READ_BEATS&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&((c.address&4095)+64*c.total)<=4096,"bad AR");
     if(c.total>1){bool allowed=false;for(const auto&t:ALLOCATIONS){std::string n=t.name;const auto k=n.substr(n.size()-std::min(size_t(2),n.size()));
       bool matrix=k=="wq"||k=="wk"||k=="wv"||k=="wo"||k=="wg"||k=="wu"||k=="wd";
       if(((matrix&&t.readonly)||(OWNER_PIPELINED&&!t.virtualValue))&&c.address>=t.address&&c.address+64*c.total<=t.address+4*t.words)allowed=true;}
       check(allowed,"burst escaped allowed tensor extent");}
     if(arHeld)check(eq(c,heldAr),"AR unstable");heldAr=c;arHeld=!ar;}else check(!arHeld,"AR withdrawn");
   if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.id=d.io_axi_aw_bits_id;a.total=a.remaining=d.io_axi_aw_bits_len+1;check(a.total<=16&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1&&((a.address&1023)+64*a.total)<=1024,"bad AW");if(awHeld)check(eq(a,heldAw),"AW unstable");heldAw=a;awHeld=!af;}else check(!awHeld,"AW withdrawn");
   if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;for(unsigned i=0;i<16;i++)b.data[i]=d.io_axi_w_bits_data[i];b.last=d.io_axi_w_bits_last;if(wHeld)check(eq(b,heldW),"W unstable");heldW=b;wHeld=!wf;}else check(!wHeld,"W withdrawn");
   if(!running)check(!a.valid&&!b.valid&&!c.valid,"DUT ran without Host launch");
   stalls+=(d.io_axi_ar_valid&&!ar)+(d.io_axi_aw_valid&&!af)+(d.io_axi_w_valid&&!wf);if(pending.valid&&pending.delay)delays++;
   if(af){aw=a;writeBursts++;}if(wf){w=b;collectedWrites.push_back(b);}Beat next;
   if(aw.valid&&collectedWrites.size()==aw.total){
     check(!pending.valid&&!ar,"AXI overlap");next=w;next.address=aw.address;next.id=aw.id;next.total=next.remaining=aw.total;
     for(unsigned i=0;i<aw.total;i++){check(collectedWrites[i].last==(i+1==aw.total),"bad WLAST");collectedWrites[i].address=aw.address+64*i;checkWrite(collectedWrites[i]);}
     committingWrites=collectedWrites;collectedWrites.clear();aw={};w={};writes+=next.total;
   }
   else if(ar){check(!pending.valid,"overlap AR");next=c;readBursts++;reads+=c.total;readBeats[d.io_pc]+=c.total;if(next.address<META_LIMIT){check(c.total==1,"metadata burst forbidden");metadata++;}}
   if(next.valid){check(next.address>=BASE&&next.address+64<=LIMIT&&(next.address&63)==0,"AXI bounds/alignment");next.delay=1+random()%5;if(next.write)check(next.address+64*next.total<=LIMIT,"write extent");else{checkRead(next.address);for(unsigned i=0;i<16;i++)next.data[i]=mem[pos(next.address)+i];}
     maybeFault(next);
   }
   if(d.io_completion_valid){check(!pending.valid&&!aw.valid&&!w.valid,"completion before memory drained");uint64_t word=d.io_completion_bits;unsigned stat=(word>>32)&255,owner=(word>>29)&7,pc=word&((1u<<29)-1);
     if(stat==0){check(pc==successful && (word>>40)==pc+1,"completion identity");unsigned localPc=pc%21;unsigned expected=(localPc==1||localPc==4||localPc==7||localPc==10||localPc==12||localPc==13||localPc==16||localPc==17||localPc==19)?2:(localPc==9?4:3);check(owner==expected,"wrong owner");}
     if(cf){completions++;if(stat==0){compare(pc);std::cout<<"OWNER_COMPLETION pc="<<pc<<" owner="<<owner<<" signal="<<(word>>40)<<" write_ack_bytes="<<writeBytes[pc]<<" cycle="<<cycles<<std::endl;successful++;}else{check(errorPc>=0&&int(pc)==errorPc,"unexpected completion error pc="+std::to_string(pc)+" status="+std::to_string(stat));std::cout<<"EXPECTED_ERROR pc="<<pc<<" status="<<stat<<std::endl;}}
   }
   d.clock=1;d.eval();cycles++;
   if(ack){if(pending.write){ackWrites+=pending.total;if(!pending.error){for(const auto& beat:committingWrites)for(unsigned i=0;i<16;i++){mem[pos(beat.address)+i]=beat.data[i];initialized[pos(beat.address)+i]=1;}writeBytes[d.io_pc]+=64*pending.total;}committingWrites.clear();}else ackReads++;
     if(!pending.write&&pending.remaining>1){
       pending.address+=64;pending.remaining--;pending.error=false;pending.delay=1+random()%5;
       checkRead(pending.address);for(unsigned i=0;i<16;i++)pending.data[i]=mem[pos(pending.address)+i];maybeFault(pending);
     }else pending={};}
   if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
 }
