// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.contracttests

import heteronpu.continuous.{GdnChunkAddressPlan, GdnChunkGeometry, GdnChunkVectorPolicy}
import GdnChunkAddressPlan._

/** Direct JVM behavior checks of the original, already compiled immutable plan.
  * No Chisel, tensor, transport, receipt, ACK execution, or numerical model is
  * constructed. expectedAckBytes is checked only as a declared byte obligation.
  * The only runtime I/O is the final success JSON on stdout. The required
  * chunk.expected.input.classes property is compared lexically with codeSource;
  * no class-root file, source file, or other file is read by this main.
  */
object GdnChunkAddressPlanBehavior {
  private var checks = 0L
  private var rejectedInputs = 0L
  private val Limit = BigInt(1) << 56
  private val LastGeneration = (BigInt(1) << 32) - 1
  private val Base = Bases(BigInt(0x01000000), BigInt(0x02000000),
    BigInt(0x03000000), BigInt(0x04000000), BigInt(0x08000000))

  // Independent literal dimensions and prefix offsets, not derived from Shapes.
  private val ExpectedShapes: Vector[(String, Int, Int, Int)] = Vector(
    ("gates", 64, 16, 0),
    ("q", 64, 128, 4096),
    ("k", 64, 128, 36864),
    ("v", 64, 128, 69632),
    ("kb", 64, 128, 102400),
    ("vb", 64, 128, 135168),
    ("kbg", 64, 128, 167936),
    ("qg", 64, 128, 200704),
    ("ke", 64, 128, 233472),
    ("kt", 128, 64, 266240),
    ("ket", 128, 64, 299008),
    ("pair", 64, 64, 331776),
    ("ut", 64, 64, 348160),
    ("intra", 64, 64, 364544),
    ("solvek", 64, 128, 380928),
    ("solvev", 64, 128, 413696),
    ("pred", 64, 128, 446464),
    ("vnew", 64, 128, 479232),
    ("inter", 64, 128, 512000),
    ("local", 64, 128, 544768),
    ("out", 64, 128, 577536),
    ("state_update", 128, 128, 610304),
    ("decay_state", 128, 128, 675840),
    ("next_state", 128, 128, 741376))

  // Phase order is independent of storage order: SolveV precedes SolveK.
  private val ExpectedPhases: Vector[(String, Vector[String], Int)] = Vector(
    ("LoadPrepAndCumsum", Vector("gates", "q", "k", "v"), 102400),
    ("DerivedAndPair", Vector("kb", "vb", "kbg", "qg", "ke", "pair"), 180224),
    ("TransposeK", Vector("kt"), 32768),
    ("TransposeDecayedK", Vector("ket"), 32768),
    ("UtMatmul", Vector("ut"), 16384),
    ("IntraMatmul", Vector("intra"), 16384),
    ("SolveV", Vector("solvev"), 32768),
    ("SolveK", Vector("solvek"), 32768),
    ("PredictMatmul", Vector("pred"), 32768),
    ("VnewSubtract", Vector("vnew"), 32768),
    ("InterMatmul", Vector("inter"), 32768),
    ("LocalMatmul", Vector("local"), 32768),
    ("OutputAdd", Vector("out"), 32768),
    ("StateUpdateMatmul", Vector("state_update"), 65536),
    ("StateDecay", Vector("decay_state"), 65536),
    ("StateAdd", Vector("next_state"), 65536),
    ("OutputMaterialize", Vector.empty[String], 0))

  private def check(ok: Boolean, clue: => String): Unit = {
    checks += 1
    if (!ok) throw new AssertionError(clue)
  }

  private def equal[A](actual: A, expected: A, clue: => String): Unit =
    check(actual == expected, clue + ": expected " + expected + ", got " + actual)

