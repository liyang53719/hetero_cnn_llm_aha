# Five elaboration warnings: source-local explanation

The generated Host93 CHIRRTL log reported five index-width warnings. These explanations do not suppress warnings, modify RTL sources or establish all-state range safety, acyclicity, protocol correctness or numerical correctness. No regeneration was performed for this explanation.

## W004: public21 opcode lookup, HostBlockCommands.scala 558:57

The 16-bit `pc` indexes a 21-entry `expectedOpcode` Vec, whose minimal selector is 5 bits. Lines525-526 define the 21 entries. Line558 combines this lookup with `pc<21.U`; lines967-968 reject `!officialRoleOK` before the validated dispatch chain. This explains the width warning and identifies an explicit range condition. A Chisel hardware conjunction is not software short-circuit evaluation: the condition alone is not a proof that the out-of-range lookup never exists or that every state transition is safe.

## W004: public21 output provenance write, HostBlockCommands.scala 76:24

`officialOutputs` is a 21-entry address Vec (line72). `rememberOfficial()` writes `officialOutputs.get(pc)` using the same 16-bit program counter. Calls at980,995,997,1000 occur in the validated dispatch chain after the `!officialRoleOK` rejection at968. Launch validation at329 requires official-profile `commands===21`, and progression guards are visible at320 and1307. These are local supporting guards, not a completed invariant proof for all command states, errors, resets and grouped commands.

## W005 twice: policy subset selectors, HostBlockCommands.scala 614:18 and614:53

`policy` has12 entries (line67), while `attentionPolicySlot` and `attentionContextSlot` have2-bit widths. The expressions at181-182 select policy slots0/1/2 and context slots1/2/3. The narrow selectors cannot address all12 entries, and this specific expression intentionally selects a subset. The official BF16 profile also requires `!bf16AttentionCore` (lines19-21); the declarations still elaborate. This source-local range observation is not proof of the broader policy parser or metadata protocol.

## W004: retained FFN drain row index, TransposedDenseOwner.scala 966:68

`finalValue(writeRow(3,0))((beat.pad(8)<<4)+i.U)` reads a256-entry row. Padding beat to8 bits and shifting left4 forms a12-bit index; only8 bits are needed to represent0..255. The drain branch chooses this value at967. `drainRowBeat=Cat(writeContext,writeBeat)` appears at954; callers may add `writeIndex` at986. Burst lengths, acknowledgements and drain row progress are constrained elsewhere, including979-986 and1511-1526. This explains the width growth but does not establish that every accepted burst's effective beat remains at most15. No truncation, cast, masking or warning suppression is proposed here without separate behavioral evidence.

## Project source identities

HostBlockCommands.scala SHA256 `94e6198a060044ae58a90328394ec8d11fe3311647fef62c1a1b975f2504ff4a`; TransposedDenseOwner.scala SHA256 `f402c19b32fb9619b549bdbe4c65c3237d49fcde01210701ed048c24540f9ac6`. Line numbers refer to this fixed new93 source snapshot.
