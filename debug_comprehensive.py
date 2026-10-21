import asyncio
import json
import subprocess
import time
import urllib.request
import websockets
import os
import shutil

async def run_diagnostics():
    print("==========================================================")
    print("STARTING COMPREHENSIVE ROOT-CAUSE DIAGNOSTICS")
    print("==========================================================")

    user_data_dir = r"C:\Users\vishn\AppData\Local\Temp\edge_debug_comp"
    if os.path.exists(user_data_dir):
        try:
            shutil.rmtree(user_data_dir)
        except Exception:
            pass

    edge_cmd = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "--headless=new",
        "--remote-debugging-port=9228",
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
                with urllib.request.urlopen("http://localhost:9228/json") as r:
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
            events_log = []

            async def router():
                while True:
                    try:
                        raw = await ws.recv()
                        data = json.loads(raw)
                        if "id" in data and data["id"] in pending_responses:
                            pending_responses[data["id"]].set_result(data.get("result", {}))
                        else:
                            events_log.append(data)
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

            await send("Page.enable")
            await send("Network.enable")
            await send("Runtime.enable")
            await send("Log.enable")

            # -------------------------------------------------------------
            # PART 1: DIAGNOSE LANDING PAGE (http://localhost:3000/)
            # -------------------------------------------------------------
            print("\n----------------------------------------------------------")
            print("PART 1: VERIFYING http://localhost:3000/")
            print("----------------------------------------------------------")
            events_log.clear()
            await send("Page.navigate", {"url": "http://localhost:3000/"})
            await asyncio.sleep(2)

            # Check network requests for style.css
            css_requests = []
            css_responses = []
            for ev in events_log:
                method = ev.get("method")
                params = ev.get("params", {})
                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url", "")
                    if "style.css" in url:
                        css_requests.append(params.get("request"))
                elif method == "Network.responseReceived":
                    url = params.get("response", {}).get("url", "")
                    if "style.css" in url:
                        css_responses.append(params.get("response"))

            print(f"1. style.css requested: {len(css_requests)} times")
            if css_requests:
                print(f"   Request URL: {css_requests[0].get('url')}")
            if css_responses:
                resp = css_responses[0]
                print(f"2 & 3. HTTP status of style.css: {resp.get('status')}")
                print(f"   MIME type: {resp.get('mimeType')}")
                print(f"   fromDiskCache: {resp.get('fromDiskCache')}")
                print(f"   fromServiceWorker: {resp.get('fromServiceWorker')}")
                print(f"   Response Headers: {json.dumps(resp.get('headers', {}), indent=2)}")

            # Check console errors
            console_errors = []
            for ev in events_log:
                if ev.get("method") == "Runtime.consoleAPICalled" and ev.get("params", {}).get("type") == "error":
                    console_errors.append(ev.get("params", {}).get("args"))
                elif ev.get("method") == "Log.entryAdded" and ev.get("params", {}).get("entry", {}).get("level") == "error":
                    console_errors.append(ev.get("params", {}).get("entry", {}).get("text"))

            print(f"5. Console errors: {console_errors}")

            # Check physical file existence & path
            referenced_href = await send("Runtime.evaluate", {"expression": "document.querySelector('link[rel=stylesheet]') ? document.querySelector('link[rel=stylesheet]').href : 'none'"})
            print(f"6. Referenced CSS href in DOM: {referenced_href.get('result', {}).get('value')}")
            
            # Check computed styles for key sections
            computed = await send("Runtime.evaluate", {"expression": """
                ({
                    body: {
                        bgColor: window.getComputedStyle(document.body).backgroundColor,
                        bgImage: window.getComputedStyle(document.body).backgroundImage,
                        color: window.getComputedStyle(document.body).color,
                        fontFamily: window.getComputedStyle(document.body).fontFamily
                    },
                    nav: {
                        exists: Boolean(document.querySelector('.institutional-nav')),
                        bgColor: document.querySelector('.institutional-nav') ? window.getComputedStyle(document.querySelector('.institutional-nav')).backgroundColor : null,
                        height: document.querySelector('.institutional-nav') ? window.getComputedStyle(document.querySelector('.institutional-nav')).height : null
                    },
                    hero: {
                        exists: Boolean(document.querySelector('.hero-section')),
                        headingColor: document.querySelector('.hero-heading') ? window.getComputedStyle(document.querySelector('.hero-heading')).color : null,
                        headingSize: document.querySelector('.hero-heading') ? window.getComputedStyle(document.querySelector('.hero-heading')).fontSize : null,
                        gridDisplay: document.querySelector('.hero-grid') ? window.getComputedStyle(document.querySelector('.hero-grid')).display : null,
                        gridCols: document.querySelector('.hero-grid') ? window.getComputedStyle(document.querySelector('.hero-grid')).gridTemplateColumns : null
                    },
                    buttons: {
                        primaryBg: document.querySelector('.btn-primary') ? window.getComputedStyle(document.querySelector('.btn-primary')).backgroundColor : null,
                        borderRadius: document.querySelector('.btn-primary') ? window.getComputedStyle(document.querySelector('.btn-primary')).borderRadius : null
                    },
                    features: {
                        exists: Boolean(document.querySelector('.features-section')),
                        cardCount: document.querySelectorAll('.feature-box').length,
                        cardBg: document.querySelector('.feature-box') ? window.getComputedStyle(document.querySelector('.feature-box')).backgroundColor : null,
                        cardBorder: document.querySelector('.feature-box') ? window.getComputedStyle(document.querySelector('.feature-box')).borderColor : null
                    },
                    workflow: {
                        exists: Boolean(document.querySelector('.workflow-section')),
                        stepCount: document.querySelectorAll('.workflow-step-card').length,
                        stepBg: document.querySelector('.workflow-step-card') ? window.getComputedStyle(document.querySelector('.workflow-step-card')).backgroundColor : null
                    },
                    portals: {
                        exists: Boolean(document.querySelector('.portals-section')),
                        gridCols: document.querySelector('.portals-grid') ? window.getComputedStyle(document.querySelector('.portals-grid')).gridTemplateColumns : null
                    },
                    footer: {
                        bgColor: document.querySelector('.institutional-footer') ? window.getComputedStyle(document.querySelector('.institutional-footer')).backgroundColor : null
                    }
                })
            """, "returnByValue": True})
            print("Computed Styles Analysis:\n", json.dumps(computed.get("result", {}).get("value"), indent=2))

            # -------------------------------------------------------------
            # PART 2: DIAGNOSE LOGIN FLOW & REDIRECT
            # -------------------------------------------------------------
            print("\n----------------------------------------------------------")
            print("PART 2: TRACING LOGIN & REDIRECT FLOW ON http://localhost:3000/login.html")
            print("----------------------------------------------------------")
            events_log.clear()
            await send("Page.navigate", {"url": "http://localhost:3000/login.html"})
            await asyncio.sleep(2)

            # Check config.js values
            config_val = await send("Runtime.evaluate", {"expression": """
                (async () => {
                    const m = await import('./js/config.js');
                    return m.CONFIG;
                })()
            """, "awaitPromise": True, "returnByValue": True})
            print("Active CONFIG in browser:\n", json.dumps(config_val.get("result", {}).get("value"), indent=2))

            # Clear event log before form submit
            events_log.clear()

            js_submit_login = """
            (async () => {
                document.getElementById('login-email').value = 'vishnu@gmail.com';
                document.getElementById('login-password').value = 'password123';
                document.getElementById('btn-login-submit').click();
                return 'Submitted';
            })()
            """
            print("Attempting login with vishnu@gmail.com...")
            res_submit = await send("Runtime.evaluate", {"expression": js_submit_login, "awaitPromise": True, "returnByValue": True})
            print("Submit eval result:", res_submit)

            # Observe sequence for 6 seconds
            for s in range(6):
                await asyncio.sleep(1)
                u = await send("Runtime.evaluate", {"expression": "window.location.href"})
                print(f"Second {s+1}: URL = {u.get('result', {}).get('value')}")

            # Print network sequence
            print("\nNetwork Sequence Recorded:")
            for ev in events_log:
                method = ev.get("method")
                params = ev.get("params", {})
                if method == "Network.requestWillBeSent":
                    req = params.get("request", {})
                    print(f"  --> {req.get('method')} {req.get('url')}")
                elif method == "Network.responseReceived":
                    resp = params.get("response", {})
                    sc = resp.get("headers", {}).get("set-cookie", resp.get("headers", {}).get("Set-Cookie", ""))
                    print(f"  <-- {resp.get('status')} {resp.get('url')} | Set-Cookie: {sc}")
                elif method == "Page.frameNavigated" and not params.get("frame", {}).get("parentId"):
                    print(f"  [FRAME NAVIGATED] -> {params.get('frame', {}).get('url')}")

            # Inspect all cookies
            all_cookies = await send("Network.getCookies")
            print("\nBrowser Cookie Store:\n", json.dumps(all_cookies.get("cookies", []), indent=2))

            router_task.cancel()
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