  // Only the specific required IllegalArgumentException counts as rejection.
  // AssertionError, linkage errors, and unrelated exception types propagate.
  private def rejects(clue: String, reason: String)(body: => Any): Unit = {
    var sawExpected = false
    try { body; () }
    catch {
      case e: IllegalArgumentException =>
        check(Option(e.getMessage).exists(_.contains(reason)),
          clue + ": wrong rejection reason: " + e.getMessage)
        sawExpected = true
    }
    check(sawExpected, clue + ": invalid input was accepted")
    rejectedInputs += 1
  }

  private def coldPlan(tokens: Int, bases: Bases = Base,
      policy: Int = GdnChunkVectorPolicy.LegacyFatalUnderflow): Plan =
    build(tokens, bases, cold = true, expectedGeneration = BigInt(0),
      committed = Committed(BigInt(0), None), vectorPolicy = policy)

  private def withBase(b: Bases, index: Int, value: BigInt): Bases = index match {
    case 0 => b.copy(input = value)
    case 1 => b.copy(stateIn = value)
    case 2 => b.copy(stateOut = value)
    case 3 => b.copy(output = value)
    case 4 => b.copy(scratch = value)
    case _ => throw new AssertionError("invalid test span index")
  }

  private def assertOrigin(label: String, clazz: Class[_], expected: String): Unit = {
    val domain = clazz.getProtectionDomain
    check(domain != null, label + ": missing protection domain")
    val source = domain.getCodeSource
    check(source != null && source.getLocation != null, label + ": missing codeSource")
    val uri = source.getLocation.toURI.normalize()
    equal(uri.getScheme, "file", label + ": codeSource must be a local class root")
    // Paths.get and Path.normalize are lexical operations, not toRealPath/Files.
    val actual = java.nio.file.Paths.get(uri).normalize().toString
    equal(actual, expected, label + ": must load from the pinned input classes")
  }

  private def testOrigins(): Unit = {
    val raw = sys.props.getOrElse("chunk.expected.input.classes",
      throw new AssertionError("missing required property chunk.expected.input.classes"))
    val path = java.nio.file.Paths.get(raw)
    check(path.isAbsolute, "expected original class root must be absolute")
    val expected = path.normalize().toString
    assertOrigin("AddressPlan", GdnChunkAddressPlan.getClass, expected)
    assertOrigin("Geometry", GdnChunkGeometry.getClass, expected)
    assertOrigin("VectorPolicy", GdnChunkVectorPolicy.getClass, expected)
    val p = coldPlan(16)
    assertOrigin("Plan", p.getClass, expected)
    assertOrigin("Shape", Shapes.head.getClass, expected)
    assertOrigin("Span", p.spans.head.getClass, expected)
    assertOrigin("Matrix", p.initial(0).getClass, expected)
    assertOrigin("Bases", Base.getClass, expected)
    assertOrigin("Committed", Committed(BigInt(0), None).getClass, expected)
    assertOrigin("AckBytes", AckBytes().getClass, expected)
    assertOrigin("Phase", Phases.head.getClass, expected)
    assertOrigin("Step", p.steps.head.getClass, expected)
  }

