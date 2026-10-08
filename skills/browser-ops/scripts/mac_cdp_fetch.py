#!/usr/bin/env python3
"""Run ON the iMac. Open URLs in a NEW tab of the already-running windowed Chrome (CDP 9334),
wait, run a JS extractor, print JSON per URL, close the tab. Usage: mac_cdp_fetch.py <js_file> <url>...
"""
import json, sys, time, urllib.request
import websocket
CDP = "http://127.0.0.1:9334"
js_src = open(sys.argv[1]).read()
for url in sys.argv[2:]:
    t = json.loads(urllib.request.urlopen(urllib.request.Request(CDP + "/json/new?about:blank", method="PUT"), timeout=10).read())
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
    n = [0]
    def call(m, **p):
        n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == n[0]: return r
    call("Page.enable"); call("Page.navigate", url=url)
    res = None
    for _ in range(20):
        time.sleep(2.5)
        r = call("Runtime.evaluate", expression=js_src, returnByValue=True, awaitPromise=True)
        res = r.get("result", {}).get("result", {}).get("value")
        if res and isinstance(res, dict) and res.get("ready"): break
    print(json.dumps({"url": url, "data": res}))
    sys.stdout.flush()
    ws.close()
    urllib.request.urlopen(CDP + "/json/close/" + t["id"], timeout=10)
    time.sleep(20)
