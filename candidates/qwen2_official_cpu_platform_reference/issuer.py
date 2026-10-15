"""Reuse existing external-certificate issuer, scoped to the new source closure."""
import recipe as R
I=R.load_ci('issuer.py')
I.source_closure_digest=lambda:R.V.source_digest(R.ROOT)
# Functions retain their original module globals, including the new bound recipe.
for key in dir(I):
    if not key.startswith('_'):globals()[key]=getattr(I,key)
if __name__=='__main__':raise SystemExit(I.main())
