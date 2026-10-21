import asyncio
import json
import subprocess
import time
import urllib.request
import websockets
import os
import shutil

async def main():
    user_data_dir = r"C:\Users\vishn\AppData\Local\Temp\edge_debug_precise"
    if os.path.exists(user_data_dir):
        try:
            shutil.rmtree(user_data_dir)
        except Exception:
            pass

    edge_cmd = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "--headless=new",
        "--remote-debugging-port=9227",
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
                with urllib.request.urlopen("http://localhost:9227/json") as r:
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

        async with websockets.connect(ws_url) as ws:
            pending_responses = {}
            events_queue = asyncio.Queue()

            async def router():
                while True:
                    try:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        if "id" in data and data["id"] in pending_responses:
                            pending_responses[data["id"]].set_result(data.get("result", {}))
                        else:
                            await events_queue.put(data)
                    except Exception:
                        break

            router_task = asyncio.create_task(router())

            msg_id = 0
            async def send(method, params=None):
                nonlocal msg_id
                msg_id += 1
                fut = asyncio.get_running_loop().create_future()
                pending_responses[msg_id] = fut
                payload = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(payload))
                res = await fut
                del pending_responses[msg_id]
                return res

            async def print_events():
                while True:
                    data = await events_queue.get()
                    method = data.get("method")
                    params = data.get("params", {})
                    if method == "Network.requestWillBeSent":
                        req = params.get("request", {})
                        print(f"--> [REQ] {req.get('method')} {req.get('url')}")
                    elif method == "Network.responseReceived":
                        resp = params.get("response", {})
                        sc = resp.get("headers", {}).get("set-cookie", resp.get("headers", {}).get("Set-Cookie", "none"))
                        print(f"<-- [RESP] {resp.get('status')} {resp.get('url')} | Set-Cookie: {sc}")
                    elif method == "Runtime.consoleAPICalled":
                        args = [str(a.get('value', '')) for a in params.get('args', [])]
                        print(f"[CONSOLE {params.get('type')}] {' '.join(args)}")
                    elif method == "Page.frameNavigated":
                        frame = params.get("frame", {})
                        if not frame.get("parentId"):
                            print(f"[NAVIGATED TO] {frame.get('url')}")
                    elif method == "Log.entryAdded":
                        entry = params.get("entry", {})
                        print(f"[LOG {entry.get('level')}] {entry.get('text')}")

            events_task = asyncio.create_task(print_events())

            await send("Page.enable")
            await send("Network.enable")
            await send("Runtime.enable")
            await send("Log.enable")

            # -------------------------------------------------------------
            # STEP 1: Navigate to http://localhost:3000/
            # -------------------------------------------------------------
            print("\n==========================================")
            print("NAVIGATING TO http://localhost:3000/")
            print("==========================================")
            await send("Page.navigate", {"url": "http://localhost:3000/"})
            await asyncio.sleep(2)

            # Check styles and loaded resources
            state = await send("Runtime.evaluate", {"expression": """
                ({
                    url: window.location.href,
                    readyState: document.readyState,
                    bodyBg: window.getComputedStyle(document.body).backgroundColor,
                    bodyBgImg: window.getComputedStyle(document.body).backgroundImage,
                    bodyColor: window.getComputedStyle(document.body).color,
                    sheets: Array.from(document.styleSheets).map(s => s.href),
                    navBg: document.querySelector('.institutional-nav') ? window.getComputedStyle(document.querySelector('.institutional-nav')).backgroundColor : 'no nav',
                    heroHeadingColor: document.querySelector('.hero-heading') ? window.getComputedStyle(document.querySelector('.hero-heading')).color : 'no heading',
                    heroGridCols: document.querySelector('.hero-grid') ? window.getComputedStyle(document.querySelector('.hero-grid')).gridTemplateColumns : 'no grid'
                })
            """, "returnByValue": True})
            print("STEP 1 STATE:", json.dumps(state.get("result", {}).get("value"), indent=2))

            # -------------------------------------------------------------
            # STEP 2: Navigate to http://localhost:3000/login.html and login
            # -------------------------------------------------------------
            print("\n==========================================")
            print("NAVIGATING TO http://localhost:3000/login.html")
            print("==========================================")
            await send("Page.navigate", {"url": "http://localhost:3000/login.html"})
            await asyncio.sleep(2)

            js_submit = """
            (async () => {
                document.getElementById('login-email').value = 'debug_user_1@test.com';
                document.getElementById('login-password').value = 'Password123!';
                document.getElementById('btn-login-submit').click();
                return 'Clicked Submit';
            })()
            """
            print("Submitting login form...")
            await send("Runtime.evaluate", {"expression": js_submit, "awaitPromise": True})

            # Monitor for 6 seconds
            for i in range(6):
                await asyncio.sleep(1)
                curr = await send("Runtime.evaluate", {"expression": "window.location.href"})
                print(f"Time +{i+1}s URL: {curr.get('result', {}).get('value')}")

            # Get cookies
            cookies = await send("Network.getCookies", {"urls": ["http://localhost:3000", "http://localhost:5000"]})
            print("\nSTORED COOKIES:", json.dumps(cookies.get("cookies", []), indent=2))

            router_task.cancel()
            events_task.cancel()
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
