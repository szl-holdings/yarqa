# yarqa domain leader study r1 (propose-only)

Date: 2026-11-22. Method: web-verified 2026 leaders. Documentation only: no code, CI, config, or existing-PR status changes. All absorb actions are FUTURE and non-authorizing; implementation and merges remain separately reviewed and gated by the signature wall.

## Domain: fail-closed declared-source /readyz readiness surface

## Leaders studied (web-verified 2026-11-22)

1. **Kubernetes probe semantics**: canonical liveness vs readiness distinction plus startup gating. [Normative docs](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).
2. **SRE status-honesty doctrine** (error budgets; freshness as first-class signal). [SRE Workbook](https://sre.google/workbook/implementing-slos/).

## Absorb actions (FUTURE PROPOSALS, non-authorizing)

1. (K8s semantics) /readyz distinct from liveness: readiness requires every declared dependency proven (declared-source contract), not merely reachable.
2. (SRE honesty) Freshness is a first-class field: every readiness input carries observation window + last-seen; absent data is UNKNOWN, never silently green.
Read-only alignment: open PR #117 (fail-closed declared-source /readyz); no status claim.

## Sources (accessed 2026-11-22)

- Kubernetes probe docs: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/ (normative)
- Google SRE Workbook, implementing SLOs: https://sre.google/workbook/implementing-slos/ (book doctrine, non-normative)

## Do not do

Do not merge, bypass the signature wall, or claim implementation beyond this card.
