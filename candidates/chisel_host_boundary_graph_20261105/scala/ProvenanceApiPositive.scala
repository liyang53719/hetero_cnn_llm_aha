package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState}
import firrtl2.ir.Circuit
object ProvenanceApiPositive {
  def take(p:ObservedPrepareAst):ObservedPrepareAst.Grant=p.takeGrant()
  def repair(b:Circuit,s:CircuitState,a:AnnotationSeq,g:ObservedPrepareAst.Grant):ClockInitRepresentationRepair.ProvenanceResult=ClockInitRepresentationRepair.applyWithProvenance(b,s,a,1,g)
  def claimTypeOnly(c:ObservedPrepareAst.Claim):ObservedPrepareAst.Claim=c
}
