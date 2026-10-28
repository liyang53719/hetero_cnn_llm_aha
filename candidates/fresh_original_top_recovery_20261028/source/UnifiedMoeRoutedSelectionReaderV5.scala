// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE parent packet captured from the same retained allocator lease and
  * the real routedLoop.done.fire. Fields/geometry are not authority. The parent
  * owns region3 permissions, full transaction/epoch attribution and the complete
  * 4MiB routedDown lifetime. No Host address/commit Boolean enters this reader.
  */
class UnifiedMoeRoutedReadJobV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val metadataBase=UInt(64.W);val descriptorBase=UInt(64.W);val routedDown=UInt(64.W)
  val allocationBase=UInt(64.W);val allocationEnd=UInt(64.W)
  val firstOwnerSequence=UInt(32.W);val postnormPhysicalSequence=UInt(32.W)
  val routed=new HostMoeRoutedPhaseResultV5
  val token=UInt(32.W)
}
class UnifiedMoeSelectedDownRouteV5 extends Bundle {
  val expert=UInt(8.W);val groupRow=UInt(7.W);val weight=UInt(16.W)
  val output=UInt(64.W);val groupRows=UInt(8.W);val ownerSequence=UInt(32.W)
}
class UnifiedMoeRoutedSelectionV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val token=UInt(32.W)
  val routes=Vec(8,new UnifiedMoeSelectedDownRouteV5)
  val readIssued=UInt(4.W);val readReturned=UInt(4.W)
  val status=UInt(8.W);val drained=Bool()
}
object UnifiedMoeRoutedReadJobV5 {
  /** Caller must invoke from actual retained lease + clean actual done.fire.
    * This combinational constructor is not a grant or a second receipt source.
    */
  def fromActualRoutedRetirement(l:HostMoeRuntimePhaseLeaseV5,
      r:HostMoeRoutedPhaseResultV5,token:UInt):UnifiedMoeRoutedReadJobV5={
    val j=Wire(new UnifiedMoeRoutedReadJobV5)
    j.context:=l.context;j.allocationSequence:=l.allocationSequence
    j.metadataBase:=l.metadataBase;j.descriptorBase:=l.descriptorBase;j.routedDown:=l.routedDown
    j.allocationBase:=l.allocationBase;j.allocationEnd:=l.allocationEnd
    j.firstOwnerSequence:=l.firstOwnerSequence;j.postnormPhysicalSequence:=l.postnormPhysicalSequence
    j.routed:=r;j.token:=token;j
  }
}

/** Actual DDR map -> actual ACKed down-descriptor reads. Exactly 1 token-major
  * 64B map read and 8 descriptor reads produce 8 compact routed selections.
  * Selection is per TOKEN, not per output tile: the parent retains its actual
  * result.fire across all 64 hidden tiles before advancing the token. Thus the
  * source read bound is 9*M (1152 at M128), not 9*M*64. No claim that this
  * parent lifetime/whole-token scheduler has already been installed.
  * Does not invent the ninth/shared contribution or a sigmoid weight of 1.
  * Shared FFN/N1 gate completion must join separately before a nine-route job.
  * No Dense/Scalar/vector/rounder/selection/transport arbiter is instantiated.
  * New local storage: retained phase job, map512b + 8*135 selected bits = 199 bytes,
  * address/tag/sequence/control, held result metadata. Constant modulo 5 owner
  * validation is integer control logic, not a hidden new numeric ALU service.
  *
  * Public host cannot grant this private job. Old DDR slots are rejected by
  * txn/allocation/expert/version/full geometry; trusted writer provenance and
  * no intervening writes still require parent's actual allocator/DDR lifetime.
  * Full metadata equality does not protect against a malicious memory writer.
  */
