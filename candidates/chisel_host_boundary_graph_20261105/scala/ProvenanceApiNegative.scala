package chiseltest.simulator

object ProvenanceApiNegative {
  def constructGrant:ObservedPrepareAst.Grant=new ObservedPrepareAst.Grant(null,null)
  def constructClaim:ObservedPrepareAst.Claim=new ObservedPrepareAst.Claim(null,null)
  def copyGrant(g:ObservedPrepareAst.Grant)=g.copy()
  def callbackGrant(g:ObservedPrepareAst.Grant)=g.withClaim((c:ObservedPrepareAst.Claim)=>c)
}