  private def testConstantsAndDescriptors(): Unit = {
    equal(GdnChunkGeometry.ChunkRows, 64, "chunk rows")
    equal(GdnChunkGeometry.Heads, 16, "heads")
    equal(GdnChunkGeometry.KeyDim, 128, "key dimension")
    equal(GdnChunkGeometry.ValueDim, 128, "value dimension")
    equal(GdnChunkGeometry.BeatBytes, 64, "beat bytes")
    equal(GdnChunkGeometry.PreparedRowBytes, 25600, "prepared row bytes")
    equal(GdnChunkGeometry.StateBytes, 1048576, "state bytes")
    equal(GdnChunkGeometry.OutputRowBytes, 4096, "output row bytes")
    equal(GdnChunkGeometry.AddressBits, 56, "address bits")
    equal(GdnChunkGeometry.SupportedTokens, Set(16, 128), "explicit supported M values")
    equal(GdnChunkVectorPolicy.LegacyFatalUnderflow, 0, "legacy policy ID")
    equal(GdnChunkVectorPolicy.FiniteGradualUnderflow, 1, "finite gradual policy ID")
    equal(PerHeadStateBytes, BigInt(65536), "FP32 per-head state bytes")
    equal(PerHeadChunkBytes, BigInt(806912), "24-matrix per-head chunk bytes")
    equal(InitialStatePhase, 0, "initial phase ID")
    equal(StateOutPhase, 18, "state-out phase ID")
    equal(Shapes.size, 24, "shape count")
    var i = 0
    while (i < 24) {
      val (name, rows, cols, _) = ExpectedShapes(i)
      equal(Shapes(i).name, name, "shape name " + i)
      equal(Shapes(i).rows, rows, "shape rows " + name)
      equal(Shapes(i).cols, cols, "shape cols " + name)
      equal(Shapes(i).bytes, BigInt(rows) * cols * 4, "FP32 shape bytes " + name)
      i += 1
    }
    equal(Phases.size, 17, "phase count")
    i = 0
    while (i < 17) {
      equal(Phases(i).name, ExpectedPhases(i)._1, "phase name " + i)
      equal(Phases(i).writes, ExpectedPhases(i)._2, "phase writes " + i)
      i += 1
    }
    equal(AckBytes(1, 2, 3) + AckBytes(5, 7, 11), AckBytes(6, 9, 14),
      "obligation counters add componentwise")
    rejects("shape zero rows", "requirement failed") { Shape("bad", 0, 16) }
    rejects("shape negative rows", "requirement failed") { Shape("bad", -1, 16) }
    rejects("shape zero cols", "requirement failed") { Shape("bad", 1, 0) }
    rejects("shape negative cols", "requirement failed") { Shape("bad", 1, -16) }
    rejects("shape incomplete beat", "requirement failed") { Shape("bad", 1, 15) }
    Vector(-1, 0, 1, 15, 17, 63, 64, 65, 127, 129, Int.MaxValue).foreach { m =>
      rejects("chunks unsupported M=" + m, "only explicit M16/M128") { chunks(m) }
      rejects("scratch unsupported M=" + m, "only explicit M16/M128") { scratchBytes(m) }
      rejects("build unsupported M=" + m, "only explicit M16/M128") { coldPlan(m) }
    }
  }

  private def testSpans(): Unit = {
    equal(Span(BigInt(0), BigInt(64)).end, BigInt(64), "zero-based span")
    equal(Span(Limit - 64, BigInt(64)).end, Limit, "56-bit exclusive end is legal")
    equal(Span(BigInt(0), Limit).end, Limit, "full domain is a scalar span, not an allocation")
    rejects("span negative base", "complete nonnegative aligned span") { Span(-64, 64) }
    rejects("span unaligned base", "complete nonnegative aligned span") { Span(1, 64) }
    rejects("span zero bytes", "complete nonnegative aligned span") { Span(0, 0) }
    rejects("span negative bytes", "complete nonnegative aligned span") { Span(0, -64) }
    rejects("span short bytes", "complete nonnegative aligned span") { Span(0, 63) }
    rejects("span unaligned bytes", "complete nonnegative aligned span") { Span(0, 65) }
    rejects("span beyond last beat", "complete span crosses 56-bit address domain") { Span(Limit, 64) }
    rejects("span end beyond domain", "complete span crosses 56-bit address domain") { Span(Limit - 64, 128) }
    rejects("large BigInt base", "complete span crosses 56-bit address domain") { Span(BigInt(1) << 80, 64) }
    val left = Span(0, 128)
    val touching = Span(128, 64)
    val overlap = Span(64, 128)
    check(left.disjoint(touching) && touching.disjoint(left), "touching spans are disjoint in both directions")
    check(!left.disjoint(overlap) && !overlap.disjoint(left), "partial overlap in both directions")
    check(!left.disjoint(left), "same nonempty span aliases itself")
    val last = Matrix(Limit - 64, Shape("last", 1, 16))
    equal(last.address(0), Limit - 64, "last legal FP32 matrix beat")
    equal(last.span.end, Limit, "last matrix exact endpoint")
    rejects("matrix extent past 56 bits", "complete span crosses 56-bit address domain") {
      Matrix(Limit - 64, Shape("too-wide", 1, 32))
    }
    rejects("matrix unaligned base", "complete nonnegative aligned span") {
      Matrix(1, Shape("one", 1, 16))
    }
    Vector((-1, 0), (1, 0), (0, -16), (0, 1), (0, 16)).foreach { case (r, c) =>
      rejects("matrix invalid beat " + r + "," + c, "complete FP32 beat index") { last.address(r, c) }
    }
  }

