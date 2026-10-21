import subprocess, time, json, urllib.request, asyncio, websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def test_nav():
    proc = subprocess.Popen([
        EDGE_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check"
    ])
    time.sleep(2)
    try:
        # Create new target
        req = urllib.request.Request("http://127.0.0.1:9222/json/new?http://localhost:3000/", method="PUT")
        with urllib.request.urlopen(req) as res:
            target = json.loads(res.read().decode())
        print("Created target:", target["id"], target["url"])
        ws_url = target["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url) as ws:
            # Enable DOM, Page, Runtime, CSS
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))
            await ws.send(json.dumps({"id": 4, "method": "CSS.enable"}))
            await asyncio.sleep(2)
            
            # Evaluate document.title and CSS rules
            eval_req = {
                "id": 5,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "JSON.stringify({ title: document.title, stylesheets: Array.from(document.styleSheets).map(s => s.href), bodyBg: window.getComputedStyle(document.body).backgroundColor, navBg: window.getComputedStyle(document.querySelector('.institutional-nav') || document.body).backgroundColor })"
                }
            }
            await ws.send(json.dumps(eval_req))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == 5:
                    print("EVAL RESULT:", resp["result"]["result"]["value"])
                    break
    finally:
        proc.terminate()
        proc.wait(timeout=3)

if __name__ == "__main__":
    asyncio.run(test_nav())
