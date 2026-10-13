#!/usr/bin/env python3
"""Render the exact static Yarqa sources without starting its API or fetching feeds.

HTTP responses are explicit local UNAVAILABLE fixtures. Successful, hostile and
failed response paints use an in-memory API replacement; no simulation, receipt
verification, feed fetch or operational POST is executed.
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 768, 1280, 1920)
ICON_SHA = "6e2b7d72a3af3d9602b79de41df0194ede6496a9661f057108ec224c0efc92e6"
ASSETS = ("index.html", "style.css", "js/app.js", "lib/three.min.js",
          "szl-space-hologram.css", "szl-space-hologram.js")


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
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
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH"),
                                    args=["--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
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
            page.wait_for_function("document.querySelector('#loader').classList.contains('hidden')")
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
            report["cases"].append({"width": width,"skip_first":skip_first,"skip_focus":skip_focus,
              "initial":initial,"orbit_key":orbit_key,"reduced_still":reduced_still,"disclosure":disclosure,
              "table_scroll":table_scroll,"nav_focus":menu_focus,"nav_trap_or_home":trap,
              "nav_escape_or_activation":escape,"nav_select":select,"layouts":layouts})
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
        report.update(sinks=sinks, deadline=deadline, forced_colors=forced,
                      exact_native_icon=icon is not None and hashlib.sha256(icon.group(0)+b"\n").hexdigest()==ICON_SHA)
        browser.close()
    server.shutdown()
    server.server_close()
    report.update(page_errors=errors, attempted_writes=writes, blocked_external_requests=outside, request_paths=sorted(set(requests)))
    passed = report["exact_native_icon"] and not errors and not writes and not outside
    for case in report["cases"]:
        passed = passed and all(case[key] for key in ("skip_first","skip_focus","orbit_key","reduced_still","disclosure","table_scroll","nav_focus","nav_trap_or_home","nav_escape_or_activation","nav_select"))
        passed = passed and all(case["initial"].values())
        passed = passed and all(not row["small"] and not row["overflow"] and row["scrollWidth"]<=row["width"]+1 and row["surface"]=="rgb(17, 23, 34)" for row in case["layouts"])
    passed = passed and not sinks["injected"] and sinks["feed"]["markup"]==0 and sinks["feed"]["literal"] and sinks["feed"]["unknown"] and sinks["feed"]["invalidLinks"]==2 and sinks["fallback"]
    passed = passed and all(item["unavailable"] and item["cleared"] for item in sinks["failures"])
    passed = passed and deadline=={"aborted":True,"delay":8000,"rejected":True} and forced["outline"]=="3px" and forced["image"]=="none"
    report["passed"] = bool(passed)
    (output / "results.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"widths":len(report["cases"]),"page_errors":len(errors),"writes":len(writes),"external":len(outside),"report":str(output / "results.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