  private def testScratch(p: Plan, headBytes: Int, expectedScratch: Int): Unit = {
    var head = 0
    while (head < 16) {
      val headBase = p.bases.scratch + BigInt(head) * headBytes
      val initial = p.initial(head)
      equal(initial.base, headBase, "head then initial ordering " + head)
      equal(initial.shape, Shape("initial", 128, 128), "initial FP32 state shape")
      equal(initial.span.bytes, BigInt(65536), "initial state extent")
      equal(initial.address(127, 112) + 64, headBase + 65536, "initial last beat")
      var chunk = 0
      while (chunk < p.chunkCount) {
        val chunkBase = headBase + 65536 + BigInt(chunk) * 806912
        var next = chunkBase
        var i = 0
        while (i < 24) {
          val (name, rows, cols, offset) = ExpectedShapes(i)
          val matrix = p.matrix(head, chunk, name)
          equal(matrix.base, chunkBase + offset, "literal matrix prefix " + name)
          equal(matrix.base, next, "consecutive matrix span " + name)
          equal(matrix.shape, Shape(name, rows, cols), "matrix shape " + name)
          equal(matrix.address(0), chunkBase + offset, "first matrix beat " + name)
          equal(matrix.address(rows - 1, cols - 16) + 64,
            chunkBase + offset + BigInt(rows) * cols * 4, "last complete FP32 beat " + name)
          // Two short consecutive row intervals per matrix; no address Set.
          Vector(0, rows - 1).foreach { row =>
            var col = 0
            var expected = chunkBase + offset + BigInt(row) * cols * 4
            while (col < cols) {
              equal(matrix.address(row, col), expected, "consecutive matrix beats " + name)
              expected += 64
              col += 16
            }
          }
          equal(matrix.address(1), matrix.address(0) + cols * 4, "matrix row stride " + name)
          if (rows == 128) {
            equal(matrix.address(64), matrix.address(63) + cols * 4, "matrix row 63 to 64 " + name)
          }
          next = matrix.span.end
          i += 1
        }
        equal(next, chunkBase + 806912, "exact chunk end")
        val previous = p.previous(head, chunk)
        if (chunk == 0) equal(previous, initial, "chunk zero uses this head's initial state")
        else equal(previous, p.matrix(head, chunk - 1, "next_state"), "chunk recurrence uses preceding next_state")
        equal(p.validRows(chunk), if (p.tokens == 16) 16 else 64, "valid rows")
        chunk += 1
      }
      equal(p.matrix(head, p.chunkCount - 1, "next_state").span.end,
        headBase + headBytes, "head scratch ends after last chunk")
      if (head < 15) equal(p.initial(head + 1).base, headBase + headBytes, "next head follows all chunks")
      head += 1
    }
    equal(p.matrix(15, p.chunkCount - 1, "next_state").span.end,
      p.bases.scratch + expectedScratch, "entire scratch exact endpoint")
    Vector(-1, 16).foreach { h =>
      rejects("initial invalid head", "head") { p.initial(h) }
      rejects("matrix invalid head", "head") { p.matrix(h, 0, "q") }
      rejects("previous invalid head", "head") { p.previous(h, 0) }
    }
    Vector(-1, p.chunkCount).foreach { c =>
      rejects("matrix invalid chunk", "chunk") { p.matrix(0, c, "q") }
      rejects("previous invalid chunk", "chunk") { p.previous(0, c) }
      rejects("validRows invalid chunk", "chunk") { p.validRows(c) }
    }
    rejects("unknown scratch name", "unknown matrix name") { p.matrix(0, 0, "Q") }
  }

