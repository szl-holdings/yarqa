# conda-forge recipe mirror (canonical sync)

This directory mirrors the staged conda-forge recipe for yarqa, byte-identical
to the one under review at conda-forge/staged-recipes#35678
(https://github.com/conda-forge/staged-recipes/pull/35678).

Sync doctrine (same as szl at szl-holdings/szl-gpu-bridge/sdk/conda-forge/):

- This in-repo copy is the canonical source of truth for the recipe.
- Changes here flow outward: after merge, the same bytes are pushed to the
  staged-recipes PR / feedstock. Never edit one without the other.
- LICENSE in this directory is the byte-exact copy from the 0.5.0 sdist
  (sha256 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30),
  vendored alongside the recipe the same way conda-forge staged-recipes
  packages it.

Receipts (MEASURED 2026-11-15, before staging):

- PyPI sdist sha256: b79b1033c995f199c80e2ad03f516eeb5bb6adee4a1f233cc112154579dc575e
- All recipe-tested modules import with numpy as the only third-party dep.
- Plug-flow smoke assertion (uniform +x flow, 6x6 grid -> 6 compartments;
  3-cell row -> 3 compartments) passes on the extracted sdist tree.
