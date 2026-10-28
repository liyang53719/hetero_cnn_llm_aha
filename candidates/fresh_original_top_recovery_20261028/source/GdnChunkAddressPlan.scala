// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

/** Immutable BigInt plan for source/elaboration/contract checks. This is NOT a
  * synthesized address generator, ACK tracker, scheduler or arithmetic owner.
  * Its exact SSA order comes from the pinned chunk/model.py, not an M1 loop.
  */
object GdnChunkAddressPlan {
  import GdnChunkGeometry._
  private val AddressLimit = BigInt(1) << AddressBits
  private val LastGeneration = (BigInt(1) << 32) - 1

  final case class Shape(name: String, rows: Int, cols: Int) {
    require(rows > 0 && cols > 0 && cols % 16 == 0)
    val bytes: BigInt = BigInt(rows) * cols * 4
  }
  val Shapes: Vector[Shape] = Vector(
    Shape("gates", 64, 16), Shape("q", 64, 128), Shape("k", 64, 128),
    Shape("v", 64, 128), Shape("kb", 64, 128), Shape("vb", 64, 128),
    Shape("kbg", 64, 128), Shape("qg", 64, 128), Shape("ke", 64, 128),
    Shape("kt", 128, 64), Shape("ket", 128, 64), Shape("pair", 64, 64),
    Shape("ut", 64, 64), Shape("intra", 64, 64), Shape("solvek", 64, 128),
    Shape("solvev", 64, 128), Shape("pred", 64, 128), Shape("vnew", 64, 128),
    Shape("inter", 64, 128), Shape("local", 64, 128), Shape("out", 64, 128),
    Shape("state_update", 128, 128), Shape("decay_state", 128, 128),
    Shape("next_state", 128, 128))
  require(Shapes.map(_.name).distinct.size == 24)
  val PerHeadChunkBytes: BigInt = Shapes.map(_.bytes).sum
  val PerHeadStateBytes: BigInt = BigInt(KeyDim) * ValueDim * 4

  final case class Span(base: BigInt, bytes: BigInt) {
    require(base >= 0 && bytes > 0 && base % BeatBytes == 0 && bytes % BeatBytes == 0,
      "complete nonnegative aligned span")
    require(base + bytes <= AddressLimit, "complete span crosses 56-bit address domain")
    val end: BigInt = base + bytes
    def disjoint(other: Span): Boolean = end <= other.base || other.end <= base
  }
  final case class Matrix(base: BigInt, shape: Shape) {
    val span: Span = Span(base, shape.bytes)
    def address(row: Int, col: Int = 0): BigInt = {
      require(row >= 0 && row < shape.rows && col >= 0 && col < shape.cols && col % 16 == 0,
        "complete FP32 beat index")
      base + (BigInt(row) * shape.cols + col) * 4
    }
  }
  final case class Bases(input: BigInt, stateIn: BigInt, stateOut: BigInt,
                         output: BigInt, scratch: BigInt)
  final case class Committed(generation: BigInt, state: Option[BigInt])
  final case class AckBytes(scratch: BigInt = 0, output: BigInt = 0, state: BigInt = 0) {
    def +(other: AckBytes): AckBytes =
      AckBytes(scratch + other.scratch, output + other.output, state + other.state)
  }

  /** One coarse phase may contain the original per-row micro-order. In
    * particular DerivedAndPair groups chunk exp followed by each row's
    * cumulative/remaining exp, key/query/vbeta products and causal pair values;
    * it does NOT move all products ahead of all rows' exponentials.
    */
  final case class Phase(name: String, writes: Vector[String])
  val Phases: Vector[Phase] = Vector(
    Phase("LoadPrepAndCumsum", Vector("gates", "q", "k", "v")),
    Phase("DerivedAndPair", Vector("kb", "vb", "kbg", "qg", "ke", "pair")),
    Phase("TransposeK", Vector("kt")),
    Phase("TransposeDecayedK", Vector("ket")),
    Phase("UtMatmul", Vector("ut")),
    Phase("IntraMatmul", Vector("intra")),
    Phase("SolveV", Vector("solvev")),
    Phase("SolveK", Vector("solvek")),
    Phase("PredictMatmul", Vector("pred")),
    Phase("VnewSubtract", Vector("vnew")),
    Phase("InterMatmul", Vector("inter")),
    Phase("LocalMatmul", Vector("local")),
    Phase("OutputAdd", Vector("out")),
    Phase("StateUpdateMatmul", Vector("state_update")),
    Phase("StateDecay", Vector("decay_state")),
    Phase("StateAdd", Vector("next_state")),
    Phase("OutputMaterialize", Vector.empty))
  require(Phases.flatMap(_.writes).sorted == Shapes.map(_.name).sorted)
  val InitialStatePhase = 0
  val StateOutPhase = 18

  final case class Step(head: Int, chunk: Int, phase: Int)

  def chunks(tokens: Int): Int = {
    require(SupportedTokens(tokens), "only explicit M16/M128, chunk size remains 64")
    (tokens + ChunkRows - 1) / ChunkRows
  }
  def scratchBytes(tokens: Int): BigInt =
    BigInt(Heads) * (PerHeadStateBytes + chunks(tokens) * PerHeadChunkBytes)

