"""
Test both localhost and 127.0.0.1 flows in Headless Edge.
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

TEMP_PROFILE = r"C:\Users\vishn\.gemini\antigravity-ide\brain\5cdfc43b-0577-4e96-a1a5-4f24723d11e8\scratch\edge_profile_hosts"

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

    async def navigate(self, url, wait_sec=2):
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

async def test_flow(host_name, email, password, expected_role, expected_page):
    print(f"\n{'='*70}\nTESTING HOSTNAME: {host_name} (User: {email}, Role: {expected_role})\n{'='*70}")
    page, tid = await create_page()
    try:
        login_url = f"http://{host_name}:3000/login.html"
        print(f"1. Navigating to {login_url}")
        await page.navigate(login_url, wait_sec=2)

        # Check config.js resolved API_BASE_URL
        api_url = await page.eval_json("import('./js/config.js').then(m => m.CONFIG.API_BASE_URL)")
        print(f"2. CONFIG.API_BASE_URL on {host_name}: {api_url}")

        # Fill and submit login
        page.events.clear()
        await page.eval_json(f"""
        (() => {{
            document.getElementById('login-email').value = '{email}';
            document.getElementById('login-password').value = '{password}';
            document.getElementById('btn-login-submit').click();
            return 'submitted';
        }})()
        """)
        print(f"3. Submitted login form for {email}")

        # Wait 5 seconds
        await asyncio.sleep(5)

        # Inspect network calls
        for ev in page.events:
            if ev.get("method") == "Network.responseReceived":
                resp = ev["params"]["response"]
                if "api" in resp["url"] or ".html" in resp["url"]:
                    hdrs = resp.get("headers", {})
                    print(f"   [{resp['status']}] {resp['url']}")
                    if "set-cookie" in hdrs:
                        print(f"        Set-Cookie: {hdrs['set-cookie']}")

        # Check current URL and DOM
        state = await page.eval_json("""
        {
            url: window.location.href,
            title: document.title,
            userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null
        }
        """)
        print(f"4. Result after 5s:")
        print(f"   URL: {state.get('url')}")
        print(f"   Title: {state.get('title')}")
        print(f"   User: {state.get('userName')}")

        success = expected_page in state.get('url', '')
        print(f"5. Stayed on {expected_page}: {'PASS' if success else 'FAIL (REDIRECTED BACK)'}")

        # Test refresh
        if success:
            print(f"6. Testing page refresh...")
            page.events.clear()
            await page.navigate(state.get('url'), wait_sec=3)
            refreshed_state = await page.eval_json("""
            {
                url: window.location.href,
                userName: document.getElementById('user-display-name') ? document.getElementById('user-display-name').textContent : null
            }
            """)
            print(f"   URL after refresh: {refreshed_state.get('url')}")
            print(f"   User after refresh: {refreshed_state.get('userName')}")
            print(f"   Refresh persistence: {'PASS' if expected_page in refreshed_state.get('url', '') else 'FAIL'}")

            # Test logout
            print(f"7. Testing logout...")
            page.events.clear()
            await page.eval_json("""
            (() => {
                const btn = document.getElementById('btn-logout');
                if (btn) btn.click();
                return 'logout clicked';
            })()
            """)
            await asyncio.sleep(2)
            logout_state = await page.eval_json("window.location.href")
            print(f"   URL after logout: {logout_state}")
            print(f"   Logout redirect: {'PASS' if 'login.html' in logout_state else 'FAIL'}")

    finally:
        await page.close()
        await close_page(tid)

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
        # Test 1: localhost with organizer
        await test_flow("localhost", "debug_user_1@test.com", "Password123!", "organizer", "organizer.html")

        # Test 2: 127.0.0.1 with organizer
        await test_flow("127.0.0.1", "debug_user_1@test.com", "Password123!", "organizer", "organizer.html")

        # Test 3: localhost with management
        await test_flow("localhost", "test_mgmt_verify@college.edu", "Password123!", "management", "management.html")

        # Test 4: 127.0.0.1 with management
        await test_flow("127.0.0.1", "test_mgmt_verify@college.edu", "Password123!", "management", "management.html")

    finally:
        edge_proc.terminate()
        try:
            edge_proc.wait(timeout=3)
        except Exception:
            edge_proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