  private def testInputAndOutput(p: Plan): Unit = {
    var token = 0
    while (token < p.tokens) {
      var role = 0
      while (role < 3) {
        var head = 0
        while (head < 16) {
          var col = 0
          while (col < 128) {
            val expected = p.bases.input + BigInt(token) * 25600 + BigInt(role * 16 + head) * 512 + col * 4
            equal(p.inputVector(token, role, head, col), expected, "prepared input token/role/head/FP32 lane")
            col += 16
          }
          head += 1
        }
        role += 1
      }
      var head = 0
      while (head < 16) {
        equal(p.inputGate(token, head), p.bases.input + BigInt(token) * 25600 + 24576 + head * 64,
          "gate beat after all q/k/v vectors")
        var col = 0
        while (col < 128) {
          equal(p.outputAddress(token, head, col),
            p.bases.output + BigInt(token * 16 + head) * 256 + col * 2, "BF16 32-element output beat")
          col += 32
        }
        head += 1
      }
      equal(p.inputVector(token, 2, 15, 112) + 64, p.inputGate(token, 0), "vectors meet gate region")
      equal(p.inputGate(token, 15) + 64, p.bases.input + BigInt(token + 1) * 25600, "prepared row exact end")
      token += 1
    }
    equal(p.inputGate(p.tokens - 1, 15) + 64, p.spans(0).end, "input last legal beat")
    equal(p.outputAddress(p.tokens - 1, 15, 96) + 64, p.spans(3).end, "BF16 output last legal beat")
    Vector(-1, p.tokens).foreach { t =>
      rejects("input invalid token", "prepared vector index") { p.inputVector(t, 0, 0, 0) }
      rejects("gate invalid token", "prepared gate index") { p.inputGate(t, 0) }
      rejects("output invalid token", "BF16 output beat") { p.outputAddress(t, 0, 0) }
    }
    Vector(-1, 3).foreach { role =>
      rejects("input invalid role", "prepared vector index") { p.inputVector(0, role, 0, 0) }
    }
    Vector(-16, 1, 128).foreach { col =>
      rejects("input invalid FP32 column", "prepared vector index") { p.inputVector(0, 0, 0, col) }
    }
    Vector(-32, 1, 16, 128).foreach { col =>
      rejects("output invalid BF16 column", "BF16 output beat") { p.outputAddress(0, 0, col) }
    }
    Vector(-1, 16).foreach { head =>
      rejects("input invalid head", "head") { p.inputVector(0, 0, head, 0) }
      rejects("gate invalid head", "head") { p.inputGate(0, head) }
      rejects("output invalid head", "head") { p.outputAddress(0, head, 0) }
    }
    if (p.tokens == 16) {
      token = 16
      while (token < 64) {
        // Padded scratch rows exist, but no padded token may access input/output.
        equal(p.matrix(0, 0, "q").address(token), p.matrix(0, 0, "q").base + token * 512,
          "padding remains addressable only within full scratch matrix")
        Vector(0, 15).foreach { head =>
          var role = 0
          while (role < 3) {
            Vector(0, 112).foreach { col =>
              rejects("padding input token " + token, "padding must not read input") {
                p.inputVector(token, role, head, col)
              }
            }
            role += 1
          }
          rejects("padding gate token " + token, "prepared gate index") { p.inputGate(token, head) }
          rejects("padding output token " + token, "BF16 output beat") { p.outputAddress(token, head, 0) }
        }
        token += 1
      }
    } else {
      Vector(0, 15).foreach { head =>
        equal(p.inputVector(64, 0, head, 0) - p.inputVector(63, 0, head, 0), BigInt(25600), "token 63 to 64 vector boundary")
        equal(p.inputGate(64, head) - p.inputGate(63, head), BigInt(25600), "token 63 to 64 gate boundary")
        equal(p.outputAddress(64, head, 0) - p.outputAddress(63, head, 0), BigInt(4096), "token 63 to 64 output boundary")
        equal(p.matrix(head, 1, "q").base - p.matrix(head, 0, "q").base,
          BigInt(806912), "chunk 0 to 1 scratch stride, not a 64-row input stride")
        equal(p.previous(head, 1), p.matrix(head, 0, "next_state"), "63 to 64 carried chunk state")
      }
    }
  }

