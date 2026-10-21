"""
Comprehensive Verification Script for All 11 Required Test Scenarios
Runs headless Edge and records Network, Console, Computed Styles, and Session States.
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

TEMP_PROFILE = r"C:\Users\vishn\.gemini\antigravity-ide\brain\5cdfc43b-0577-4e96-a1a5-4f24723d11e8\scratch\edge_profile_11_steps"

class CDPClient:
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

async def create_tab():
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req) as res:
        target = json.loads(res.read().decode())
    client = CDPClient(target["webSocketDebuggerUrl"])
    await client.connect()
    return client, target["id"]

async def close_tab(target_id):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:9222/json/close/{target_id}")
        urllib.request.urlopen(req)
    except Exception:
        pass

def inspect_events(events):
    responses = []
    console_errors = []
    four_o_fours = []
    for ev in events:
        if ev.get("method") == "Network.responseReceived":
            resp = ev["params"]["response"]
            url = resp["url"]
            status = resp["status"]
            responses.append((status, url))
            if status == 404:
                four_o_fours.append(url)
        elif ev.get("method") == "Runtime.consoleAPICalled":
            t = ev["params"]["type"]
            args = [a.get("value", "") for a in ev["params"]["args"]]
            if t in ["error", "warning"]:
                console_errors.append(f"[{t}] {args}")
        elif ev.get("method") == "Runtime.exceptionThrown":
            console_errors.append(f"[EXCEPTION] {ev['params']['exceptionDetails']['text']}")
    return responses, console_errors, four_o_fours

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

    results = {}

    try:
        # =========================================================================
        # 1. LOCALHOST HOMEPAGE
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 1: LOCALHOST HOMEPAGE (http://localhost:3000/)")
        print("="*80)
        tab, tid = await create_tab()
        await tab.navigate("http://localhost:3000/", wait_sec=2.5)
        resps, errs, four04s = inspect_events(tab.events)
        styles = await tab.eval_json("""
        {
            bodyBg: window.getComputedStyle(document.body).backgroundColor,
            navBg: window.getComputedStyle(document.querySelector('.institutional-nav') || document.body).backgroundColor,
            btnColor: window.getComputedStyle(document.querySelector('.btn-primary') || document.body).backgroundColor,
            heroGridDisplay: window.getComputedStyle(document.querySelector('.hero-grid') || document.body).display,
            featuresDisplay: window.getComputedStyle(document.querySelector('.features-grid') || document.body).display
        }
        """)
        css_ok = any("style.css" in u and s == 200 for s, u in resps)
        js_ok = any("app.js" in u and s == 200 for s, u in resps)
        print(f"  CSS 200 OK: {css_ok}")
        print(f"  JS 200 OK: {js_ok}")
        print(f"  404 Errors: {four04s}")
        print(f"  Console Errors: {errs}")
        print(f"  Computed Styles: {styles}")
        results["1. localhost homepage"] = {
            "css_200": css_ok, "js_200": js_ok, "no_404s": len(four04s) == 0,
            "no_errors": len(errs) == 0, "styles": styles
        }
        await tab.close()
        await close_tab(tid)

        # =========================================================================
        # 2. 127.0.0.1 HOMEPAGE
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 2: 127.0.0.1 HOMEPAGE (http://127.0.0.1:3000/)")
        print("="*80)
        tab, tid = await create_tab()
        await tab.navigate("http://127.0.0.1:3000/", wait_sec=2.5)
        resps, errs, four04s = inspect_events(tab.events)
        styles = await tab.eval_json("""
        {
            bodyBg: window.getComputedStyle(document.body).backgroundColor,
            navBg: window.getComputedStyle(document.querySelector('.institutional-nav') || document.body).backgroundColor
        }
        """)
        css_ok = any("style.css" in u and s == 200 for s, u in resps)
        js_ok = any("app.js" in u and s == 200 for s, u in resps)
        print(f"  CSS 200 OK: {css_ok}")
        print(f"  JS 200 OK: {js_ok}")
        print(f"  404 Errors: {four04s}")
        print(f"  Console Errors: {errs}")
        print(f"  Computed Styles: {styles}")
        results["2. 127.0.0.1 homepage"] = {
            "css_200": css_ok, "js_200": js_ok, "no_404s": len(four04s) == 0,
            "no_errors": len(errs) == 0
        }
        await tab.close()
        await close_tab(tid)

        # =========================================================================
        # 3. LOGIN PAGE
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 3: LOGIN PAGE (http://localhost:3000/login.html)")
        print("="*80)
        tab, tid = await create_tab()
        await tab.navigate("http://localhost:3000/login.html", wait_sec=2.5)
        resps, errs, four04s = inspect_events(tab.events)
        css_ok = any("style.css" in u and s == 200 for s, u in resps)
        js_ok = any("auth.js" in u and s == 200 for s, u in resps)
        print(f"  CSS 200 OK: {css_ok}")
        print(f"  JS 200 OK: {js_ok}")
        print(f"  404 Errors: {four04s}")
        print(f"  Console Errors: {errs}")
        results["3. login page"] = {
            "css_200": css_ok, "js_200": js_ok, "no_404s": len(four04s) == 0,
            "no_errors": len(errs) == 0
        }

        # =========================================================================
        # 4. ORGANIZER LOGIN
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 4: ORGANIZER LOGIN (debug_user_1@test.com)")
        print("="*80)
        tab.events.clear()
        await tab.eval_json("""
        (() => {
            document.getElementById('login-email').value = 'debug_user_1@test.com';
            document.getElementById('login-password').value = 'Password123!';
            document.getElementById('btn-login-submit').click();
            return 'submitted';
        })()
        """)
        await asyncio.sleep(5)
        resps, errs, four04s = inspect_events(tab.events)
        login_resp = next(((s, u) for s, u in resps if "/api/auth/login" in u), None)
        print(f"  POST /api/auth/login response: {login_resp}")
        results["4. organizer login"] = {"status": login_resp[0] if login_resp else None}

        # =========================================================================
        # 5. ORGANIZER DASHBOARD
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 5: ORGANIZER DASHBOARD (organizer.html)")
        print("="*80)
        state = await tab.eval_json("""
        {
            url: window.location.href,
            title: document.title,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null,
            dashTabDisplay: document.getElementById('tab-dashboard') ? window.getComputedStyle(document.getElementById('tab-dashboard')).display : null
        }
        """)
        stayed = "organizer.html" in state.get("url", "")
        print(f"  URL: {state.get('url')}")
        print(f"  User Display: {state.get('userName')}")
        print(f"  Dashboard Open: {stayed}")
        results["5. organizer dashboard"] = {"stayed": stayed, "user": state.get("userName")}

        # =========================================================================
        # 6. ORGANIZER DASHBOARD REFRESH
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 6: ORGANIZER DASHBOARD REFRESH")
        print("="*80)
        tab.events.clear()
        await tab.navigate("http://localhost:3000/organizer.html", wait_sec=3)
        resps, errs, four04s = inspect_events(tab.events)
        refr_state = await tab.eval_json("""
        {
            url: window.location.href,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null
        }
        """)
        refr_stayed = "organizer.html" in refr_state.get("url", "")
        print(f"  URL after refresh: {refr_state.get('url')}")
        print(f"  User after refresh: {refr_state.get('userName')}")
        print(f"  Refresh persisted: {refr_stayed}")
        results["6. organizer dashboard refresh"] = {"persisted": refr_stayed}

        # =========================================================================
        # 7. ORGANIZER LOGOUT
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 7: ORGANIZER LOGOUT")
        print("="*80)
        tab.events.clear()
        await tab.eval_json("""
        (() => {
            document.getElementById('btn-logout').click();
            return 'logout clicked';
        })()
        """)
        await asyncio.sleep(2)
        logout_url = await tab.eval_json("window.location.href")
        logout_ok = "login.html" in logout_url
        print(f"  URL after logout: {logout_url}")
        print(f"  Redirected to login.html: {logout_ok}")
        results["7. organizer logout"] = {"redirected_to_login": logout_ok}

        # =========================================================================
        # 8. MANAGEMENT LOGIN
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 8: MANAGEMENT LOGIN (test_mgmt_verify@college.edu)")
        print("="*80)
        tab.events.clear()
        await tab.eval_json("""
        (() => {
            document.getElementById('login-email').value = 'test_mgmt_verify@college.edu';
            document.getElementById('login-password').value = 'Password123!';
            document.getElementById('btn-login-submit').click();
            return 'submitted';
        })()
        """)
        await asyncio.sleep(5)
        resps, errs, four04s = inspect_events(tab.events)
        mgmt_login_resp = next(((s, u) for s, u in resps if "/api/auth/login" in u), None)
        print(f"  POST /api/auth/login response: {mgmt_login_resp}")
        results["8. management login"] = {"status": mgmt_login_resp[0] if mgmt_login_resp else None}

        # =========================================================================
        # 9. MANAGEMENT DASHBOARD
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 9: MANAGEMENT DASHBOARD (management.html)")
        print("="*80)
        mgmt_state = await tab.eval_json("""
        {
            url: window.location.href,
            title: document.title,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null
        }
        """)
        mgmt_stayed = "management.html" in mgmt_state.get("url", "")
        print(f"  URL: {mgmt_state.get('url')}")
        print(f"  User Display: {mgmt_state.get('userName')}")
        print(f"  Management Dashboard Open: {mgmt_stayed}")
        results["9. management dashboard"] = {"stayed": mgmt_stayed, "user": mgmt_state.get("userName")}

        # =========================================================================
        # 10. MANAGEMENT DASHBOARD REFRESH
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 10: MANAGEMENT DASHBOARD REFRESH")
        print("="*80)
        tab.events.clear()
        await tab.navigate("http://localhost:3000/management.html", wait_sec=3)
        mgmt_refr = await tab.eval_json("""
        {
            url: window.location.href,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null
        }
        """)
        mgmt_refr_stayed = "management.html" in mgmt_refr.get("url", "")
        print(f"  URL after refresh: {mgmt_refr.get('url')}")
        print(f"  User after refresh: {mgmt_refr.get('userName')}")
        print(f"  Refresh persisted: {mgmt_refr_stayed}")
        results["10. management dashboard refresh"] = {"persisted": mgmt_refr_stayed}

        # =========================================================================
        # 11. MANAGEMENT LOGOUT
        # =========================================================================
        print("\n" + "="*80)
        print("STEP 11: MANAGEMENT LOGOUT")
        print("="*80)
        tab.events.clear()
        await tab.eval_json("""
        (() => {
            document.getElementById('btn-logout').click();
            return 'logout clicked';
        })()
        """)
        await asyncio.sleep(2)
        mgmt_logout_url = await tab.eval_json("window.location.href")
        mgmt_logout_ok = "login.html" in mgmt_logout_url
        print(f"  URL after logout: {mgmt_logout_url}")
        print(f"  Redirected to login.html: {mgmt_logout_ok}")
        results["11. management logout"] = {"redirected_to_login": mgmt_logout_ok}

        await tab.close()
        await close_tab(tid)

        print("\n" + "="*80)
        print("ALL 11 TEST RESULTS SUMMARY:")
        print("="*80)
        print(json.dumps(results, indent=2))

    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=3)
        except Exception:
            edge_proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
