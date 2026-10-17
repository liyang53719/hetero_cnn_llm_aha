"""Boolean handshake model of existing bridge + real VectorSilu loan equations.
No arithmetic/payload computation and no hardware protocol PASS implied.
"""
from dataclasses import dataclass
@dataclass(frozen=True)
class Inputs:
 binary:bool=True
 external_abort:bool=False
 bridge_poison:bool=False
 loan_poison:bool=False
 loan_active:bool=True
 raw_valid:bool=True
 raw_error:bool=False
 tile_reset:bool=False
 tile_valid:bool=False
 tile_error:bool=False
 write_ready:bool=False
 in_result:bool=True
 tile_drained:bool=True
 bridge_busy:bool=True
 other_services_busy:bool=False

def evaluate(i):
 abort=i.external_abort or i.bridge_poison
 valid=i.loan_active and i.raw_valid and (not i.binary or not(i.loan_poison or abort))
 bad=i.external_abort or i.bridge_poison or i.tile_reset or i.loan_poison or (i.tile_valid and i.tile_error) or (valid and i.raw_error)
 ready=bad or (i.in_result and i.write_ready)
 raw_ready=i.loan_active and (ready or (i.binary and (i.loan_poison or abort)))
 raw_fire=i.raw_valid and raw_ready
 public_fire=valid and ready
 active_next=i.loan_active and not(raw_fire if i.binary else public_fire)
 poison_next=i.loan_poison or abort or ((raw_fire if i.binary else public_fire) and i.raw_error)
 return dict(abort=abort,bad=bad,valid=valid,ready=ready,raw_fire=raw_fire,public_fire=public_fire,
  write_valid=not bad and i.in_result and valid,admit_new=not bad,
  loan_active_next=active_next,loan_poison_next=poison_next,bridge_poison_next=i.bridge_poison or bad,
  loan_drained=not i.loan_active,bridge_can_lock=bad and i.tile_drained and not i.loan_active,
  coordinator_can_reply=not i.other_services_busy and i.tile_drained and not i.loan_active and not i.bridge_busy)

def original_fixed_points(i):
 result=[]
 for abort in (False,True):
  valid=i.loan_active and i.raw_valid and (not i.binary or not(i.loan_poison or abort))
  bad=i.external_abort or i.bridge_poison or i.tile_reset or i.loan_poison or (i.tile_valid and i.tile_error) or (valid and i.raw_error)
  if abort==bad:result.append((abort,valid,bad))
 return result

def loan_edge(binary,abort,poison,active,raw_valid,public_ready):
 """Independent service-side ready case, including borrower ready held low."""
 valid=active and raw_valid and (not binary or not(poison or abort))
 raw_ready=active and (public_ready or (binary and (poison or abort)))
 fire=raw_valid and raw_ready
 public_fire=valid and public_ready
 return valid,fire,public_fire,active and not(fire if binary else public_fire)