  private def testState(p: Plan): Unit = {
    Vector(false, true).foreach { out =>
      val base = if (out) p.bases.stateOut else p.bases.stateIn
      var head = 0
      while (head < 16) {
        var row = 0
        while (row < 128) {
          var col = 0
          while (col < 128) {
            equal(p.stateAddress(out, head, row, col),
              base + BigInt(head * 128 + row) * 512 + col * 4, "state remains FP32 head/row/16-element beat")
            col += 16
          }
          row += 1
        }
        equal(p.stateAddress(out, head, 64, 0) - p.stateAddress(out, head, 63, 0), BigInt(512), "state row 63 to 64")
        head += 1
      }
      equal(p.stateAddress(out, 15, 127, 112) + 64, base + 1048576, "last FP32 state beat")
      Vector(-1, 128).foreach { row =>
        rejects("state invalid row", "state beat") { p.stateAddress(out, 0, row, 0) }
      }
      Vector(-16, 1, 128).foreach { col =>
        rejects("state invalid column", "state beat") { p.stateAddress(out, 0, 0, col) }
      }
      Vector(-1, 16).foreach { head =>
        rejects("state invalid head", "head") { p.stateAddress(out, head, 0, 0) }
      }
    }
  }

  private def testSchedule(p: Plan, expectedSteps: Int, expectedScratch: Int, expectedOutput: Int): Unit = {
    equal(p.steps.size, expectedSteps, "exact schedule length")
    var index = 0
    var previous: Option[Step] = None
    var totals = AckBytes()
    def visit(expected: Step, obligation: AckBytes): Unit = {
      equal(p.steps(index), expected, "head -> initial -> chunks -> stateOut schedule at " + index)
      equal(p.predecessor(expected), previous, "serial predecessor at " + index)
      equal(p.expectedAckBytes(expected), obligation, "declared phase byte obligation at " + index)
      totals = totals + obligation
      previous = Some(expected)
      index += 1
    }
    var head = 0
    while (head < 16) {
      visit(Step(head, 0, 0), AckBytes(scratch = BigInt(65536)))
      var chunk = 0
      while (chunk < p.chunkCount) {
        var phase = 1
        while (phase <= 17) {
          val obligation = if (phase == 17)
            AckBytes(output = BigInt(if (p.tokens == 16) 4096 else 16384))
          else AckBytes(scratch = BigInt(ExpectedPhases(phase - 1)._3))
          visit(Step(head, chunk, phase), obligation)
          phase += 1
        }
        chunk += 1
      }
      visit(Step(head, p.chunkCount - 1, 18), AckBytes(state = BigInt(65536)))
      head += 1
    }
    equal(index, expectedSteps, "all steps visited exactly once")
    val wanted = AckBytes(BigInt(expectedScratch), BigInt(expectedOutput), BigInt(1048576))
    equal(totals, wanted, "independently summed declared obligations")
    equal(p.expectedTotalAcks, wanted, "plan declared total obligations, not observed ACKs")
    val invalid = Vector(Step(-1, 0, 0), Step(16, 0, 0), Step(0, -1, 1),
      Step(0, p.chunkCount, 1), Step(0, 0, -1), Step(0, 0, 19)) ++
      (if (p.chunkCount == 2) Vector(Step(0, 1, 0), Step(0, 0, 18)) else Vector.empty[Step])
    invalid.foreach { step =>
      rejects("invalid predecessor step " + step, "step identity") { p.predecessor(step) }
      rejects("invalid obligation step " + step, "step identity") { p.expectedAckBytes(step) }
    }
  }

