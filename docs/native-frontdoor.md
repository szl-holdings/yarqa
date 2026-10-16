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
focus on Escape and moves focus to the selected workspace. On short viewports the
dialog scrolls inside its own envelope with the Close heading kept in view;
the body never scrolls. If the window widens past 860px while the dialog is
open, the dialog closes, background inertness clears and focus moves to the
selected desktop tab with a visible ring (the menu button is hidden there).
Zoom is unrestricted. Controls have explicit labels, usable hit areas and
forced-color focus.

The startup loader is a `role=status` only while it is visible. Normal
completion and the boot watchdog share one dismissal path that removes the
role, marks it `aria-hidden` and inert, then ends the fade with `hidden`
(immediately under reduced motion).

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

The browser verifier's dependencies are declared separately from the Space
runtime in `.github/requirements/frontdoor-browser.in` and its hash lock:

```bash
python -m venv .qa-venv
.qa-venv/bin/python -m pip install --require-hashes -r .github/requirements/frontdoor-browser.lock
.qa-venv/bin/python -m playwright install chromium
.qa-venv/bin/python -I tools/verify_frontdoor_browser.py --output <new-directory>
```

`CHROME_PATH` may name a compatible local Chromium instead. A missing
dependency or browser, or an aborted observation, writes `complete: false`,
`passed: false` and exits nonzero; reuse of an old output directory is refused.
`.github/workflows/frontdoor-browser.yml` runs the same steps on every pull
request and main push and keeps the report and screenshots as an artifact.

`tools/verify_frontdoor_browser.py --output <new-directory>` serves only the six
static files over loopback. Every HTTP API response is an explicit unavailable
fixture. Successful, hostile and failure paints use an in-memory response helper;
the verifier does not start the Space app, fetch public feeds or submit actions.
All five widths—320, 390, 768, 1280 and 1920px—passed keyboard, containment, contrast
surface, SVG identity, mobile dialog, WebGL fallback and timeout checks, with zero
page errors, attempted writes or external requests. The review workspace retains
the final report and screenshots at `hf_live_2026_10_11/yarqa-browser-qualified`.

Later cases cover the dismissed loader at every width, a boot watchdog
dismissal with `/healthz` held open (reduced and full motion), the 390→1280px
resize focus hand-off and continued arrow-key navigation, and the sheet at
667×320 and 390×300: Close, all five workspaces and the last source link are
reachable by wheel scrolling and by keyboard, with no horizontal overflow.
Reduced viewports are a keyboard-height proxy, not a real-device keyboard test.

The same sheets are rerun on an emulated touch phone with positive safe-area
insets set through DevTools `Emulation.setSafeAreaInsetsOverride`: 390×300 with
a 47px top and 34px bottom inset, and 667×320 landscape with 47px side insets.
With the shared stylesheet loaded, each case checks the computed cap
(`innerHeight - 12px - top inset`), the sheet's top clearance, every sheet
control inside the side insets, and that the sticky Close stays hit-testable and
keyboard-reachable after wheel scrolling to the end. The sheet's inline padding
grows to the side insets for this. The desktop-tab case uses only real input:
Flow is selected, ArrowRight roves to the unselected Agent tab, the sheet opens
by pointer at 390px and the window widens to 1280px. It requires focus and a 3px
ring on the selected tab, exactly one tablist stop counted with real Tab presses,
Tab out of the tablist and Shift+Tab back, under reduced and full motion. A
further loader fixture patches no timer: every API request stays unanswered, so
the app's own 9500ms watchdog must dismiss the loader after the real 8000ms
deadline fails `/healthz` and while the Flow request is still pending. Emulated
insets are not a real-device notch test.

## Publication

The sole `.github/workflows/hf-space.yml` writer remains pinned to reusable
deployer `1b3255219cd1d5fa7ac850195b18fc907cac2cbf`. It publishes exact accepted
main, derives the payload from the Dockerfile, preserves the separately owned
Space card (`include-readme:false`), and retains credential, restart, source
binding and immutable/runtime readback gates. Local presentation proof does not
establish a published runtime or scientific correctness.
