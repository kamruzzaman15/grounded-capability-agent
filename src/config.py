"""Tunable limits in one place so routing functions and the README agree."""

MAX_STEPS = 10        # cap on the gather loop (plan/act pairs)
MAX_RETRIES = 2       # in-node retries on a failing fetch before falling back
MAX_REVISIONS = 2     # cap on the verify/revise loop
STALL_LIMIT = 2       # consecutive gather steps with no new evidence -> stop
RECURSION_LIMIT = 90  # LangGraph safety limit for a full run

# Grounding vocabulary. A "polarized" claim asserts a capability is present or
# unavailable and therefore requires evidence; unverified asserts nothing.
VERIFIED_PRESENT = "verified_present"
VERIFIED_UNAVAILABLE = "verified_unavailable"
UNVERIFIED = "unverified"
POLARIZED = {VERIFIED_PRESENT, VERIFIED_UNAVAILABLE}