  private def testPlacement(p: Plan): Unit = {
    val aliasReason = "five complete input/state/output/scratch spans must be disjoint"
    var first = 0
    var pairs = 0
    while (first < 5) {
      var second = first + 1
      while (second < 5) {
        check(p.spans(first).disjoint(p.spans(second)), "baseline five-span disjointness")
        Vector(0, 64).foreach { displacement =>
          val bad = withBase(Base, second, p.spans(first).base + displacement)
          rejects("cold alias pair " + first + "/" + second, aliasReason) { coldPlan(p.tokens, bad) }
          rejects("warm alias pair " + first + "/" + second, aliasReason) {
            build(p.tokens, bad, cold = false, expectedGeneration = BigInt(1),
              committed = Committed(BigInt(1), Some(bad.stateIn)), vectorPolicy = 0)
          }
        }
        pairs += 1
        second += 1
      }
      first += 1
    }
    equal(pairs, 10, "every unordered pair of five spans covered")
    var index = 0
    while (index < 5) {
      Vector(1, 32).foreach { shift =>
        rejects("unaligned plan span " + index, "complete nonnegative aligned span") {
          coldPlan(p.tokens, withBase(Base, index, p.spans(index).base + shift))
        }
      }
      rejects("negative plan span " + index, "complete nonnegative aligned span") {
        coldPlan(p.tokens, withBase(Base, index, BigInt(-64)))
      }
      val highBase = Limit - p.spans(index).bytes
      val high = coldPlan(p.tokens, withBase(Base, index, highBase))
      equal(high.spans(index).end, Limit, "each complete plan span may end exactly at 2^56")
      val lastBeat = index match {
        case 0 => high.inputGate(p.tokens - 1, 15)
        case 1 => high.stateAddress(false, 15, 127, 112)
        case 2 => high.stateAddress(true, 15, 127, 112)
        case 3 => high.outputAddress(p.tokens - 1, 15, 96)
        case 4 => high.matrix(15, p.chunkCount - 1, "next_state").address(127, 112)
        case _ => throw new AssertionError("invalid high-span test index")
      }
      equal(lastBeat + 64, Limit, "each span's actual final address respects full beat boundary")
      rejects("complete plan span exceeds 56 bits " + index, "complete span crosses 56-bit address domain") {
        coldPlan(p.tokens, withBase(Base, index, highBase + 64))
      }
      index += 1
    }
    // All five positive spans can touch consecutively, without any gap.
    val packed = Bases(BigInt(0), p.spans(0).bytes, p.spans(0).bytes + 1048576,
      p.spans(0).bytes + 2097152, p.spans(0).bytes + 2097152 + p.spans(3).bytes)
    val packedPlan = coldPlan(p.tokens, packed)
    index = 0
    while (index < 4) {
      equal(packedPlan.spans(index).end, packedPlan.spans(index + 1).base, "adjacent full plan spans are legal")
      index += 1
    }
  }

