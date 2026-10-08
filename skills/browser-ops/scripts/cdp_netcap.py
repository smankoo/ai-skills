#!/usr/bin/env python3
"""Run ON the iMac (CDP 9334 windowed Chrome). Navigate one URL in a new tab with Network enabled and dump
every fetch/XHR whose URL matches a regex: method, request headers, POST body, status, and the first
N bytes of the response body. Recon tool for finding a site's own JSON API.

Usage: costco-venv/bin/python cdp_netcap.py <url> <url_regex> [max_body_chars]
"""
import json, re, sys, time, urllib.request
import websocket
CDP = "http://127.0.0.1:9334"
url, pat = sys.argv[1], re.compile(sys.argv[2])
maxb = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
t = json.loads(urllib.request.urlopen(urllib.request.Request(CDP + "/json/new?about:blank", method="PUT"), timeout=10).read())
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
n = [0]; events = []
def send(m, **p):
    n[0] += 1; ws.send(json.dumps({"id": n[0], "method": m, "params": p})); return n[0]
def call(m, **p):
    i = send(m, **p)
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == i: return r
        events.append(r)
call("Network.enable", maxPostDataSize=65536); call("Page.enable"); call("Page.navigate", url=url)
reqs = {}
end = time.time() + 25
ws.settimeout(2)
while time.time() < end:
    try: events.append(json.loads(ws.recv()))
    except Exception: pass
    while events:
        e = events.pop(0); m = e.get("method"); p = e.get("params", {})
        if m == "Network.requestWillBeSent" and pat.search(p["request"]["url"]):
            reqs[p["requestId"]] = {"url": p["request"]["url"], "method": p["request"]["method"],
                                    "headers": p["request"].get("headers"), "post": p["request"].get("postData")}
        elif m == "Network.requestWillBeSentExtraInfo" and p.get("requestId") in reqs:
            reqs[p["requestId"]]["extra_headers"] = {k: v for k, v in p.get("headers", {}).items() if k.lower() != "cookie"}
        elif m == "Network.responseReceived" and p.get("requestId") in reqs:
            reqs[p["requestId"]]["status"] = p["response"]["status"]
ws.settimeout(30)
for rid, r in reqs.items():
    try:
        b = call("Network.getResponseBody", requestId=rid).get("result", {})
        r["body"] = (b.get("body") or "")[:maxb]; r["body_len"] = len(b.get("body") or "")
    except Exception as ex:
        r["body_err"] = str(ex)[:100]
    print(json.dumps(r)); sys.stdout.flush()
ws.close()
urllib.request.urlopen(CDP + "/json/close/" + t["id"], timeout=10)
