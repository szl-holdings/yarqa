# Yarqa native frontdoor

The served page is `space/static/index.html`, returned by `space/app.py` and
included by `space/Dockerfile`'s existing `COPY space/`. `style.css` and
`js/app.js` remain its local stylesheet and browser controller.

## Identity and reading surfaces

The interface projects the accepted KANCHAY graphite, silver and teal palette
from `szl-brand@27d12e77fc0f9f1a0e5fae8b34adf2380d51d070`. Reading surfaces are
opaque, with restrained foil edges. The original Yarqa flow glyph remains the
product mark; the SZL endorsement is the exact native Orbit suite SVG, displayed
at 40px. Its source SHA-256 is
`6e2b7d72a3af3d9602b79de41df0194ede6496a9661f057108ec224c0efc92e6`.
The page provides source and CC BY 4.0 artwork attribution; software stays
Apache-2.0. This is a native palette projection, not a full-bundle installation.

The admitted `szl-space-hologram.css` and `.js` bytes are unchanged. The existing
`data-szl-space-no-shell` option prevents their duplicate shadow header from
covering Yarqa's fixed product header. Native header/menu links retain source
and ecosystem access. Native CSS binds the shared ambience to the accepted
palette and hides the skip link until focused even under reduced motion.

## Interaction and evidence

Desktop tabs expose selected state, a single tab stop and named panels;
Left/Right/Home/End move focus, while native Enter/Space activates. The mobile
dialog sets background content inert, keeps keyboard focus inside, returns
focus on Escape and moves focus to the selected workspace. Zoom is unrestricted.
Controls have explicit labels, usable hit areas and forced-color focus.

The Flow view renders the API's `top_compartments` summary in a keyboard-scrollable
native table. Returned numerical evidence remains visible if WebGL fails, while
the unavailable renderer is labeled separately. Keyboard orbit, a rotation
toggle, reduced-motion preference and hidden-tab pause support the 3D view.
Replacing geometry disposes the old GPU resources. Compartment calculations,
routing scores, forecast fit and receipt payloads remain the existing API's work.

Response text is escaped and source links accept only absolute HTTP(S) URLs
without embedded credentials. Unknown feed states remain UNAVAILABLE. Failed
flow/forecast requests clear stale results; failed chain verification clears the
old intact verdict and chain. Existing verify/tamper POST method, endpoint and
JSON expressions are unchanged. No new operational action is introduced.

## Qualification

Run the source suite with `python -m pytest -q tests`, and the shipped browser
fixtures with `node --test tests/space_availability.test.cjs`. The qualified local
source passed 134 Python tests, with two optional skips, and 18 Node response
fixtures. The full Python invocation denied network transport before imports and
recorded zero unmocked transport attempts.

`tools/verify_frontdoor_browser.py --output <new-directory>` serves only the six
static files over loopback. Every HTTP API response is an explicit unavailable
fixture. Successful, hostile and failure paints use an in-memory response helper;
the verifier does not start the Space app, fetch public feeds or submit actions.
All five widths—320, 390, 768, 1280 and 1920px—passed keyboard, containment, contrast
surface, SVG identity, mobile dialog, WebGL fallback and timeout checks, with zero
page errors, attempted writes or external requests. The review workspace retains
the final report and screenshots at `hf_live_2026_10_11/yarqa-browser-qualified`.

## Publication

The sole `.github/workflows/hf-space.yml` writer remains pinned to reusable
deployer `1b3255219cd1d5fa7ac850195b18fc907cac2cbf`. It publishes exact accepted
main, derives the payload from the Dockerfile, preserves the separately owned
Space card (`include-readme:false`), and retains credential, restart, source
binding and immutable/runtime readback gates. Local presentation proof does not
establish a published runtime or scientific correctness.