  private def testAdmission(): Unit = {
    Vector(16, 128).foreach { m =>
      Vector(0, 1).foreach { policy =>
        val cold = coldPlan(m, Base, policy)
        check(cold.cold, "cold flag retained")
        equal(cold.expectedGeneration, BigInt(0), "cold generation retained")
        equal(cold.vectorPolicy, policy, "explicit policy retained on cold plan")
        Vector(BigInt(1), LastGeneration - 1).foreach { generation =>
          val warm = build(m, Base, cold = false, expectedGeneration = generation,
            committed = Committed(generation, Some(Base.stateIn)), vectorPolicy = policy)
          check(!warm.cold, "warm flag retained")
          equal(warm.expectedGeneration, generation, "exact warm generation retained")
          equal(warm.vectorPolicy, policy, "explicit policy retained on warm plan")
          equal(warm.spans, cold.spans, "cold and carried plans retain the same complete spans")
          equal(warm.steps, cold.steps, "cold and carried plans retain exact phase order")
          equal(warm.expectedTotalAcks, cold.expectedTotalAcks, "cold and carried obligation totals")
        }
      }
      Vector(BigInt(-1), LastGeneration, LastGeneration + 1).foreach { generation =>
        rejects("generation cannot wrap " + generation, "generation cannot wrap") {
          build(m, Base, cold = false, expectedGeneration = generation,
            committed = Committed(generation, Some(Base.stateIn)), vectorPolicy = 0)
        }
      }
      rejects("committed generation mismatch", "committed generation identity") {
        build(m, Base, cold = false, expectedGeneration = BigInt(1),
          committed = Committed(BigInt(2), Some(Base.stateIn)), vectorPolicy = 0)
      }
      rejects("cold nonzero generation", "exact cold/carried state root") {
        build(m, Base, cold = true, expectedGeneration = BigInt(1), committed = Committed(BigInt(1), None), vectorPolicy = 0)
      }
      rejects("cold has committed root", "exact cold/carried state root") {
        build(m, Base, cold = true, expectedGeneration = BigInt(0),
          committed = Committed(BigInt(0), Some(Base.stateIn)), vectorPolicy = 0)
      }
      rejects("warm generation zero", "exact cold/carried state root") {
        build(m, Base, cold = false, expectedGeneration = BigInt(0),
          committed = Committed(BigInt(0), Some(Base.stateIn)), vectorPolicy = 0)
      }
      rejects("warm missing committed root", "exact cold/carried state root") {
        build(m, Base, cold = false, expectedGeneration = BigInt(1), committed = Committed(BigInt(1), None), vectorPolicy = 0)
      }
      rejects("warm wrong committed root", "exact cold/carried state root") {
        build(m, Base, cold = false, expectedGeneration = BigInt(1),
          committed = Committed(BigInt(1), Some(Base.stateIn + 64)), vectorPolicy = 0)
      }
      Vector(-1, 2, Int.MaxValue).foreach { policy =>
        rejects("undeclared vector policy " + policy, "explicit declared vector policy") { coldPlan(m, Base, policy) }
      }
    }
  }

  def main(args: Array[String]): Unit = {
    testOrigins()
    testConstantsAndDescriptors()
    testSpans()
    Vector((16, 1, 872448, 13959168, 409600, 65536, 304),
      (128, 2, 1679360, 26869760, 3276800, 524288, 576)).foreach {
      case (tokens, chunkCount, headBytes, scratch, input, output, stepCount) =>
        val p = coldPlan(tokens)
        equal(p.tokens, tokens, "tokens retained")
        equal(p.bases, Base, "base roots retained")
        equal(chunks(tokens), chunkCount, "chunk count")
        equal(p.chunkCount, chunkCount, "plan chunk count")
        equal(scratchBytes(tokens), BigInt(scratch), "exact scratch capacity")
        equal(p.spans.size, 5, "five full spans")
        equal(p.spans.map(_.base), Vector(Base.input, Base.stateIn, Base.stateOut, Base.output, Base.scratch), "span role order")
        equal(p.spans.map(_.bytes), Vector(BigInt(input), BigInt(1048576), BigInt(1048576), BigInt(output), BigInt(scratch)), "exact input/state/output/scratch capacities")
        testScratch(p, headBytes, scratch)
        testInputAndOutput(p)
        testState(p)
        testSchedule(p, stepCount, scratch, output)
        testPlacement(p)
    }
    testAdmission()
    println("{\"status\":\"PASS_SCALA_ADDRESS_PLAN_BEHAVIOR_ONLY\",\"checks\":" + checks +
      ",\"rejected_inputs\":" + rejectedInputs + ",\"sources_bound\":true," +
      "\"groups\":[\"class_origins\",\"m16_m128_capacities\",\"24_shape_offsets\",\"head_initial_chunk_order\"," +
      "\"63_to_64_boundaries\",\"valid_rows_padding_rejection\",\"state_fp32_output_bf16\",\"56_bit_span_endpoints\"," +
      "\"alignment\",\"five_span_ten_pair_aliases\",\"cold_warm_generation_policy\",\"phase_predecessors\",\"declared_byte_obligations\"]}")
  }
}
