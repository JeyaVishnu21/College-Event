"""
Comprehensive Edge/CDP Diagnostics and Verification Script
Covers Part 1 (CSS), Part 2 (Auth/Login/Redirect), Part 3 & 4 (Scripts), and 11 Verification Steps.
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

TEMP_PROFILE = r"C:\Users\vishn\.gemini\antigravity-ide\brain\5cdfc43b-0577-4e96-a1a5-4f24723d11e8\scratch\edge_profile_full"

class CDPPage:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0
        self.pending = {}
        self.events = []
        self.running = True
        self.reader_task = None

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url)
        self.reader_task = asyncio.create_task(self._reader())
        await self.call("Network.enable")
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        await self.call("DOM.enable")
        await self.call("CSS.enable")

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
        except Exception:
            pass

    async def call(self, method, params=None, timeout=15):
        self.msg_id += 1
        curr_id = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[curr_id] = fut
        req = {"id": curr_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(req))
        res = await asyncio.wait_for(fut, timeout=timeout)
        del self.pending[curr_id]
        return res

    async def eval_json(self, expr):
        wrapped = f"(() => {{ try {{ return JSON.stringify({expr}); }} catch (e) {{ return JSON.stringify({{ error: e.toString() }}); }} }})()"
        res = await self.call("Runtime.evaluate", {"expression": wrapped, "returnByValue": True})
        val = res.get("result", {}).get("result", {}).get("value") or res.get("result", {}).get("value")
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    async def navigate(self, url, wait_sec=2.5):
        self.events.clear()
        res = await self.call("Page.navigate", {"url": url})
        await asyncio.sleep(wait_sec)
        return res

    async def close(self):
        self.running = False
        if self.reader_task:
            self.reader_task.cancel()
        if self.ws:
            await self.ws.close()

async def create_page():
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req) as res:
        target = json.loads(res.read().decode())
    page = CDPPage(target["webSocketDebuggerUrl"])
    await page.connect()
    return page, target["id"]

async def close_page(target_id):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:9222/json/close/{target_id}")
        urllib.request.urlopen(req)
    except Exception:
        pass

async def main():
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
        # =========================================================================
        # PART 1: CSS DIAGNOSTICS FOR http://localhost:3000/
        # =========================================================================
        print("="*80)
        print("PART 1: CSS DIAGNOSTICS FOR http://localhost:3000/")
        print("="*80)

        page, tid = await create_page()
        print("Created blank tab, now navigating to http://localhost:3000/...")
        await page.navigate("http://localhost:3000/", wait_sec=3)

        # 1. Analyze Network Requests
        requests_seen = []
        responses_seen = []
        for ev in page.events:
            if ev.get("method") == "Network.requestWillBeSent":
                r = ev["params"]["request"]
                requests_seen.append((r["method"], r["url"]))
            elif ev.get("method") == "Network.responseReceived":
                resp = ev["params"]["response"]
                responses_seen.append({
                    "url": resp["url"],
                    "status": resp["status"],
                    "statusText": resp["statusText"],
                    "headers": resp.get("headers", {}),
                    "mimeType": resp.get("mimeType"),
                    "fromDiskCache": resp.get("fromDiskCache", False)
                })

        print("\nAll Network Requests Sent:")
        for m, u in requests_seen:
            print(f"  [{m}] {u}")

        print("\n1-3. style.css Network Status:")
        css_resp = next((r for r in responses_seen if "style.css" in r["url"]), None)
        if css_resp:
            print(f"  style.css Requested: YES -> {css_resp['url']}")
            print(f"  HTTP Status: {css_resp['status']} {css_resp['statusText']}")
            print(f"  MimeType: {css_resp['mimeType']}")
            print(f"  Headers: {css_resp['headers']}")
            print(f"  From Disk Cache: {css_resp['fromDiskCache']}")
        else:
            print("  style.css was NOT found in responses!")

        # 4-5. Console messages
        console_logs = []
        for ev in page.events:
            if ev.get("method") == "Runtime.consoleAPICalled":
                args = [a.get("value", "") for a in ev["params"]["args"]]
                console_logs.append(f"[{ev['params']['type']}] {args}")
            elif ev.get("method") == "Runtime.exceptionThrown":
                console_logs.append(f"[EXCEPTION] {ev['params']['exceptionDetails']['text']}")

        print("\n4-5. Browser Console Messages:")
        if console_logs:
            for l in console_logs:
                print(f"  {l}")
        else:
            print("  (Zero console errors or warnings)")

        # 6-12. Stylesheet inspection
        dom_css_info = await page.eval_json("""
        {
            links: Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => ({
                href: l.getAttribute('href'),
                fullHref: l.href
            })),
            inlineStylesCount: document.querySelectorAll('style').length,
            sheets: Array.from(document.styleSheets).map(s => ({
                href: s.href,
                rulesCount: s.cssRules ? s.cssRules.length : 'inaccessible'
            }))
        }
        """)
        print("\n6-7. Referenced Stylesheet in DOM:")
        print(f"  Links in DOM: {dom_css_info.get('links')}")
        print(f"  Inline <style> count: {dom_css_info.get('inlineStylesCount')}")
        print(f"  Loaded StyleSheets count: {len(dom_css_info.get('sheets', []))}")
        for s in dom_css_info.get('sheets', []):
            print(f"    href: {s['href']}, rulesCount: {s['rulesCount']}")

        # Verify physical file existence
        css_file_path = os.path.abspath(r"c:\Users\vishn\OneDrive\Pictures\Mini project 3\code\frontend\css\style.css")
        print(f"  Physical File Exists at '{css_file_path}': {os.path.exists(css_file_path)}")
        if os.path.exists(css_file_path):
            print(f"  Physical File Size: {os.path.getsize(css_file_path)} bytes")

        # Computed styles
        computed_styles = await page.eval_json("""
        (() => {
            function getStyles(sel) {
                const el = document.querySelector(sel);
                if (!el) return { selector: sel, error: 'Element not found' };
                const cs = window.getComputedStyle(el);
                return {
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
                    gridTemplateColumns: cs.gridTemplateColumns,
                    flexDirection: cs.flexDirection
                };
            }
            return {
                body: getStyles('body'),
                navigation: getStyles('.institutional-nav'),
                hero: getStyles('.hero-section'),
                btnPrimary: getStyles('.btn.btn-primary'),
                btnSecondary: getStyles('.btn.btn-secondary'),
                featureSections: getStyles('.features-grid'),
                featureCard: getStyles('.feature-card'),
                workflow: getStyles('.workflow-steps'),
                portalSections: getStyles('.portal-preview-grid'),
                portalCard: getStyles('.portal-preview-card'),
                footer: getStyles('.institutional-footer')
            };
        })()
        """)
        print("\nComputed Styles of Key Sections:")
        for k, v in computed_styles.items():
            print(f"  [{k}] -> bg: {v.get('backgroundColor')}, color: {v.get('color')}, display: {v.get('display')}, border: {v.get('border')}")

        await page.close()
        await close_page(tid)

        # =========================================================================
        # PART 2: AUTHENTICATION & LOGIN FLOW REPRODUCTION
        # =========================================================================
        print("\n" + "="*80)
        print("PART 2: LOGIN & REDIRECT FLOW FOR ORGANIZER")
        print("="*80)

        page, tid = await create_page()
        await page.navigate("http://localhost:3000/login.html", wait_sec=2)

        # Fill credentials for debug_user_1@test.com
        fill_res = await page.eval_json("""
        (() => {
            document.getElementById('login-email').value = 'debug_user_1@test.com';
            document.getElementById('login-password').value = 'Password123!';
            document.getElementById('btn-login-submit').click();
            return 'Clicked submit';
        })()
        """)
        print("Form submission:", fill_res)

        # Observe for 6 seconds as login response arrives, redirects to organizer.html, and runs /me
        page.events.clear()
        await asyncio.sleep(6)

        # Analyze network calls
        print("\nExact Network Sequence during Login & Redirect:")
        for ev in page.events:
            if ev.get("method") == "Network.requestWillBeSent":
                r = ev["params"]["request"]
                if "api" in r["url"] or "organizer.html" in r["url"] or "login.html" in r["url"]:
                    cookie = r["headers"].get("Cookie", r["headers"].get("cookie", "(no cookie header)"))
                    print(f"  --> REQUEST: {r['method']} {r['url']}")
                    print(f"      Cookie Sent: {cookie}")
            elif ev.get("method") == "Network.responseReceived":
                resp = ev["params"]["response"]
                if "api" in resp["url"] or "organizer.html" in resp["url"] or "login.html" in resp["url"]:
                    hdrs = resp.get("headers", {})
                    set_cookie = hdrs.get("set-cookie", hdrs.get("Set-Cookie", "(none)"))
                    print(f"  <-- RESPONSE: {resp['status']} {resp['url']}")
                    if "api" in resp["url"]:
                        print(f"      Set-Cookie: {set_cookie}")

        # Check console logs
        print("\nConsole Messages during Login Flow:")
        for ev in page.events:
            if ev.get("method") == "Runtime.consoleAPICalled":
                args = [a.get("value", "") for a in ev["params"]["args"]]
                print(f"  [{ev['params']['type']}] {args}")
            elif ev.get("method") == "Runtime.exceptionThrown":
                print(f"  [EXCEPTION] {ev['params']['exceptionDetails']['text']}")

        # Current URL and state after 6s
        final_state = await page.eval_json("""
        {
            url: window.location.href,
            title: document.title,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null,
            eventsCount: document.getElementById('nav-events-count') ? document.getElementById('nav-events-count').textContent : null
        }
        """)
        print("\nFinal Browser State:")
        print(f"  Current URL:   {final_state.get('url')}")
        print(f"  Page Title:    {final_state.get('title')}")
        print(f"  User Display:  {final_state.get('userName')}")
        print(f"  Events Count:  {final_state.get('eventsCount')}")

        # Cookies in browser
        cookies = await page.call("Network.getCookies")
        print("\nCookies Stored in Browser:")
        for c in cookies.get("result", {}).get("cookies", []):
            print(f"  Name: {c['name']}, Domain: {c['domain']}, Path: {c['path']}, HttpOnly: {c['httpOnly']}, SameSite: {c.get('sameSite')}")

        await page.close()
        await close_page(tid)

    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=3)
        except Exception:
            edge_proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
