import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm

# Flood's entry here is the PROVISIONAL one: calibrate_frequency()
# re-derives it against the severity the two flood legs actually blend
# to, which no import-time constant can know. Nothing is calibrated in
# this script, so the flood row below is the ABI headline version.
print("ABI target frequencies (per policy per year):")
for k, v in bm.ABI_TARGET_FREQ.items():
    print(f"  {k:4} {v:.4%}   implied claims/yr {v * bm.POLICIES:,.0f}")
print(f"\nmodelled-peril loss cost target : £{bm.ABI_LOSS_PER_POLICY:,.2f}/policy")
allp = bm.ABI["total_home_paid"] / bm.POLICIES
print(f"all-perils home claims cost     : £{allp:,.2f}/policy")
print(f"modelled perils as share of all : {bm.ABI_LOSS_PER_POLICY / allp:.0%}")
