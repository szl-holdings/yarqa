# Copyright 2026 SZL Holdings
# SPDX-License-Identifier: Apache-2.0
"""Append-only, tamper-evident chain over agentic step receipts.

Each :class:`yarqa.agentic.AgentStep` is hashed into a chain *link* that also
commits to the previous link's digest (``prev_digest -> digest``). The result is
a hash-linked log: editing, reordering, inserting, or deleting any past step
breaks the chain, because every later link's digest depends on it. A holder of
the chain can :func:`ReceiptChain.verify` it end-to-end with no secret material.

This mirrors the SHAPE of SZL's platform receipt chain (P1 receipt-completeness
and P5 append-only ordering): one link per step, strictly appended, each
committing to its predecessor.

HONESTY (doctrine v11): this is an **integrity / tamper-evidence** mechanism,
not a proof of correctness and NOT a locked theorem. It demonstrates that a log
was not altered after the fact under the stated hash function; it makes no claim
that the agent's decisions were *correct*. ``claim_tier`` stays honest. It is a
plain hash chain, not a signed/anchored ledger; signing and external anchoring
are left to the platform's key-management, exactly as in ``yarqa.provenance``.

Original SZL implementation. Concept (hash-linked records, Merkle/Lamport-style
tamper evidence) is public and uncopyrightable; no third-party source was copied.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from typing import Any

from .agentic import AgentStep

_CHAIN_SCHEMA = "szl.yarqa.receipt-chain/v1"
# Genesis predecessor for the first link: a fixed, well-known zero digest.
GENESIS_PREV = "0" * 64

_CLAIM_TIER = (
    "engineering-method-cfd; append-only integrity chain; tamper-evident; "
    "NOT a locked theorem; asserts integrity/ordering, not correctness"
)


def _canonical(obj: Any) -> str:
    """Deterministic JSON for hashing (sorted keys, no whitespace drift)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@dataclass
class ChainLink:
    """One hash-linked record wrapping a single :class:`AgentStep`.

    Attributes
    ----------
    index : int
        0-based position in the chain.
    prev_digest : str
        Digest of the previous link (``GENESIS_PREV`` for the first link).
    step : dict
        The serialized ``AgentStep`` payload committed by this link.
    digest : str
        SHA-256 over ``(schema, index, prev_digest, step)``. Recomputable and
        verifiable by anyone holding the link.
    """

    index: int
    prev_digest: str
    step: dict[str, Any]
    digest: str

    @staticmethod
    def compute_digest(index: int, prev_digest: str, step: dict[str, Any]) -> str:
        """SHA-256 commitment binding this link to its predecessor and payload."""
        body = _canonical(
            {
                "schema": _CHAIN_SCHEMA,
                "index": index,
                "prev_digest": prev_digest,
                "step": step,
            }
        )
        return hashlib.sha256(body.encode()).hexdigest()

    def recompute(self) -> str:
        """Recompute this link's digest from its own fields."""
        return self.compute_digest(self.index, self.prev_digest, self.step)


@dataclass
class ReceiptChain:
    """An append-only, hash-linked chain of agentic step receipts.

    Use :meth:`append` to add steps in order; the chain refuses out-of-band
    mutation of ordering. :meth:`verify` re-derives every digest and confirms
    the ``prev_digest -> digest`` links are intact.
    """

    schema: str = _CHAIN_SCHEMA
    claim_tier: str = _CLAIM_TIER
    links: list[ChainLink] = field(default_factory=list)

    @property
    def head(self) -> str:
        """Digest of the latest link, or ``GENESIS_PREV`` if empty."""
        return self.links[-1].digest if self.links else GENESIS_PREV

    def append(self, step: AgentStep) -> ChainLink:
        """Append an ``AgentStep`` as a new link committing to the current head."""
        index = len(self.links)
        prev_digest = self.head
        payload = asdict(step)
        digest = ChainLink.compute_digest(index, prev_digest, payload)
        link = ChainLink(
            index=index, prev_digest=prev_digest, step=payload, digest=digest
        )
        self.links.append(link)
        return link

    def extend(self, steps: list[AgentStep]) -> None:
        """Append several steps in order."""
        for s in steps:
            self.append(s)

    def verify(self) -> dict[str, Any]:
        """Verify the chain end-to-end.

        Checks, for every link in order: (a) its recorded ``digest`` equals the
        recomputed digest of its fields, (b) its ``prev_digest`` equals the
        previous link's ``digest`` (``GENESIS_PREV`` for index 0), and (c) its
        ``index`` is the expected sequential value. Returns a verdict dict whose
        ``ok`` flag is True only if the whole chain is intact.
        """
        checks: dict[str, Any] = {}
        ok = True
        prev = GENESIS_PREV
        first_broken: int | None = None
        for i, link in enumerate(self.links):
            link_ok = True
            if link.index != i:
                link_ok = False
            if link.prev_digest != prev:
                link_ok = False
            if link.recompute() != link.digest:
                link_ok = False
            checks[f"link_{i}"] = link_ok
            if not link_ok:
                ok = False
                if first_broken is None:
                    first_broken = i
            prev = link.digest
        return {
            "ok": ok,
            "n_links": len(self.links),
            "head": self.head,
            "first_broken_index": first_broken,
            "checks": checks,
            "claim_tier": self.claim_tier,
        }

    def to_json(self) -> str:
        """Serialize the whole chain to canonical JSON."""
        return _canonical(
            {
                "schema": self.schema,
                "claim_tier": self.claim_tier,
                "links": [asdict(link) for link in self.links],
            }
        )

    @classmethod
    def from_json(cls, text: str) -> "ReceiptChain":
        """Load a chain from JSON produced by :meth:`to_json`.

        Loading does NOT trust the contents; call :meth:`verify` afterward to
        confirm integrity. This is how a third party validates a published log.
        """
        data = json.loads(text)
        links = [
            ChainLink(
                index=int(d["index"]),
                prev_digest=str(d["prev_digest"]),
                step=d["step"],
                digest=str(d["digest"]),
            )
            for d in data.get("links", [])
        ]
        return cls(
            schema=str(data.get("schema", _CHAIN_SCHEMA)),
            claim_tier=str(data.get("claim_tier", _CLAIM_TIER)),
            links=links,
        )
