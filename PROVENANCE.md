# Provenance & honesty statement — yarqa

**License:** Apache-2.0. **Author:** SZL Holdings (clean-room). **Doctrine v11.**

## What this is
`yarqa` is an original, clean-room implementation of plug-flow compartmentalization:
reducing a resolved CFD velocity field into a network of sequential plug-flow
compartments by region-growing groups of velocity-aligned cells across a common
flow front.

## How it was built (clean-room discipline)
- It was written **solely from a published high-level algorithm description** (the
  region-growing-by-velocity-alignment method, described in prose/pseudocode).
- **No third-party source code was read or copied.** In particular, no AGPL-3.0
  source was consulted. The data structures (`Mesh`, the BFS frontier grower,
  the synthesized representative-point cloud for the straddle test), the
  vectorized NumPy implementation, the public API, the tests, and the docs are
  all original to SZL.
- Algorithms themselves are not copyrightable; this implementation is independent
  expression of a public method, released under Apache-2.0.

## What it is NOT (honesty doctrine)
- **`yarqa` formulas are NOT lutar-lean locked-proven theorems.** They are a
  numerical engineering method, not kernel-verified mathematics. They MUST NOT be
  added to the locked-proven count (which stays **8** {F1,F4,F7,F11,F12,F18,F19,F22}
  @ `c7c0ba17`), nor shown with a "proven/kernel-verified" badge. If surfaced in a
  product, label as: **"engineering method (CFD), not a locked theorem."**
- It makes no compliance, SLSA, or formal-verification claims.

## Relationship to prior art
The plug-flow compartmentalization *concept* appears in reactor-engineering
literature and in at least one prior open-source package under AGPL-3.0. `yarqa`
was implemented independently and does not incorporate that package's code; it is
not a derivative work of it. Cite the method conceptually, not that codebase.