  final class Plan private[GdnChunkAddressPlan](val tokens: Int, val bases: Bases,
      val cold: Boolean, val expectedGeneration: BigInt, val vectorPolicy: Int) {
    val chunkCount: Int = chunks(tokens)
    val spans: Vector[Span] = Vector(
      Span(bases.input, BigInt(tokens) * PreparedRowBytes),
      Span(bases.stateIn, BigInt(StateBytes)), Span(bases.stateOut, BigInt(StateBytes)),
      Span(bases.output, BigInt(tokens) * OutputRowBytes), Span(bases.scratch, scratchBytes(tokens)))
    require(spans.indices.forall(i => (0 until i).forall(j => spans(i).disjoint(spans(j)))),
      "five complete input/state/output/scratch spans must be disjoint, including cold stateIn")
    private val headScratchBytes = PerHeadStateBytes + chunkCount * PerHeadChunkBytes
    private def checkHead(head: Int): Unit = require(head >= 0 && head < Heads, "head")
    private def checkChunk(chunk: Int): Unit = require(chunk >= 0 && chunk < chunkCount, "chunk")
    def initial(head: Int): Matrix = {
      checkHead(head)
      Matrix(bases.scratch + head * headScratchBytes, Shape("initial", KeyDim, ValueDim))
    }
    def matrix(head: Int, chunk: Int, name: String): Matrix = {
      checkHead(head); checkChunk(chunk)
      val index = Shapes.indexWhere(_.name == name)
      require(index >= 0, "unknown matrix name")
      val offset = Shapes.take(index).map(_.bytes).sum
      Matrix(initial(head).span.end + chunk * PerHeadChunkBytes + offset, Shapes(index))
    }
    def previous(head: Int, chunk: Int): Matrix = {
      checkHead(head); checkChunk(chunk)
      if (chunk == 0) initial(head) else matrix(head, chunk - 1, "next_state")
    }
    def validRows(chunk: Int): Int = {
      checkChunk(chunk); math.min(ChunkRows, tokens - chunk * ChunkRows)
    }
    def inputVector(token: Int, role: Int, head: Int, col: Int): BigInt = {
      checkHead(head)
      require(token >= 0 && token < tokens && role >= 0 && role < 3 &&
        col >= 0 && col < KeyDim && col % 16 == 0, "prepared vector index; padding must not read input")
      bases.input + BigInt(token) * PreparedRowBytes + BigInt(role * Heads + head) * KeyDim * 4 + col * 4
    }
    def inputGate(token: Int, head: Int): BigInt = {
      checkHead(head); require(token >= 0 && token < tokens, "prepared gate index")
      bases.input + BigInt(token) * PreparedRowBytes + 24576 + head * BeatBytes
    }
    def stateAddress(out: Boolean, head: Int, row: Int, col: Int): BigInt = {
      checkHead(head)
      require(row >= 0 && row < KeyDim && col >= 0 && col < ValueDim && col % 16 == 0, "state beat")
      (if (out) bases.stateOut else bases.stateIn) + (BigInt(head * KeyDim + row) * ValueDim + col) * 4
    }
    def outputAddress(token: Int, head: Int, col: Int): BigInt = {
      checkHead(head)
      require(token >= 0 && token < tokens && col >= 0 && col < ValueDim && col % 32 == 0, "BF16 output beat")
      bases.output + (BigInt(token * Heads + head) * ValueDim + col) * 2
    }
    // This serial phase order is the existing software order, not a proposal
    // for overlapping phases/heads. Initial/StateOut steps use canonical chunk 0/last.
    val steps: Vector[Step] = (0 until Heads).toVector.flatMap { head =>
      Vector(Step(head, 0, InitialStatePhase)) ++
        (0 until chunkCount).toVector.flatMap { chunk =>
          Phases.indices.toVector.map(i => Step(head, chunk, i + 1))
        } ++ Vector(Step(head, chunkCount - 1, StateOutPhase))
    }
    def predecessor(step: Step): Option[Step] = {
      val index = steps.indexOf(step); require(index >= 0, "step identity")
      if (index == 0) None else Some(steps(index - 1))
    }
    def expectedAckBytes(step: Step): AckBytes = {
      require(steps.contains(step), "step identity")
      if (step.phase == InitialStatePhase) AckBytes(scratch = PerHeadStateBytes)
      else if (step.phase == StateOutPhase) AckBytes(state = PerHeadStateBytes)
      else if (step.phase == Phases.size) AckBytes(output = BigInt(validRows(step.chunk)) * ValueDim * 2)
      else AckBytes(scratch = Phases(step.phase - 1).writes.map(name => matrix(step.head, step.chunk, name).span.bytes).sum)
    }
    val expectedTotalAcks: AckBytes = steps.map(expectedAckBytes).foldLeft(AckBytes())(_ + _)
    require(expectedTotalAcks == AckBytes(scratchBytes(tokens), BigInt(tokens) * OutputRowBytes, BigInt(StateBytes)),
      "every scratch matrix, stateOut beat and valid output beat has one ACK obligation")
  }

  def build(tokens: Int, bases: Bases, cold: Boolean, expectedGeneration: BigInt,
      committed: Committed, vectorPolicy: Int): Plan = {
    chunks(tokens)
    require(expectedGeneration >= 0 && expectedGeneration < LastGeneration, "generation cannot wrap")
    require(committed.generation == expectedGeneration, "committed generation identity")
    require(if (cold) expectedGeneration == 0 && committed.state.isEmpty
      else expectedGeneration > 0 && committed.state.contains(bases.stateIn), "exact cold/carried state root")
    require(vectorPolicy == GdnChunkVectorPolicy.LegacyFatalUnderflow ||
      vectorPolicy == GdnChunkVectorPolicy.FiniteGradualUnderflow, "explicit declared vector policy")
    new Plan(tokens, bases, cold, expectedGeneration, vectorPolicy)
  }
}
