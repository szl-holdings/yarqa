"""Yarqa — plug-flow compartmentalization for compartmental models.

`yarqa` (Quechua: an Andean irrigation canal that divides and routes flowing
water) partitions a CFD mesh into plug-flow compartments by grouping cells whose
velocity fields are aligned and that lie across a common flow front.

Clean-room implementation by SZL Holdings, written from the published algorithm
description only. Apache-2.0. See PROVENANCE.md.
"""

from .core import (
    Mesh,
    compartmentalize,
    build_connection_map,
)

__all__ = ["Mesh", "compartmentalize", "build_connection_map"]
__version__ = "0.1.0"
