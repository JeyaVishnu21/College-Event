import asyncio
import json
import subprocess
import time
import urllib.request
import websockets
import os
import shutil

async def debug_all():
    print("==================================================")
    print("PART 1 & 2: DEEP ROOT-CAUSE INVESTIGATION")
    print("==================================================")

    user_data_dir = r"C:\Users\vishn\AppData\Local\Temp\edge_debug_user"
    if os.path.exists(user_data_dir):
        try:
            shutil.rmtree(user_data_dir)
        except Exception:
            pass

    edge_cmd = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "--headless=new",
        "--remote-debugging-port=9226",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank"
    ]
    
    proc = subprocess.Popen(edge_cmd)
    try:
        target = None
        for _ in range(12):
            try:
                with urllib.request.urlopen("http://localhost:9226/json") as r:
                    targets = json.loads(r.read().decode())
                    for t in targets:
                        if t.get("type") == "page":
                            target = t
                            break
                    if target:
                        break
            except Exception:
                time.sleep(0.5)

        ws_url = target["webSocketDebuggerUrl"]
        print("Connected to Edge page:", ws_url)

        async with websockets.connect(ws_url) as ws:
            msg_id = 0
            async def send(method, params=None):
                nonlocal msg_id
                msg_id += 1
                payload = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(payload))
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if data.get("id") == msg_id:
                        return data.get("result", {})

            await send("Page.enable")
            await send("Network.enable")
            await send("Runtime.enable")
            await send("Log.enable")

            # Record all network requests & responses
            requests_log = []
            responses_log = []

            async def listen():
                while True:
                    try:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        method = data.get("method")
                        params = data.get("params", {})
                        if method == "Network.requestWillBeSent":
                            req = params.get("request", {})
                            requests_log.append({
                                "url": req.get("url"),
                                "method": req.get("method"),
                                "headers": req.get("headers")
                            })
                            print(f"--> [REQ] {req.get('method')} {req.get('url')}")
                        elif method == "Network.responseReceived":
                            resp = params.get("response", {})
                            responses_log.append({
                                "url": resp.get("url"),
                                "status": resp.get("status"),
                                "headers": resp.get("headers"),
                                "fromDiskCache": resp.get("fromDiskCache"),
                                "fromServiceWorker": resp.get("fromServiceWorker")
                            })
                            sc = resp.get("headers", {}).get("set-cookie", resp.get("headers", {}).get("Set-Cookie", ""))
                            print(f"<-- [RESP] {resp.get('status')} {resp.get('url')} (fromCache: {resp.get('fromDiskCache')}) Set-Cookie: {sc}")
                        elif method == "Runtime.consoleAPICalled":
                            args = [str(a.get('value', '')) for a in params.get('args', [])]
                            print(f"[CONSOLE {params.get('type')}] {' '.join(args)}")
                        elif method == "Page.frameNavigated":
                            frame = params.get("frame", {})
                            if not frame.get("parentId"):
                                print(f"[NAVIGATED TO] {frame.get('url')}")
                    except Exception:
                        break

            listener = asyncio.create_task(listen())

            # -------------------------------------------------------------
            # INVESTIGATION 1: Landing Page CSS & Network
            # -------------------------------------------------------------
            print("\n--------------------------------------------------")
            print("STEP 1: Navigate to http://localhost:3000/")
            print("--------------------------------------------------")
            await send("Page.navigate", {"url": "http://localhost:3000/"})
            await asyncio.sleep(2)

            # Check computed styles for body, h1, nav
            body_bg = await send("Runtime.evaluate", {"expression": "window.getComputedStyle(document.body).backgroundColor"})
            body_bg_img = await send("Runtime.evaluate", {"expression": "window.getComputedStyle(document.body).backgroundImage"})
            body_color = await send("Runtime.evaluate", {"expression": "window.getComputedStyle(document.body).color"})
            print("Computed Body BG:", body_bg.get("result", {}).get("value"))
            print("Computed Body BG Image:", body_bg_img.get("result", {}).get("value"))
            print("Computed Body Color:", body_color.get("result", {}).get("value"))

            # Check stylesheets loaded in document
            sheets = await send("Runtime.evaluate", {"expression": """
                Array.from(document.styleSheets).map(s => ({
                    href: s.href,
                    rulesCount: s.cssRules ? s.cssRules.length : 0
                }))
            """, "returnByValue": True})
            print("Document StyleSheets:", sheets.get("result", {}).get("value"))

            # -------------------------------------------------------------
            # INVESTIGATION 2: Login Flow & Session Cookie
            # -------------------------------------------------------------
            print("\n--------------------------------------------------")
            print("STEP 2: Navigate to http://localhost:3000/login.html")
            print("--------------------------------------------------")
            await send("Page.navigate", {"url": "http://localhost:3000/login.html"})
            await asyncio.sleep(2)

            # Fill credentials and login
            js_login = """
            (async () => {
                document.getElementById('login-email').value = 'debug_user_1@test.com';
                document.getElementById('login-password').value = 'Password123!';
                document.getElementById('btn-login-submit').click();
                return 'Submitted';
            })()
            """
            print("\nSubmitting login with debug_user_1@test.com...")
            await send("Runtime.evaluate", {"expression": js_login, "awaitPromise": True})

            # Monitor for 6 seconds
            for i in range(6):
                await asyncio.sleep(1)
                curr_url = await send("Runtime.evaluate", {"expression": "window.location.href"})
                print(f"T+{i+1}s: {curr_url.get('result', {}).get('value')}")

            # Get cookies for localhost
            cookies = await send("Network.getCookies", {"urls": ["http://localhost:3000", "http://localhost:5000"]})
            print("\nStored Cookies:", json.dumps(cookies.get("cookies", []), indent=2))

            listener.cancel()
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(debug_all())