class UnifiedMoeRoutedSelectionReaderV5 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new UnifiedMoeRoutedReadJobV5))
    val result=Decoupled(new UnifiedMoeRoutedSelectionV5)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val currentFault=Input(Bool())
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val idle::prepare::offer::waiting::report::locked::Nil=Enum(6)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeRoutedReadJobV5)
  val map=Reg(Vec(8,UInt(64.W)));val selected=Reg(Vec(8,new UnifiedMoeSelectedDownRouteV5))
  val index=Reg(UInt(4.W)) //0 map,1..8 selected expert descriptors
  val address=Reg(UInt(64.W));val tag=Reg(UInt(64.W));val sequence=RegInit(0.U(64.W))
  val issued=RegInit(0.U(4.W));val returned=RegInit(0.U(4.W))
  val outStatus=Reg(UInt(8.W));val outDrained=Reg(Bool())
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknown=io.response.valid && state=/=waiting
  when(unknown||io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.currentFault){poison:=true.B}
  val fault=poison||quarantine||unknown||io.memoryResetRequired||io.currentFault
  io.resetRequired:=fault;io.contextReserved:=state=/=idle||io.job.valid
  io.job.ready:=state===idle && !fault
  io.memory.valid:=state===offer // preserve already offered request through fault
  io.memory.bits:=0.U.asTypeOf(new MemoryRequest)
  io.memory.bits.address:=address;io.memory.bits.tag:=tag
  io.response.ready:=state===waiting && !quarantine && !io.memoryResetRequired
  io.result.valid:=state===report
  io.result.bits.context:=job.context;io.result.bits.allocationSequence:=job.allocationSequence
  io.result.bits.token:=job.token
  io.result.bits.routes:=Mux(outStatus===Status.Ok.U,selected,0.U.asTypeOf(selected))
  io.result.bits.readIssued:=issued;io.result.bits.readReturned:=returned
  io.result.bits.status:=outStatus;io.result.bits.drained:=outDrained
  val in=io.job.bits;val c=in.context;val r=in.routed
  val (p,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
  val ranges=Seq((in.metadataBase,16384L),(in.descriptorBase,16384L),(in.routedDown,4194304L))
  val geometry=ranges.map{case(b,n)=>b=/=0.U && b(5,0)===0.U && b>=in.allocationBase &&
    b.pad(96)+n.U<=in.allocationEnd.pad(96)}.reduce(_&&_)
  val disjoint=(for(i<-ranges.indices;j<-0 until i)yield
    !(ranges(i)._1.pad(96)<ranges(j)._1.pad(96)+ranges(j)._2.U &&
      ranges(j)._1.pad(96)<ranges(i)._1.pad(96)+ranges(i)._2.U)).reduce(_&&_)
  val owners=in.firstOwnerSequence>in.postnormPhysicalSequence &&
    in.firstOwnerSequence.pad(33)+1280.U<"hffffffff".U(33.W) &&
    r.nextOwnerSequence.pad(33)===in.firstOwnerSequence.pad(33)+1.U+r.groups.pad(33)*5.U
  val legal=known && p.asUInt===c.profile.asUInt && p.mlp===1.U && p.hidden===2048.U &&
    p.expertCount===256.U && p.expertsPerToken===8.U &&
    c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U &&
    HostCommandLaunchV4.known(c.host) && c.tokens>=1.U && c.tokens<=128.U &&
    in.token<c.tokens && in.allocationSequence=/=0.U &&
    r.transactionId===c.transactionId && r.allocationSequence===in.allocationSequence &&
    r.status===Status.Ok.U && r.locallyDrained && !r.resetRequired &&
    r.groups>=1.U && r.groups<=256.U && r.routedRows===(c.tokens.pad(11)<<3) &&
    r.routedDownBase===in.routedDown && owners && geometry && disjoint &&
    in.allocationBase>=c.host.regions(3).base && in.allocationBase<in.allocationEnd &&
    in.allocationEnd<=(BigInt(1)<<56).U &&
    sequence.pad(65)+9.U<=(BigInt(1)<<64).U-1.U
  def finish(status:UInt,drained:Bool):Unit={outStatus:=status;outDrained:=drained;state:=report}
  when(io.job.fire){
    job:=in;issued:=0.U;returned:=0.U;index:=0.U
    when(legal){state:=prepare}.otherwise{finish(Status.Dependency.U,true.B)}
  }
  when(state===prepare){
    when(fault){finish(Status.Dependency.U,!quarantine && !unknown && !io.memoryResetRequired)}.otherwise{
      val safe=Mux(index>=1.U && index<=8.U,index-1.U,0.U)(2,0)
      address:=Mux(index===0.U,job.metadataBase+(job.token.pad(64)<<6),
        job.descriptorBase+(UnifiedMoeRouteLayoutV2.expert(map(safe)).pad(64)<<6))
      tag:=sequence;state:=offer
    }
  }
  when(io.memory.fire){issued:=issued+1.U;sequence:=sequence+1.U;state:=waiting}
  when(io.response.fire){
    when(io.response.bits.tag=/=tag || io.response.bits.error){
      // Wrong attribution/error is NOT proof that this outstanding read retired.
      poison:=true.B;quarantine:=true.B;finish(Status.Protocol.U,false.B)
    }.otherwise{
      returned:=returned+1.U
      when(fault){finish(Status.Dependency.U,!quarantine && !unknown && !io.memoryResetRequired)}
      .elsewhen(index===0.U){
        val words=io.response.bits.data.asTypeOf(Vec(8,UInt(64.W)))
        val each=(0 until 8).map{i=>
          val w=words(i);val unique=(0 until i).map(j=>UnifiedMoeRouteLayoutV2.expert(w)=/=UnifiedMoeRouteLayoutV2.expert(words(j))).foldLeft(true.B)(_&&_)
          w(63,41)===0.U && UnifiedMoeRouteLayoutV2.token(w)===job.token &&
            UnifiedMoeRouteLayoutV2.rank(w)===i.U && UnifiedMoeRouteLayoutV2.row(w)<job.context.tokens &&
            !UnifiedMoeRouteLayoutV2.weight(w)(15) && UnifiedMoeRouteLayoutV2.weight(w)<="h3f80".U && unique
        }.reduce(_&&_)
        when(!each){poison:=true.B;finish(Status.Protocol.U,true.B)}
        .otherwise{map:=words;index:=1.U;state:=prepare}
      }.otherwise{
        val safe=Mux(index>=1.U && index<=8.U,index-1.U,0.U)(2,0)
        val w=map(safe);val d=io.response.bits.data
        val rows=UnifiedMoeDownDescriptorV4.rows(d);val first=UnifiedMoeDownDescriptorV4.firstRoute(d)
        val owner=UnifiedMoeDownDescriptorV4.owner(d);val out=UnifiedMoeDownDescriptorV4.output(d)
        val nbytes=rows.pad(96)<<12
        val expected=job.routedDown.pad(96)+(first.pad(96)<<12)
        val unique=(0 until 8).map{i=>
          i.U>=safe || (selected(i).ownerSequence=/=owner &&
            !(out.pad(96)<selected(i).output.pad(96)+(selected(i).groupRows.pad(96)<<12) &&
              selected(i).output.pad(96)<out.pad(96)+nbytes))
        }.reduce(_&&_)
        val valid=UnifiedMoeDownDescriptorV4.canonical(d) &&
          UnifiedMoeDownDescriptorV4.transaction(d)===job.context.transactionId &&
          UnifiedMoeDownDescriptorV4.allocation(d)===job.allocationSequence &&
          UnifiedMoeDownDescriptorV4.status(d)===Status.Ok.U &&
          UnifiedMoeDownDescriptorV4.expert(d)===UnifiedMoeRouteLayoutV2.expert(w) &&
          rows<=job.context.tokens && UnifiedMoeRouteLayoutV2.row(w)<rows &&
          first.pad(17)+rows.pad(17)<=(job.context.tokens.pad(17)<<3) &&
          out.pad(96)===expected && UnifiedMoeDownDescriptorV4.bytes(d).pad(96)===nbytes &&
          out.pad(96)+nbytes<=job.routedDown.pad(96)+4194304.U &&
          owner>job.firstOwnerSequence && owner<job.routed.nextOwnerSequence &&
          (owner-job.firstOwnerSequence)%5.U===0.U && unique
        when(!valid){poison:=true.B;finish(Status.Protocol.U,true.B)}.otherwise{
          selected(safe).expert:=UnifiedMoeRouteLayoutV2.expert(w)
          selected(safe).groupRow:=UnifiedMoeRouteLayoutV2.row(w)
          selected(safe).weight:=UnifiedMoeRouteLayoutV2.weight(w)
          selected(safe).output:=out;selected(safe).groupRows:=rows;selected(safe).ownerSequence:=owner
          when(index===8.U){
            val exact=issued===9.U && returned===8.U
            when(!exact){poison:=true.B};finish(Mux(exact,Status.Ok.U,Status.Protocol.U),true.B)
          }.otherwise{index:=index+1.U;state:=prepare}
        }
      }
    }
  }
  when(io.result.fire){state:=Mux(fault,locked,idle)}
  // Result fields hold; late fault remains an independent current sideband.
  // Unknown/missing read may wait forever: parent watchdog+isolated reset, not
  // invented empty debt or automatic successful output/allocator release.
}
