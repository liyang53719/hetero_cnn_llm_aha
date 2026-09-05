package heteronpu.p0
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.util.Random

class MatrixTilePayloadSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d: MatrixTilePayload): Unit = {
    d.io.start_i.poke(false.B); d.io.activation_local_i.poke(0x1000.U); d.io.weight_local_i.poke(0x20000.U); d.io.output_local_i.poke(0x160000.U)
    d.io.depth_i.poke(1.U); d.io.weight_k_stride_i.poke(64.U); d.io.rows_i.poke(16.U); d.io.columns_i.poke(32.U); d.io.output_fp32_i.poke(false.B)
    d.io.l2_rd_ready_i.poke(false.B); d.io.l2_rsp_valid_i.poke(false.B); d.io.l2_rsp_data_i.poke(0.U); d.io.l2_wr_ready_i.poke(false.B)
    d.io.matrix_step_ready_i.poke(false.B); d.io.matrix_out_valid_i.poke(false.B); d.io.matrix_out_last_i.poke(false.B); d.io.matrix_acc_i.poke(0.U)
  }
  val invalid = Seq("a_at_end", "b_at_end", "c_at_end", "a_wrap", "b_wrap", "c_wrap", "depth0", "rows0", "rows17", "cols0", "cols33", "stride0", "stride65", "misaligned", "fp32_second_beat_overflow")
  for(kind <- invalid) it should s"reject $kind before any memory or Matrix request" in {
    test(new MatrixTilePayload).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      kind match {
        case "a_at_end" => d.io.activation_local_i.poke(0x180000.U)
        case "b_at_end" => d.io.weight_local_i.poke(0x180000.U)
        case "c_at_end" => d.io.output_local_i.poke(0x180000.U)
        case "a_wrap" => d.io.activation_local_i.poke(((BigInt(1)<<64)-64).U); d.io.depth_i.poke(2.U)
        case "b_wrap" => d.io.weight_local_i.poke(((BigInt(1)<<64)-64).U); d.io.depth_i.poke(2.U)
        case "c_wrap" => d.io.output_local_i.poke(((BigInt(1)<<64)-64).U)
        case "depth0" => d.io.depth_i.poke(0.U)
        case "rows0" => d.io.rows_i.poke(0.U)
        case "rows17" => d.io.rows_i.poke(17.U)
        case "cols0" => d.io.columns_i.poke(0.U)
        case "cols33" => d.io.columns_i.poke(33.U)
        case "stride0" => d.io.weight_k_stride_i.poke(0.U)
        case "stride65" => d.io.weight_k_stride_i.poke(65.U)
        case "misaligned" => d.io.activation_local_i.poke(0x1001.U)
        case "fp32_second_beat_overflow" => d.io.output_fp32_i.poke(true.B); d.io.rows_i.poke(1.U); d.io.output_local_i.poke(0x17ffc0.U)
      }
      d.io.start_i.poke(true.B); d.clock.step(); d.io.start_i.poke(false.B)
      d.io.done_o.expect(true.B); d.io.status_o.expect(5.U)
      d.io.l2_rd_valid_o.expect(false.B); d.io.l2_wr_valid_o.expect(false.B); d.io.matrix_step_valid_o.expect(false.B)
      d.io.read_beats_o.expect(0.U); d.io.write_beats_o.expect(0.U); d.io.matrix_steps_o.expect(0.U)
      d.clock.step(); d.io.done_o.expect(false.B)
    }
  }
  val shapes = Seq((1,1,1,false),(3,17,4,false),(16,32,17,false),(1,1,1,true),(3,16,4,true),(5,17,7,true),(16,32,17,true))
  for((r,c,depth,fp) <- shapes) it should s"execute ${r}x${c}x${depth} fp32=$fp with stalled payload and masked writeback" in {
    test(new MatrixTilePayload).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); d.clock.setTimeout(20000)
      d.io.rows_i.poke(r.U); d.io.columns_i.poke(c.U); d.io.depth_i.poke(depth.U); d.io.output_fp32_i.poke(fp.B)
      val outBase=if(r==1) 0x180000-(if(fp && c>16)128 else 64) else 0x160000
      d.io.output_local_i.poke(outBase.U); d.io.weight_k_stride_i.poke(512.U)
      val rng=new Random(9200+r+c+depth)
      def pack(xs:Seq[BigInt],w:Int):BigInt=xs.zipWithIndex.foldLeft(BigInt(0)){case(a,(v,i))=>a|(v<<(i*w))}
      def abeat(k:Int)=pack((0 until 32).map(i=>BigInt(0x3f00+k*33+i)),16)
      def bbeat(k:Int)=pack((0 until 32).map(i=>BigInt(0x3e00+k*35+i)),16)
      val words=(0 until 512).map(i=>BigInt(java.lang.Float.floatToRawIntBits((i-255).toFloat/17.0f).toLong & 0xffffffffL))
      val accumulator=pack(words,32)
      def bf(x:BigInt)=((x+0x7fff+((x>>16)&1))&0xffffffffL)>>16
      d.io.start_i.poke(true.B); d.clock.step(); d.io.start_i.poke(false.B)
      var response:Option[(BigInt,Int)]=None; var accDelay = -1; var steps=0; var reads=0; var writes=0; var ticks=0
      var heldRead:Option[BigInt]=None; var heldIssue:Option[(BigInt,BigInt,Boolean,Boolean)]=None; var heldWrite:Option[(BigInt,BigInt,BigInt)]=None
      while(!d.io.done_o.peek().litToBoolean && ticks<20000) {
        val rr=rng.nextInt(4)!=0; val mr=rng.nextInt(3)!=0; val wr=rng.nextInt(3)!=0
        d.io.l2_rd_ready_i.poke(rr.B); d.io.matrix_step_ready_i.poke(mr.B); d.io.l2_wr_ready_i.poke(wr.B)
        val responding=response.exists(_._2==0); d.io.l2_rsp_valid_i.poke(responding.B); d.io.l2_rsp_data_i.poke(response.map(_._1).getOrElse(BigInt(0)).U)
        val returning=accDelay==0; d.io.matrix_out_valid_i.poke(returning.B); d.io.matrix_out_last_i.poke(returning.B); d.io.matrix_acc_i.poke(accumulator.U)
        if(d.io.l2_rd_valid_o.peek().litToBoolean) {
          val addr=d.io.l2_rd_addr_o.peek().litValue; heldRead.foreach(_ shouldBe addr)
          if(rr) {
            val k=reads/2; addr shouldBe (if(reads%2==0) BigInt(0x1000/64+k) else BigInt(0x20000/64+k*8))
            response=Some((if(reads%2==0)abeat(k) else bbeat(k),1+rng.nextInt(3))); reads+=1; heldRead=None
          } else heldRead=Some(addr)
        }
        if(responding && d.io.l2_rsp_ready_o.peek().litToBoolean) response=None
        if(d.io.matrix_step_valid_o.peek().litToBoolean) {
          val tuple=(d.io.matrix_a_o.peek().litValue,d.io.matrix_b_o.peek().litValue,d.io.matrix_clear_o.peek().litToBoolean,d.io.matrix_last_o.peek().litToBoolean)
          heldIssue.foreach(_ shouldBe tuple)
          tuple._1 shouldBe (abeat(steps)&((BigInt(1)<<(16*r))-1)); tuple._2 shouldBe (bbeat(steps)&((BigInt(1)<<(16*c))-1))
          tuple._3 shouldBe (steps==0); tuple._4 shouldBe (steps==depth-1)
          if(mr) { steps+=1;heldIssue=None;if(steps==depth)accDelay=3 } else heldIssue=Some(tuple)
        }
        if(d.io.l2_wr_valid_o.peek().litToBoolean) {
          val tuple=(d.io.l2_wr_addr_o.peek().litValue,d.io.l2_wr_data_o.peek().litValue,d.io.l2_wr_be_o.peek().litValue)
          heldWrite.foreach(_ shouldBe tuple)
          val perRow=if(fp && c>16)2 else 1; val row=writes/perRow;val half=writes%perRow
          val n=if(fp)16 else 32; val expected=pack(words.slice(row*32+half*16,row*32+half*16+n).map(x=>if(fp)x else bf(x)),if(fp)32 else 16)
          val kept=if(fp)math.min(16,c-half*16)*4 else c*2
          tuple shouldBe ((BigInt(outBase/64+writes),expected,(BigInt(1)<<kept)-1))
          if(wr){writes+=1;heldWrite=None}else heldWrite=Some(tuple)
        }
        d.clock.step();ticks+=1
        response=response.map{case(x,n)=>(x,math.max(0,n-1))}; if(accDelay>=0)accDelay-=1
      }
      ticks should be < 20000; d.io.status_o.expect(0.U); d.io.matrix_steps_o.expect(depth.U); d.io.read_beats_o.expect((2*depth).U)
      val expectedWrites=r*(if(fp&&c>16)2 else 1); writes shouldBe expectedWrites; d.io.write_beats_o.expect(expectedWrites.U)
    }
  }
}
