import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as bm

print("ABI target frequencies (per policy per year):")
for k, v in bm.ABI_TARGET_FREQ.items():
    print(f"  {k:4} {v:.4%}   implied claims/yr {v * bm.POLICIES:,.0f}")
print(f"\nmodelled-peril loss cost target : £{bm.ABI_LOSS_PER_POLICY:,.2f}/policy")
allp = bm.ABI["total_home_paid"] / bm.POLICIES
print(f"all-perils home claims cost     : £{allp:,.2f}/policy")
print(f"modelled perils as share of all : {bm.ABI_LOSS_PER_POLICY / allp:.0%}")
