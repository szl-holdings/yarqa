---
title: yarqa — Plug-Flow Compartments (live or sample, always honest)
emoji: 🌊
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# yarqa Space

A multi-tab demo of **yarqa** — clean-room plug-flow compartmentalization for
compartmental CFD models (Apache-2.0). FastAPI backend + a sovereign static app
with **vendored THREE r160** (no CDN; the library is copied into `static/lib/`).

> **Honesty (doctrine v11).** yarqa is an **engineering method (CFD) tier**
> capability. It is **NOT** a locked theorem, is **never** folded into the
> locked-8 `{F1,F4,F7,F11,F12,F18,F19,F22}`, and carries **no "proven" badge**.
> Receipts assert **integrity / reproducibility**, *not correctness*.
> Λ = Conjecture 1, Khipu = Conjecture 2, SLSA L1.

## Tabs (each unique)

1. **Flow Compartments (3D)** — vendored-THREE render of a velocity field
   colored by `yarqa.compartmentalize` labels; `align_threshold` + top-k
   sliders; live recompute; compartment count + signed-ready receipt digest.
2. **Agentic Loop** — live `AgenticYarqa` sense→route→gate→receipt; streams the
   `AgentStep` log (route target, ALLOW/DENY, receipt digest). Conforms to the
   SHAPE of P1/P2/P4 — an engineering loop, not a proof.
3. **Receipt Chain** — the append-only hash-linked chain with a **verify** /
   **tamper** button that replays digests and shows OK / first-broken index.
4. **Forecast** — an HONEST short-horizon projection; everything beyond the
   live/sample data is labeled **PROJECTED**. No invented numbers.
5. **Live Data** — the real feeds powering the maritime/flow use case, each
   independently **LIVE** when reachable else **SAMPLE / SIMULATED**, with the
   source URL cited.

## Architecture rule

Every data tab uses **one code path** with an explicit **LIVE vs SAMPLE** badge
based on **real reachability** of license-clean public feeds — synthetic data is
never shown as LIVE. Same code in the preview sandbox and on the HF Space; only
the badge differs.

### Feeds (license-clean, cited)

| Source | Use | Attribution |
| --- | --- | --- |
| [Open-Meteo Marine](https://marine-api.open-meteo.com/v1/marine?latitude=40.7&longitude=-70.0&hourly=ocean_current_velocity,ocean_current_direction&forecast_days=1) | ocean current velocity/direction | Open-Meteo (CC BY 4.0) |
| [Open-Meteo Wind](https://api.open-meteo.com/v1/forecast?latitude=40.7&longitude=-70.0&hourly=wind_speed_10m,wind_direction_10m&forecast_days=1) | 10 m wind speed/direction | Open-Meteo (CC BY 4.0) |
| [NOAA CO-OPS currents](https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?date=latest&station=cb0102&product=currents&time_zone=gmt&units=metric&format=json) | real-time currents (station cb0102) | NOAA Tides & Currents (U.S. public domain) |

Current speed+direction are converted to 2-D velocity vectors
(`vx = v·sin θ`, `vy = v·cos θ`) sampled over a small lat/lon grid to form a
real velocity field that feeds `yarqa.compartmentalize`.

## Run locally

The package requires Python 3.10 or newer because Pydantic 2.14 does. The Space image and Space CI run on Python 3.11. The other workflows run on Python 3.12.

```bash
pip install -e .                      # the yarqa package (repo root)
pip install -r space/requirements.txt
cd space && python -m uvicorn app:app --port 7860
# open http://localhost:7860
```

## Endpoints

`/healthz` · `/api/feeds` · `/api/compartments` · `/api/agentic` ·
`/api/chain` · `POST /api/chain/verify` · `/api/forecast`

## Provenance

Clean-room. No third-party source copied. THREE.js r160 is vendored verbatim
under its MIT license (`static/lib/three.min.js`). See repo `PROVENANCE.md`.

*SZL Holdings · Apache-2.0 · Doctrine v11.*
