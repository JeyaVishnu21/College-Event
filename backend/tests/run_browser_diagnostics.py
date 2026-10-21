"""
Robust Edge/CDP Diagnostics Script for Part 1 & Part 2
Using single receive loop for CDP events and method responses.
"""

import subprocess
import time
import json
import urllib.request
import asyncio
import os
import shutil
import websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE_PATH):
    EDGE_PATH = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

TEMP_PROFILE = r"C:\Users\vishn\.gemini\antigravity-ide\brain\5cdfc43b-0577-4e96-a1a5-4f24723d11e8\scratch\edge_profile"

class CDPClient:
    def __init__(self, ws):
        self.ws = ws
        self.msg_id = 0
        self.pending = {}
        self.events = []
        self.running = True
        self.reader_task = asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            while self.running:
                raw = await self.ws.recv()
                data = json.loads(raw)
                if "id" in data:
                    req_id = data["id"]
                    if req_id in self.pending:
                        self.pending[req_id].set_result(data)
                else:
                    self.events.append(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            # print("Reader error:", e)
            pass

    async def call(self, method, params=None, timeout=10):
        self.msg_id += 1
        curr_id = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[curr_id] = fut
        req = {"id": curr_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(req))
        res = await asyncio.wait_for(fut, timeout=timeout)
        del self.pending[curr_id]
        return res

    async def close(self):
        self.running = False
        self.reader_task.cancel()
        await self.ws.close()

async def run_diagnostics():
    if os.path.exists(TEMP_PROFILE):
        try:
            shutil.rmtree(TEMP_PROFILE)
        except Exception:
            pass
    os.makedirs(TEMP_PROFILE, exist_ok=True)

    edge_proc = subprocess.Popen([
        EDGE_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        f"--user-data-dir={TEMP_PROFILE}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check"
    ])

    time.sleep(2)

    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json") as res:
            targets = json.loads(res.read().decode())
        ws_url = targets[0]["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url)

        async with websockets.connect(ws_url) as ws:
            client = CDPClient(ws)

            # Enable Network, Page, Runtime
            await client.call("Network.enable")
            await client.call("Page.enable")
            await client.call("Runtime.enable")

            # -------------------------------------------------------------
            # PART 1: TEST http://localhost:3000/
            # -------------------------------------------------------------
            print("\n" + "="*70)
            print("PART 1: TESTING http://localhost:3000/")
            print("="*70)

            client.events.clear()
            nav_res = await client.call("Page.navigate", {"url": "http://localhost:3000/"})
            print("Navigating... result:", nav_res)

            # Wait 3 seconds for all assets to load
            await asyncio.sleep(3)

            # Collect requests, responses, console logs
            reqs = []
            resps = []
            console_logs = []
            for ev in client.events:
                method = ev.get("method")
                if method == "Network.requestWillBeSent":
                    r = ev["params"]["request"]
                    reqs.append((r["method"], r["url"]))
                elif method == "Network.responseReceived":
                    resp = ev["params"]["response"]
                    resps.append((resp["status"], resp["url"], resp.get("mimeType"), resp.get("headers", {})))
                elif method == "Runtime.consoleAPICalled":
                    args = [a.get("value", "") for a in ev["params"]["args"]]
                    console_logs.append(f"[{ev['params']['type']}] {args}")
                elif method == "Runtime.exceptionThrown":
                    console_logs.append(f"[EXCEPTION] {ev['params']['exceptionDetails']['text']}")

            print("\n--- Network Requests Sent (Total: {}) ---".format(len(reqs)))
            for m, u in reqs:
                print(f"  {m} {u}")

            print("\n--- Network Responses Received (Total: {}) ---".format(len(resps)))
            for status, u, mime, hdrs in resps:
                print(f"  {status} {u} ({mime})")

            print("\n--- Console Logs ---")
            if console_logs:
                for c in console_logs:
                    print(f"  {c}")
            else:
                print("  (Zero console messages/errors)")

            # Check computed styles for body, navigation, hero, buttons, feature sections, workflow, portal sections, footer
            eval_code = """
            (() => {
                function comp(sel) {
                    const el = document.querySelector(sel);
                    if (!el) return { found: false, selector: sel };
                    const cs = window.getComputedStyle(el);
                    return {
                        found: true,
                        selector: sel,
                        tagName: el.tagName,
                        backgroundColor: cs.backgroundColor,
                        color: cs.color,
                        display: cs.display,
                        fontFamily: cs.fontFamily,
                        fontSize: cs.fontSize,
                        padding: cs.padding,
                        margin: cs.margin,
                        borderRadius: cs.borderRadius,
                        boxShadow: cs.boxShadow,
                        border: cs.border,
                        width: cs.width,
                        gridTemplateColumns: cs.gridTemplateColumns,
                        flexDirection: cs.flexDirection
                    };
                }

                return {
                    body: comp('body'),
                    navigation: comp('.institutional-nav'),
                    brandTitles: comp('.brand-titles'),
                    hero: comp('.hero-section'),
                    heroGrid: comp('.hero-grid'),
                    heroHeading: comp('.hero-heading'),
                    btnPrimary: comp('.btn.btn-primary'),
                    btnSecondary: comp('.btn.btn-secondary'),
                    featureSections: comp('.features-grid'),
                    featureCard: comp('.feature-card'),
                    workflow: comp('.workflow-steps'),
                    portalSections: comp('.portal-preview-grid'),
                    portalCard: comp('.portal-preview-card'),
                    footer: comp('.institutional-footer'),
                    styleSheets: Array.from(document.styleSheets).map(s => ({ href: s.href, cssRulesCount: s.cssRules ? s.cssRules.length : 'cross-origin' })),
                    inlineStyles: Array.from(document.querySelectorAll('style')).map(s => s.textContent.trim().substring(0, 50))
                };
            })()
            """
            eval_res = await client.call("Runtime.evaluate", {"expression": eval_code, "returnByValue": True})
            styles = eval_res.get("result", {}).get("value", {})
            print("\n--- Computed Styles in Browser ---")
            print(json.dumps(styles, indent=2))

            # -------------------------------------------------------------
            # PART 2: TEST LOGIN & REDIRECT FLOW
            # -------------------------------------------------------------
            print("\n" + "="*70)
            print("PART 2: TESTING LOGIN & REDIRECT AT http://localhost:3000/login.html")
            print("="*70)

            client.events.clear()
            await client.call("Page.navigate", {"url": "http://localhost:3000/login.html"})
            await asyncio.sleep(2)

            login_action = """
            (() => {
                const emailInput = document.getElementById('login-email');
                const passInput = document.getElementById('login-password');
                const btn = document.getElementById('btn-login-submit');
                if (!emailInput || !passInput || !btn) return 'Form elements not found';
                emailInput.value = 'debug_user_1@test.com';
                passInput.value = 'Password123!';
                btn.click();
                return 'Submitted login for debug_user_1@test.com';
            })()
            """
            act_res = await client.call("Runtime.evaluate", {"expression": login_action, "returnByValue": True})
            print("Action Result:", act_res.get("result", {}).get("value"))

            # Track activity for 5 seconds post-submit
            await asyncio.sleep(5)

            # Analyze events during login and navigation
            login_reqs = []
            login_resps = []
            login_console = []
            for ev in client.events:
                method = ev.get("method")
                if method == "Network.requestWillBeSent":
                    r = ev["params"]["request"]
                    login_reqs.append({
                        "method": r["method"],
                        "url": r["url"],
                        "headers": r.get("headers", {})
                    })
                elif method == "Network.responseReceived":
                    resp = ev["params"]["response"]
                    login_resps.append({
                        "status": resp["status"],
                        "url": resp["url"],
                        "headers": resp.get("headers", {})
                    })
                elif method == "Runtime.consoleAPICalled":
                    args = [a.get("value", "") for a in ev["params"]["args"]]
                    login_console.append(f"[{ev['params']['type']}] {args}")
                elif method == "Runtime.exceptionThrown":
                    login_console.append(f"[EXCEPTION] {ev['params']['exceptionDetails']['text']}")

            print("\n--- Network Requests during Login & Navigation ---")
            for req in login_reqs:
                auth_header = req["headers"].get("Authorization", "(none)")
                cookie_header = req["headers"].get("Cookie", req["headers"].get("cookie", "(none)"))
                print(f"  {req['method']} {req['url']}")
                if "api" in req["url"]:
                    print(f"       -> Cookie sent in request: {cookie_header}")

            print("\n--- Network Responses during Login & Navigation ---")
            for resp in login_resps:
                hdrs = resp["headers"]
                set_cookie = hdrs.get("set-cookie") or hdrs.get("Set-Cookie") or "(none)"
                print(f"  {resp['status']} {resp['url']}")
                if "api" in resp["url"]:
                    print(f"       -> Set-Cookie: {set_cookie}")
                    print(f"       -> Access-Control-Allow-Origin: {hdrs.get('access-control-allow-origin', '(none)')}")
                    print(f"       -> Access-Control-Allow-Credentials: {hdrs.get('access-control-allow-credentials', '(none)')}")

            print("\n--- Console Logs during Login & Navigation ---")
            if login_console:
                for c in login_console:
                    print(f"  {c}")
            else:
                print("  (Zero console messages/errors)")

            cur_url = await client.call("Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
            cur_title = await client.call("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
            print(f"\nPage after 5 seconds:")
            print(f"  Current URL: {cur_url.get('result', {}).get('value')}")
            print(f"  Page Title:  {cur_title.get('result', {}).get('value')}")

            # Check if user display name was rendered if on organizer.html
            dash_check = """
            (() => {
                const nameEl = document.getElementById('user-display-name');
                const statsEl = document.getElementById('stat-total');
                return {
                    nameText: nameEl ? nameEl.textContent : null,
                    statsTotal: statsEl ? statsEl.textContent : null,
                    url: window.location.href
                };
            })()
            """
            dash_res = await client.call("Runtime.evaluate", {"expression": dash_check, "returnByValue": True})
            print("Dashboard DOM check:", dash_res.get("result", {}).get("value"))

            # Get cookies stored in browser
            cookies_res = await client.call("Network.getCookies")
            print("\n--- Cookies Stored in Browser ---")
            print(json.dumps(cookies_res.get("result", {}).get("cookies", []), indent=2))

            await client.close()

    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=3)
        except Exception:
            edge_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
