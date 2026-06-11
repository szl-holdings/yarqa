# Citations — yarqa

`yarqa` is an original clean-room implementation. The *ideas* it builds on are
published research; we cite them as inspiration and prior art, and we copied no
code from any of them.

## CFD-based compartmental modeling (the core method's research lineage)
- Le Nepvou De Carfort, Pinto, Krühne (2024). *An Automatic Method for Generation
  of CFD-Based 3D Compartment Models: Towards Real-Time Mixing Simulations.*
  Bioengineering 11(2):169. doi:10.3390/bioengineering11020169.
- Haringa, Noorman, Tang (2021). *Stochastic parcel tracking in an Euler–Lagrange
  compartment model for fast simulation of fermentation processes.*
  doi:10.1002/bit.28094.
- Jupke, Weber (2020). *Compartment-model for the simulation of the separation
  performance of stirred liquid–liquid-extraction columns.* AIChE J.
  doi:10.1002/aic.16286.
- Yu, Hounslow, Reynolds, et al. (2017). *A compartmental CFD-PBM model of high
  shear wet granulation.* AIChE J. doi:10.1002/AIC.15401.
- Wiersdalen et al. (2025). *Stability Analysis of Compartmental and Cooperative
  Systems.* arXiv:2312.11061 (compartmental-matrix stability conditions).

## Mixture-of-Experts routing (the agentic routing IDEA only)
- Jacobs, Jordan, Nowlan, Hinton (1991). *Adaptive Mixtures of Local Experts.*
  Neural Computation 3(1).
- Shazeer et al. (2017). *Outrageously Large Neural Networks: The Sparsely-Gated
  Mixture-of-Experts Layer.* (top-k gating idea.)

## Information-flow security (the governed-loop P3 SHAPE only)
- Goguen, Meseguer (1982). *Security Policies and Security Models* (non-interference).

> All concepts above are used as published ideas. yarqa's data structures, code,
> tests, the provenance-receipt design, and the agentic loop are original SZL
> work under Apache-2.0. yarqa is an **engineering method (CFD)**, not a
> lutar-lean locked theorem.
