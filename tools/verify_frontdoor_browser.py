#!/usr/bin/env python3
"""Render the exact static Yarqa sources without starting its API or fetching feeds.

HTTP responses are explicit local UNAVAILABLE fixtures. Successful, hostile and
failed response paints use an in-memory API replacement; no simulation, receipt
verification, feed fetch or operational POST is executed.

Setup is declared in .github/requirements/frontdoor-browser.lock (QA only, never
the Space runtime) plus `python -m playwright install chromium`. A missing
dependency or browser is reported as an incomplete, failing result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 768, 1280, 1920)
ICON_SHA = "6e2b7d72a3af3d9602b79de41df0194ede6496a9661f057108ec224c0efc92e6"
ASSETS = ("index.html", "style.css", "js/app.js", "lib/three.min.js",
          "szl-space-hologram.css", "szl-space-hologram.js")
SETUP = ("python -m pip install --require-hashes -r .github/requirements/frontdoor-browser.lock"
         " && python -m playwright install chromium")
# Short-height mobile viewports: landscape phone and an on-screen-keyboard proxy.
SHORT_VIEWPORTS = ((667, 320), (390, 300))
# Boot watchdog delay in app.js (API_TIMEOUT_MS + 1500), shortened in one fixture.
WATCHDOG_MS = 9500
LOADER_STATE = """() => {const l=document.querySelector('#loader');return {exposed:l.getAttribute('role')==='status'
  &&!l.hidden&&l.getAttribute('aria-hidden')!=='true',hidden:l.hidden,display:getComputedStyle(l).display,
  ariaHidden:l.getAttribute('aria-hidden')==='true',role:l.hasAttribute('role'),inert:l.inert,
  focusable:l.querySelectorAll('a,button,input,[tabindex]').length,
  health:document.querySelector('#hdot').className}}"""


def _dismissed(state: dict) -> bool:
    return (state["hidden"] and state["display"] == "none" and state["ariaHidden"]
            and not state["role"] and state["inert"] and state["focusable"] == 0)


def _incomplete(output: Path, error: str, exit_code: int = 2) -> int:
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "complete": False, "passed": False,
              "error": error, "setup": SETUP}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": False, "complete": False, "error": error}))
    return exit_code


def _settle_loader(page, timeout: int = 15000) -> None:
    """Wait for dismissal to start, then briefly for its end; a missing end is recorded, not raised."""
    page.wait_for_function("document.querySelector('#loader').classList.contains('hidden')", timeout=timeout, polling=100)
    try:
        page.wait_for_function("document.querySelector('#loader').hidden", timeout=2000, polling=100)
    except Exception:  # Playwright TimeoutError: LOADER_STATE then reports the loader as still exposed.
        pass


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _incomplete(output, f"Playwright is not installed ({exc.name}); run: {SETUP}")
    try:
        return _observe(output, sync_playwright)
    except Exception as exc:  # An aborted observation is incomplete and failing, never a partial pass.
        first = (str(exc).splitlines() or [""])[0][:300]
        return _incomplete(output, f"qualification aborted: {type(exc).__name__}: {first}", exit_code=1)


def _observe(output: Path, sync_playwright) -> int:
    files = {"/" + name: (ROOT / "space/static" / name).read_bytes() for name in ASSETS}
    files["/"] = files["/index.html"]
    requests, writes, outside, errors = [], [], [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            requests.append(path)
            if path in files:
                body = files[path]
                self.send_response(200)
                if path in ("/", "/index.html"):
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                elif path in ("/style.css", "/szl-space-hologram.css"):
                    self.send_header("Content-Type", "text/css; charset=utf-8")
                else:
                    self.send_header("Content-Type", "text/javascript; charset=utf-8")
            else:
                body = b'{"state":"UNAVAILABLE","error":"local presentation fixture; no API started"}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            writes.append(self.path)
            self.send_error(405)

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    report = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "scope": "LOCAL_SOURCE_PRESENTATION_ONLY_NO_API_FEEDS_OR_OPERATIONAL_ACTIONS",
              "source_hashes": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()},
              "cases": []}
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH"),
                                        args=["--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        except Exception as exc:  # A missing or incompatible browser is a setup failure, never a pass.
            server.shutdown()
            server.server_close()
            return _incomplete(output, f"Chromium could not start ({type(exc).__name__}); run: {SETUP}")
        report["browser_version"] = browser.version
        context = browser.new_context(reduced_motion="reduce")

        def intercept(route):
            if route.request.method != "GET":
                writes.append(route.request.url)
                route.abort()
            elif route.request.url.startswith(origin + "/"):
                route.continue_()
            else:
                outside.append(route.request.url)
                route.abort()

        context.route("**/*", intercept)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 1000})
            page.goto(origin, wait_until="domcontentloaded")
            _settle_loader(page)
            loader = page.evaluate(LOADER_STATE)
            loader["dismissed"] = _dismissed(loader) and "initializing yarqa" not in page.locator("body").aria_snapshot()
            page.keyboard.press("Tab")
            skip_first = page.evaluate("document.activeElement.hasAttribute('data-szl-space-skip')")
            page.keyboard.press("Enter")
            skip_focus = page.evaluate("document.activeElement.id==='main'")
            initial = page.evaluate("""() => ({
              unavailable:document.querySelector('#flowBadge').textContent==='UNAVAILABLE',
              sceneHidden:document.querySelector('#scene').hidden,
              noDuplicateShell:document.querySelectorAll('szl-space-ecosystem-bar').length===0,
              paused:Flow.motionPaused,
              labels:[...document.querySelectorAll('input')].every(e=>e.labels.length>0)
            })""")
            # Explicit SAMPLE values are a local UI fixture, not a computed result.
            page.evaluate("""async () => {
              window.originalApi=api;
              window.flowFixture={state:'SAMPLE',n_compartments:2,receipt_digest:'LOCAL_UI_FIXTURE_NOT_A_RECEIPT',
                nx:2,ny:2,centers:[[0,0],[1,0],[0,1],[1,1]],velocities:[[0.2,0.3],[0.3,0.2],[0.4,0.2],[0.2,0.4]],labels:[0,0,1,1],
                top_compartments:[{id:0,n_cells:2,mean_velocity:[0.25,0.25]},{id:1,n_cells:2,mean_velocity:[0.3,0.3]}]};
              api=async()=>window.flowFixture;
              await Flow.refresh();
            }""")
            page.locator("#scene").focus()
            before = page.evaluate("Flow.group.rotation.y")
            page.keyboard.press("ArrowRight")
            orbit_key = page.evaluate("Flow.group.rotation.y") > before
            angle = page.evaluate("Flow.group.rotation.y")
            page.wait_for_timeout(100)
            reduced_still = page.evaluate("Flow.group.rotation.y") == angle
            page.locator(".flow-data summary").focus()
            page.keyboard.press("Space")
            disclosure = page.locator(".flow-data").evaluate("element=>element.open")
            page.locator(".flow-data .table-region").focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(150)
            table_scroll = page.locator(".flow-data .table-region").evaluate("e=>e.scrollWidth<=e.clientWidth||e.scrollLeft>0")
            if width <= 860:
                page.locator("#fab").click()
                menu_focus = page.evaluate("document.activeElement.matches('.sheet-item[data-go=flow]')&&document.querySelector('#main').inert")
                page.locator(".sheet-sources a").last.focus()
                page.keyboard.press("Tab")
                trap = page.evaluate("document.activeElement.id==='closeSheet'")
                page.keyboard.press("Escape")
                escape = page.evaluate("document.querySelector('#sheet').hidden&&document.activeElement.id==='fab'&&!document.querySelector('#main').inert")
                page.locator("#fab").click()
                page.locator(".sheet-item[data-go=forecast]").click()
                select = page.evaluate("document.activeElement.id==='panel-forecast'&&document.querySelector('#sheet').hidden&&document.querySelector('#tab-forecast').getAttribute('aria-selected')==='true'")
            else:
                page.locator("#tab-flow").focus()
                page.keyboard.press("End")
                menu_focus = page.evaluate("document.activeElement.id==='tab-live'")
                page.keyboard.press("Home")
                trap = page.evaluate("document.activeElement.id==='tab-flow'")
                page.keyboard.press("ArrowRight")
                page.keyboard.press("Space")
                escape = page.evaluate("document.querySelector('#tab-agent').getAttribute('aria-selected')==='true'")
                select = page.evaluate("document.querySelectorAll('.tab[aria-selected=true]').length===1")
            # Each tab is painted with a failed response through an in-memory helper.
            page.evaluate("() => {api=async()=>{throw new Error('LOCAL unavailable response fixture')}}")
            layouts = []
            for tab in ("flow", "agent", "chain", "forecast", "live"):
                page.evaluate("tab=>activate(tab)", tab)
                page.wait_for_timeout(60)
                layout = page.evaluate("""() => {
                  const shown=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
                  const targets=[...document.querySelectorAll('.panel.is-active button,.panel.is-active summary,.panel.is-active input,.topbar a')].filter(shown);
                  return {tab:document.body.dataset.tab,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                    small:targets.filter(e=>e.getBoundingClientRect().height<43.5).map(e=>e.id||e.className),
                    overflow:[...document.querySelectorAll('.topbar,.side,.content,.panel.is-active .feed,.panel.is-active .table-region')].filter(e=>shown(e)&&e.getBoundingClientRect().right>innerWidth+1).map(e=>e.className),
                    surface:getComputedStyle(document.querySelector('.panel.is-active .content,.panel.is-active .side')).backgroundColor};
                }""")
                layouts.append(layout)
            page.evaluate("activate('flow')")
            page.locator("#panel-flow").evaluate("element=>element.scrollTop=0")
            if width in (320, 1280):
                page.evaluate("() => {document.activeElement.blur();document.querySelectorAll('.table-region').forEach(e=>{e.scrollLeft=0})}")
                page.screenshot(path=str(output / f"yarqa-{width}.png"), full_page=False)
            report["cases"].append({"width": width,"loader_dismissed":loader["dismissed"],"skip_first":skip_first,"skip_focus":skip_focus,
              "initial":initial,"orbit_key":orbit_key,"reduced_still":reduced_still,"disclosure":disclosure,
              "table_scroll":table_scroll,"nav_focus":menu_focus,"nav_trap_or_home":trap,
              "nav_escape_or_activation":escape,"nav_select":select,"layouts":layouts})
        # Resize closure: an open mobile sheet crossing to desktop hands focus to
        # the visible selected tab, and keyboard navigation continues there.
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("activate('flow')")
        page.locator("#fab").click()
        page.keyboard.press("Tab")
        in_sheet = page.evaluate("document.querySelector('#sheet').contains(document.activeElement)")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(100)
        resize = page.evaluate("""() => {const a=document.activeElement;return {
          sheetHidden:document.querySelector('#sheet').hidden&&document.querySelector('#sheetBackdrop').hidden,
          backgroundActive:!document.querySelector('#main').inert&&!document.querySelector('.tabs').inert,
          selectedTab:a.matches('.tab[aria-selected=true]'),visible:a.getClientRects().length>0,
          outline:getComputedStyle(a).outlineWidth}}""")
        resize["inSheetBefore"] = in_sheet
        page.keyboard.press("ArrowRight")
        resize["keyboardContinues"] = page.evaluate("document.activeElement.id==='tab-agent'")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(100)
        page.locator("#fab").click()
        page.keyboard.press("Escape")
        resize["mobileEscape"] = page.evaluate("document.querySelector('#sheet').hidden&&document.activeElement.id==='fab'&&document.activeElement.getClientRects().length>0")
        # Short-height sheet: Close, every workspace and the last source link are
        # reachable by scrolling and by keyboard, without horizontal overflow.
        short = []
        for width, height in SHORT_VIEWPORTS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)
            page.evaluate("activate('flow')")
            page.locator("#fab").click()
            page.wait_for_timeout(50)
            geometry = page.evaluate("""() => {const s=document.querySelector('#sheet'),r=s.getBoundingClientRect(),
              inView=e=>{const b=e.getBoundingClientRect();return b.top>=r.top-1&&b.bottom<=r.bottom+1&&b.top>=-1&&b.bottom<=innerHeight+1};
              return {fits:r.top>=-1&&r.bottom<=innerHeight+1,scrollable:s.scrollHeight>s.clientHeight&&getComputedStyle(s).overflowY==='auto',
                closeAtTop:inView(document.querySelector('#closeSheet')),
                noOverflow:document.documentElement.scrollWidth<=innerWidth+1&&s.scrollWidth<=s.clientWidth+1}}""")
            page.mouse.move(width // 2, height - 20)
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(150)
            geometry.update(page.evaluate("""() => {const s=document.querySelector('#sheet'),r=s.getBoundingClientRect(),
              a=[...s.querySelectorAll('.sheet-sources a')].pop().getBoundingClientRect(),c=document.querySelector('#closeSheet').getBoundingClientRect();
              return {wheelReachesEnd:s.scrollTop>0&&a.bottom<=r.bottom+1&&a.bottom<=innerHeight+1,
                closeStaysVisible:c.top>=r.top-1&&c.bottom<=innerHeight+1}}"""))
            page.evaluate("document.querySelector('#sheet').scrollTop=0")
            controls = page.locator("#sheet button, #sheet a[href]")
            reachable = []
            for index in range(controls.count()):
                controls.nth(index).focus()
                reachable.append(page.evaluate("""() => {const s=document.querySelector('#sheet').getBoundingClientRect(),
                  b=document.activeElement.getBoundingClientRect();return b.top>=s.top-1&&b.bottom<=s.bottom+1&&b.bottom<=innerHeight+1}"""))
            page.keyboard.press("Tab")
            geometry["trapToClose"] = page.evaluate("document.activeElement.id==='closeSheet'")
            geometry["keyboardReach"] = len(reachable) >= 9 and all(reachable)
            page.keyboard.press("Escape")
            short.append({"width": width, "height": height, **geometry})
        page.set_viewport_size({"width": 1280, "height": 1000})
        sinks = page.evaluate("""async () => {
          const hostile='<img src=x onerror="window.__injected=true">';
          api=async()=>({any_live:false,sources:{one:{state:'UNKNOWN',name:hostile,detail:hostile,
            speed_ms:1,direction_deg:1,fetched_utc:hostile,attribution:hostile,error:hostile,
            url:'javascript:window.__injected=true',license_url:'data:text/html,unsafe'}}});
          await Live.refresh();
          const root=document.querySelector('#feedCards');
          const feed={markup:root.querySelectorAll('img,script,[onerror],a').length,
            literal:root.textContent.includes('<img'),unknown:root.querySelector('.badge').textContent==='UNAVAILABLE',
            invalidLinks:root.querySelectorAll('.invalid-link').length};
          const failures=[];api=async()=>{throw new Error('LOCAL failure fixture')};
          for(const method of ['verify','tamper']){
            Chain.json=JSON.stringify({links:[{}]});document.querySelector('#chainVerdict').className='verdict ok';
            await Chain[method]();failures.push({method,unavailable:document.querySelector('#chainVerdict').className==='verdict unavailable',cleared:Chain.json===null});
          }
          api=async()=>window.flowFixture;const init=Flow.init;
          Flow.ready=false;Flow.init=()=>{throw new Error('LOCAL WebGL unavailable')};await Flow.refresh();
          const fallback=document.querySelector('#flowBadge').textContent==='SAMPLE'&&document.querySelector('#scene').hidden&&document.querySelector('#flowTable').textContent.includes('0.2500');
          Flow.init=init;api=window.originalApi;
          return {feed,failures,fallback,injected:!!window.__injected};
        }""")
        deadline = page.evaluate("""async () => {
          const oldFetch=fetch,oldTimer=setTimeout;let aborted=false,delay=null;
          window.setTimeout=(fn,ms,...args)=>{delay=ms;return oldTimer(fn,ms===8000?1:ms,...args)};
          window.fetch=(_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('LOCAL deadline'))},{once:true}));
          try{await api('/local-layout-fixture');return {aborted,delay,rejected:false}}
          catch(_){return {aborted,delay,rejected:true}}
          finally{window.fetch=oldFetch;window.setTimeout=oldTimer}
        }""")
        page.emulate_media(forced_colors="active")
        page.locator("[data-szl-space-skip]").focus()
        forced = page.evaluate("""() => ({outline:getComputedStyle(document.activeElement).outlineWidth,
          surface:getComputedStyle(document.querySelector('.side')).backgroundColor,
          image:getComputedStyle(document.querySelector('.side')).backgroundImage})""")
        icon = re.search(rb'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600".*?</svg>', files["/"], re.S)
        loaders = []
        for motion in ("reduce", "no-preference"):
            fixture = browser.new_context(reduced_motion=motion)

            def stall(route):
                if route.request.method != "GET":
                    writes.append(route.request.url)
                    route.abort()
                elif not route.request.url.startswith(origin + "/"):
                    outside.append(route.request.url)
                    route.abort()
                elif urlsplit(route.request.url).path == "/healthz":
                    return  # Never answered: boot stays pending, so only the watchdog can dismiss.
                else:
                    route.continue_()

            fixture.route("**/*", stall)
            fixture.add_init_script("(()=>{const t=window.setTimeout;window.__yarqaDelays=[];window.setTimeout=(f,ms,...a)=>"
                                    "{window.__yarqaDelays.push(ms);return t(f,ms===%d?1200:ms,...a)}})();" % WATCHDOG_MS)
            watch = fixture.new_page()
            watch.on("pageerror", lambda error: errors.append(str(error)))
            row = {"motion": motion, "initially_exposed": False, "dismissed_by_watchdog": False}
            try:
                watch.goto(origin, wait_until="domcontentloaded")
                before = watch.evaluate(LOADER_STATE)
                row["initially_exposed"] = before["exposed"]
                _settle_loader(watch, timeout=10000)
                after = watch.evaluate(LOADER_STATE)
                row["dismissed_by_watchdog"] = (_dismissed(after) and after["health"] == before["health"]
                                                and "ok" not in after["health"].split() and "bad" not in after["health"].split())
            except Exception as exc:  # Recorded as a failed case with diagnostics, not an aborted run.
                row["error"] = f"{type(exc).__name__}: {(str(exc).splitlines() or [''])[0][:200]}"
            try:
                row["scheduled_delays"] = watch.evaluate("window.__yarqaDelays.slice(0,20)")
                row["loader"] = watch.evaluate(LOADER_STATE)
            except Exception:
                pass
            loaders.append(row)
            fixture.unroute_all(behavior="ignoreErrors")  # Release the intentionally stalled request.
            fixture.close()
        report.update(sinks=sinks, deadline=deadline, forced_colors=forced, resize_focus=resize,
                      short_height=short, loader_watchdog=loaders,
                      exact_native_icon=icon is not None and hashlib.sha256(icon.group(0)+b"\n").hexdigest()==ICON_SHA)
        browser.close()
    server.shutdown()
    server.server_close()
    report.update(page_errors=errors, attempted_writes=writes, blocked_external_requests=outside, request_paths=sorted(set(requests)))
    passed = report["exact_native_icon"] and not errors and not writes and not outside
    for case in report["cases"]:
        passed = passed and all(case[key] for key in ("loader_dismissed","skip_first","skip_focus","orbit_key","reduced_still","disclosure","table_scroll","nav_focus","nav_trap_or_home","nav_escape_or_activation","nav_select"))
        passed = passed and all(case["initial"].values())
        passed = passed and all(not row["small"] and not row["overflow"] and row["scrollWidth"]<=row["width"]+1 and row["surface"]=="rgb(17, 23, 34)" for row in case["layouts"])
    passed = passed and not sinks["injected"] and sinks["feed"]["markup"]==0 and sinks["feed"]["literal"] and sinks["feed"]["unknown"] and sinks["feed"]["invalidLinks"]==2 and sinks["fallback"]
    passed = passed and all(item["unavailable"] and item["cleared"] for item in sinks["failures"])
    passed = passed and deadline=={"aborted":True,"delay":8000,"rejected":True} and forced["outline"]=="3px" and forced["image"]=="none"
    passed = passed and all(resize[key] for key in ("inSheetBefore","sheetHidden","backgroundActive","selectedTab","visible","keyboardContinues","mobileEscape")) and resize["outline"] == "3px"
    passed = passed and len(short) == len(SHORT_VIEWPORTS) and all(all(value for key, value in row.items() if key not in ("width", "height")) for row in short)
    passed = passed and len(loaders) == 2 and all(row["initially_exposed"] and row["dismissed_by_watchdog"] for row in loaders)
    report["complete"] = True
    report["passed"] = bool(passed)
    (output / "results.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"complete":True,"widths":len(report["cases"]),"short_height":len(short),"loader_fixtures":len(loaders),"page_errors":len(errors),"writes":len(writes),"external":len(outside),"report":str(output / "results.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
