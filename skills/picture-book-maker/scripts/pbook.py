#!/usr/bin/env -S uv run --quiet --with requests --with pymupdf --with pillow --with numpy python3
"""pbook: make illustrated picture books for the kids (any series, any family cast), print-ready as booklets.

Data lives OUTSIDE the skill (private photos): ~/.hermes/data/kids-books/
  config.json                       models, judge, OpenRouter key ref
  cast/<id>/cast.json, sheet.png    reusable characters (family + series characters), photo.* optional
  series/<id>/series.json, refs/    painting style + style reference pages for a series (Tractor Mac, Daniel Tiger...)
  books/<slug>/story.json, art/     one book: pages, scenes, cast per page; output book.pdf + BOOKLET pdf

Commands (run `pbook.py <cmd> -h`):
  cast-add ID ...        register a character; makes a character sheet from a photo (or from a series ref)
  series-add ID ...      register a series style from reference pages (PDF pages or images)
  new SLUG ...           start a book (story.json skeleton)
  art SLUG [N ...]       paint pages: generate -> judge -> retry with fixes; keeps the best try
  bake SLUG N ... --models a,b   compare image models on the same pages (cost + judge verdict)
  layout SLUG            typeset book.pdf (art + text, Andika type, red sound words, soft vignette edges)
  booklet SLUG           impose for saddle-stitch printing + verify every page lands on the right sheet
  sheets SLUG            contact sheets (art + laid-out pages) for visual QA
  cost                   OpenRouter credit used so far (compare before/after a run)
"""
import argparse, base64, io, json, os, re, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import fitz
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.expanduser(os.environ.get("PBOOK_ROOT", "~/.hermes/data/kids-books"))
FONTS = os.path.expanduser("~/.hermes/data/fonts")
BOOKLET = os.path.expanduser("~/.hermes/scripts/booklet.py")
DEFAULTS = {
    "image_model": "gemini-3.1-flash-image",   # chosen by bake-off 2026-10-23: same quality as 3-pro-image at half the price
    "image_size": "1K",                        # 1024 px over a ~4.7 in page = ~215 dpi: plenty for watercolour on laser
    "cover_model": "gemini-3-pro-image",       # covers are worth the best model
    "cover_size": "2K",
    "judge": "paid",                           # "local" = Magnus Ollama (free) — tested 2026-10-23: gemma3:12b ran away
                                               # (12 KB of JSON) and swapped Magnus; paid flash judge is ~$0.002/check
    "local_judge_url": "http://100.119.136.41:11434",
    "local_judge_model": "gemma3:12b",
    "paid_judge_model": "google/gemini-2.5-flash",
    "max_tries": 3,
    "workers": 3,
    "openrouter_key_ref": "op://Home Servers/qfdfv5gyv5gturvopv3qj5ndl4/credential",
}
lock = threading.Lock()


# ---------------------------------------------------------------- basics
def cfg():
    p = f"{ROOT}/config.json"
    c = dict(DEFAULTS)
    if os.path.exists(p):
        c.update(json.load(open(p)))
    return c


def jload(p):
    return json.load(open(p))


def jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)


def log(*a):
    with lock:
        print(*a, flush=True)


_KEY = None


def or_key():
    global _KEY
    if _KEY is None:
        _KEY = os.environ.get("OPENROUTER_API_KEY")
        if not _KEY:
            env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=open(os.path.expanduser("~/.op_service_token")).read().strip())
            _KEY = subprocess.run(["op", "read", cfg()["openrouter_key_ref"]], env=env, capture_output=True,
                                  text=True, check=True).stdout.strip()
    return _KEY


def png_bytes(path_or_ref, max_px=1024):
    """Image path, or '<pdf path>#<page>' for a page of a reference PDF."""
    if "#" in path_or_ref and path_or_ref.split("#")[0].lower().endswith(".pdf"):
        pdf, pg = path_or_ref.rsplit("#", 1)
        pix = fitz.open(pdf)[int(pg) - 1].get_pixmap(dpi=90)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        im = Image.open(path_or_ref).convert("RGB")
    im.thumbnail((max_px, max_px))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def data_url(path, px=1024):
    return "data:image/png;base64," + base64.b64encode(png_bytes(path, px)).decode()


# ---------------------------------------------------------------- models
def generate(prompt, refs, out_png, model, size="1K", aspect="1:1"):
    """One image from Gemini via OpenRouter. Returns cost (USD) or raises."""
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": data_url(r)}} for r in refs]
    body = {"model": "google/" + model.replace("google/", ""), "modalities": ["image", "text"],
            "messages": [{"role": "user", "content": content}], "image_config": {"aspect_ratio": aspect, "image_size": size}}
    for attempt in range(8):
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=300,
                          headers={"Authorization": f"Bearer {or_key()}"})
        j = r.json()
        err = j.get("error")
        if err and ("429" in str(err) or "Retry" in str(err)):
            log(f"  rate-limited, waiting 90s"); time.sleep(90); continue
        if err:
            raise RuntimeError(str(err)[:300])
        imgs = j["choices"][0]["message"].get("images") or []
        if not imgs:
            raise RuntimeError("no image returned: " + str(j["choices"][0]["message"].get("content"))[:200])
        data = base64.b64decode(imgs[0]["image_url"]["url"].split(",", 1)[1])
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
        Image.open(io.BytesIO(data)).save(out_png)
        return j.get("usage", {}).get("cost") or 0.0
    raise RuntimeError("rate-limited too long")


JUDGE_ASK = ("You are a strict art director for a children's picture book. Check the NEW page (the last image) against "
             "the cast rules and the brief. Flag only what a parent would notice: a wrong or missing character, wrong "
             "skin, hair, age/size or outfit, a series character off-model, a brief element missing or wrong, any "
             "text/letters in the picture, anatomy errors (extra or missing limbs, fingers, wheels), or a hard "
             "rectangular edge instead of a soft vignette. Do NOT flag tiny stylistic variation, cuff/hem details, "
             "or a back view when the brief asks for one. Reply ONLY with JSON: "
             '{"pass": true|false, "problems": ["short, specific, fixable instruction", ...]}')


def _parse(txt):
    return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])


def judge(rules, brief, img, anchors):
    c = cfg()
    text = JUDGE_ASK + "\n\n" + rules + "\n\nBRIEF: " + brief
    if c["judge"] == "local":
        try:
            ims = [base64.b64encode(png_bytes(a, 640)).decode() for a in anchors[:2]] + [base64.b64encode(png_bytes(img, 896)).decode()]
            r = requests.post(f"{c['local_judge_url']}/api/chat", timeout=900, json={
                "model": c["local_judge_model"], "stream": False, "format": "json", "options": {"temperature": 0},
                "messages": [{"role": "user", "content": "The first images are approved character references; the LAST is the new page.\n" + text, "images": ims}]})
            v = _parse(r.json()["message"]["content"]); v["judge"] = "local"; return v
        except Exception as e:
            log(f"  local judge unavailable ({str(e)[:80]}); using paid judge")
    content = [{"type": "text", "text": "The first images are approved character references; the LAST is the new page.\n" + text}]
    content += [{"type": "image_url", "image_url": {"url": data_url(a, 640)}} for a in anchors[:3]]
    content += [{"type": "image_url", "image_url": {"url": data_url(img, 1024)}}]
    for _ in range(4):
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=240, headers={"Authorization": f"Bearer {or_key()}"},
                              json={"model": c["paid_judge_model"], "messages": [{"role": "user", "content": content}],
                                    "response_format": {"type": "json_object"}})
            v = _parse(r.json()["choices"][0]["message"]["content"]); v["judge"] = c["paid_judge_model"]; return v
        except Exception as e:
            log(f"  paid judge error {str(e)[:80]}; retry in 30s"); time.sleep(30)
    return {"pass": False, "problems": ["judge unavailable"], "judge": "none"}


# ---------------------------------------------------------------- cast & series
def cast(cid):
    p = f"{ROOT}/cast/{cid}/cast.json"
    if not os.path.exists(p):
        sys.exit(f"unknown cast member '{cid}' — add with: pbook.py cast-add {cid} ...")
    d = jload(p); d["dir"] = os.path.dirname(p); return d


def series(sid):
    d = jload(f"{ROOT}/series/{sid}/series.json"); d["dir"] = f"{ROOT}/series/{sid}"; return d


def series_refs(s):
    return [r if r.startswith("/") else f"{s['dir']}/{r}" for r in s.get("refs", [])]


def cmd_cast_add(a):
    d = f"{ROOT}/cast/{a.id}"; os.makedirs(d, exist_ok=True)
    c = {"id": a.id, "name": a.name, "role": a.role, "description": a.desc, "outfit": a.outfit, "sheet": "sheet.png"}
    refs = []
    if a.photo:
        ext = os.path.splitext(a.photo)[1].lower() or ".jpg"
        shutil.copy(a.photo, f"{d}/photo{ext}"); c["photo"] = f"photo{ext}"; refs.append(f"{d}/photo{ext}")
    refs += a.ref or []
    s = series(a.series) if a.series else None
    if s:
        refs += series_refs(s)[:2]
    jsave(f"{d}/cast.json", c)
    if a.sheet:
        shutil.copy(a.sheet, f"{d}/sheet.png"); print(f"{d}/sheet.png (copied)"); return
    style = s["style"] if s else "a warm hand-painted watercolour-and-ink children's picture-book style"
    prompt = (f"Make a CHARACTER REFERENCE SHEET for a children's picture book, painted in {style}, on plain white paper. "
              + (f"Keep the real likeness of the person in the first attached photo. " if a.photo else "")
              + (f"Copy this character EXACTLY as drawn in the first attached image (same face placement, proportions, colours). " if a.ref and not a.photo else "")
              + f"Character: {a.name}, {a.role}. {a.desc} Outfit: {a.outfit or 'everyday clothes'}. Show four poses: front view smiling, side view walking, a "
              "crouching or sitting pose, and one expressive action pose. Same face, outfit and colours in every pose. "
              "No text, labels or lettering.")
    cost = generate(prompt, refs, f"{d}/sheet.png", cfg()["cover_model"], "2K", "16:9")
    print(f"{d}/sheet.png  cost ${cost:.3f}  — check it, then use it in books")


def cmd_series_add(a):
    d = f"{ROOT}/series/{a.id}"; os.makedirs(f"{d}/refs", exist_ok=True)
    refs = []
    if a.ref_pdf:
        for pg in a.pages.split(","):
            out = f"refs/p{int(pg):02d}.png"
            open(f"{d}/{out}", "wb").write(png_bytes(f"{a.ref_pdf}#{pg}", 1400)); refs.append(out)
    for i, img in enumerate(a.ref_img or []):
        out = f"refs/img{i:02d}.png"; open(f"{d}/{out}", "wb").write(png_bytes(img, 1400)); refs.append(out)
    jsave(f"{d}/series.json", {"id": a.id, "name": a.name, "style": a.style, "rules": a.rules or "", "refs": refs})
    print(f"{d}/series.json with {len(refs)} reference pages")


# ---------------------------------------------------------------- book
def bdir(slug):
    return f"{ROOT}/books/{slug}"


def story(slug):
    return jload(f"{bdir(slug)}/story.json")


def cmd_new(a):
    p = f"{bdir(a.slug)}/story.json"
    if os.path.exists(p):
        sys.exit(f"{p} exists")
    for cid in a.cast.split(","):
        cast(cid)
    jsave(p, {"title": a.title, "subtitle": a.subtitle or "", "for": a.for_, "series": a.series, "cast": a.cast.split(","),
              "dedication": f"For {a.for_}.", "colophon": "Made at home with love.",
              "pages": [{"n": 1, "kind": "cover", "aspect": "3:4", "scene": "FRONT COVER, portrait. Top third plain sky for the title. ..."},
                        {"n": 2, "kind": "belongs", "scene": "small spot illustration on white paper ..."},
                        {"n": 3, "kind": "title", "scene": "small spot illustration of the main characters on white paper ..."},
                        {"n": 4, "text": "...", "scene": "..."},
                        {"n": 26, "kind": "end", "scene": "..."}, {"n": 27, "kind": "dedication"},
                        {"n": 28, "kind": "back", "aspect": "3:4", "scene": "..."}]})
    print(p, "— fill in the pages (page count must be a multiple of 4), then: pbook.py art", a.slug, "1  (cover first)")


def page_cast(st, p):
    if "cast" in p:
        return p["cast"]
    s = (p.get("scene", "") + " " + p.get("text", "")).lower()
    names = lambda cid: [st.get("names", {}).get(cid, cast(cid)["name"]), cast(cid)["name"]]
    return [cid for cid in st["cast"] if any(n.split()[-1].lower() in s for n in names(cid))]


def rules_for(st, ids):
    lines = ["CAST RULES (must hold wherever the character appears):"]
    for cid in ids:
        c = cast(cid); name = st.get("names", {}).get(cid, c["name"])
        outfit = st.get("outfits", {}).get(cid) or c.get("outfit", "")
        lines.append(f"- {name.upper()} ({c['role']}): {c['description']} {('In this book: ' + outfit) if outfit else ''} "
                     "Face exactly as on their character sheet.")
    lines.append("- No text, letters, numbers, writing or signature anywhere in the picture.")
    return "\n".join(lines)


def page_prompt(st, p, ids, fixes):
    s = series(st["series"]) if st.get("series") else None
    style = s["style"] if s else "loose hand-painted watercolour with fine ink lines"
    rules = rules_for(st, ids)
    pr = (f"Paint a NEW illustration for a children's picture book in this style: {style}. The attached images are, in order: "
          + ("the APPROVED COVER of this book (copy the characters exactly from it); " if st.get("anchor") else "")
          + ", ".join(f"the character sheet of {cast(c)['name']}" for c in ids)
          + ("; then the series reference pages, for painting style only" if s else "") + ".\n\n"
          + (s.get("rules", "") + "\n\n" if s else "") + rules
          + "\n\nCOMPOSITION: one scene, no frame; the painting fades softly into white paper at the edges (soft vignette)."
          + "\n\nSCENE: " + p["scene"])
    if fixes:
        pr += "\n\nIMPORTANT FIXES (a previous attempt got these wrong):\n- " + "\n- ".join(fixes)
    return pr, rules


def page_refs(st, p, ids):
    b = bdir_of(st)
    refs = [f"{b}/{st['anchor']}"] if st.get("anchor") and p.get("kind") != "cover" else []
    refs += [f"{cast(c)['dir']}/{cast(c)['sheet']}" for c in ids]
    if st.get("series"):
        refs += series_refs(series(st["series"]))[:1]
    refs += [r if r.startswith("/") else f"{b}/{r}" for r in p.get("refs", [])]
    return refs[:6]


def bdir_of(st):
    return st["_dir"]


def cmd_art(a):
    st = story(a.slug); st["_dir"] = bdir(a.slug); c = cfg()
    only = set(a.pages)
    qa_p = f"{st['_dir']}/qa.json"
    spend = [0.0]

    def job(p):
        n, name = p["n"], f"p{p['n']:02d}"
        if "scene" not in p or (only and n not in only) or (not only and os.path.exists(f"{st['_dir']}/art/{name}.png")):
            return
        ids = page_cast(st, p)
        cover = p.get("kind") in ("cover", "back")
        model = a.model or (c["cover_model"] if cover else c["image_model"])
        size = c["cover_size"] if cover else c["image_size"]
        fixes, best = list(p.get("fixes", [])), None
        for t in range(1, c["max_tries"] + 1):
            prompt, rules = page_prompt(st, p, ids, fixes)
            refs = page_refs(st, p, ids)
            out = f"{st['_dir']}/art/tries/{name}_t{t}.png"
            try:
                cost = generate(prompt, refs, out, model, size, p.get("aspect", "1:1"))
                with lock:
                    spend[0] += cost
            except Exception as e:
                log(f"{name} t{t} generation failed: {e}"); continue
            v = judge(rules, p["scene"], out, refs)
            probs = [] if v.get("pass") else (v.get("problems") or ["unspecified"])
            log(f"{name} t{t} {model} ${cost:.3f} {v.get('judge')}: {'PASS' if not probs else 'FAIL ' + str(probs)[:200]}")
            if best is None or len(probs) < len(best[1]):
                best = (out, probs, t)
            if not probs:
                break
            fixes = list(p.get("fixes", [])) + probs
        if best:
            shutil.copy(best[0], f"{st['_dir']}/art/{name}.png")
            with lock:
                qa = jload(qa_p) if os.path.exists(qa_p) else {}
                qa[name] = {"try": best[2], "open_problems": best[1]}; jsave(qa_p, qa)

    with ThreadPoolExecutor(c["workers"]) as ex:
        list(ex.map(job, st["pages"]))
    print(f"DONE. Image spend this run: ${spend[0]:.2f} (+ judge checks, ~$0.002 each)")


def credit_used():
    try:
        return requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {or_key()}"},
                            timeout=30).json()["data"]["total_usage"]
    except Exception:
        return None


def cmd_cost(a):
    r = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {or_key()}"}, timeout=30).json()["data"]
    print(f"credits ${r['total_credits']:.2f}, used ${r['total_usage']:.2f}, left ${r['total_credits'] - r['total_usage']:.2f}")


def cmd_bake(a):
    st = story(a.slug); st["_dir"] = bdir(a.slug); res = []
    for n in a.pages:
        p = next(x for x in st["pages"] if x["n"] == n); ids = page_cast(st, p)
        for m in a.models.split(","):
            prompt, rules = page_prompt(st, p, ids, [])
            out = f"{st['_dir']}/art/bake/{m}_p{n:02d}.png"
            try:
                cost = generate(prompt, page_refs(st, p, ids), out, m, a.size, p.get("aspect", "1:1"))
                v = judge(rules, p["scene"], out, page_refs(st, p, ids))
                res.append({"model": m, "page": n, "cost": cost, "pass": v.get("pass"), "problems": v.get("problems")})
            except Exception as e:
                res.append({"model": m, "page": n, "error": str(e)[:200]})
            print(res[-1], flush=True)
    jsave(f"{st['_dir']}/bake.json", res)


# ---------------------------------------------------------------- layout
W, HH, M = 4.95 * 72, 6.9 * 72, 10       # page fills a half-Letter booklet page at 100%
SFX_DEFAULT = ["CRUNCH!", "Moooo!", "Baaa! Baaa!", "Hooray"]


FONT_URLS = {"Andika-Regular.ttf": "ofl/andika/Andika-Regular.ttf", "LilitaOne-Regular.ttf": "ofl/lilitaone/LilitaOne-Regular.ttf"}


def css():
    os.makedirs(FONTS, exist_ok=True)
    for f, u in FONT_URLS.items():  # Google Fonts (OFL): fetched once on a fresh machine
        if not os.path.exists(f"{FONTS}/{f}"):
            open(f"{FONTS}/{f}", "wb").write(requests.get(f"https://github.com/google/fonts/raw/main/{u}", timeout=60).content)
    return f"""
@font-face {{font-family: andika; src: url({FONTS}/Andika-Regular.ttf);}}
@font-face {{font-family: lilita; src: url({FONTS}/LilitaOne-Regular.ttf);}}
* {{color: #211c1a; font-family: andika;}}
p {{margin: 0 0 7pt 0; line-height: 1.32;}}
.c {{text-align: center;}}"""


def whiten(im):
    out = []
    for ch in im.split():
        hist = ch.histogram(); total = sum(hist); acc = 0
        for v in range(255, -1, -1):
            acc += hist[v]
            if acc >= total * 0.04:
                break
        g = 255.0 / max(v, 200); out.append(ch.point(lambda x, g=g: min(255, int(x * g))))
    return Image.merge("RGB", out)


def soften(im, feather):
    import numpy as np
    a = np.asarray(im).astype(np.float32); mx, mn = a.max(axis=2), a.min(axis=2)
    paper = np.clip((mn - 185) / 45.0, 0, 1) * np.clip(1 - (mx - mn) / 45.0, 0, 1)
    a = a * (1 - paper[..., None]) + 255 * paper[..., None]
    h, w = mn.shape; f = int(min(w, h) * feather)
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rectangle([f, f, w - f, h - f], fill=255)
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(f * 0.6))).astype(np.float32) / 255
    a = a * m[..., None] + 255 * (1 - m[..., None])
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def img_stream(path, max_px=1600, feather=0.09):
    im = whiten(Image.open(path).convert("RGB")); im.thumbnail((max_px, max_px))
    if feather:
        im = soften(im, feather)
    b = io.BytesIO(); im.save(b, "JPEG", quality=90); return b.getvalue()


def smart(t, sfx):
    t = t.replace("...", "\u2026")
    t = re.sub(r'(^|[\s(\n])"', "\\1\u201c", t); t = t.replace('"', "\u201d")
    t = re.sub(r"(\w)'", "\\1\u2019", t); t = t.replace("'", "\u2018")
    span = '<span style="font-family:lilita; color:#b8121a; font-size:1.25em">'
    for w in sfx:
        for pat in (f"\u201c{w}\u201d", f"\u201c{w}", w):
            if pat in t:
                t = t.replace(pat, f"{span}{pat}</span>"); break
    return t


def html(text, size, sfx):
    paras = "".join(f'<p class="c">{x.replace(chr(10), "<br>")}</p>' for x in smart(text, sfx).split("\n\n"))
    return f'<div style="font-size:{size}pt">{paras}</div>'


def fit_text(page, rect, text, sfx, start=14, minimum=10):
    s = start
    while s >= minimum:
        probe = fitz.open().new_page(width=W, height=HH)
        spare, _ = probe.insert_htmlbox(rect, html(text, s, sfx), css=css(), scale_low=1)
        if spare >= 0:
            page.insert_htmlbox(fitz.Rect(rect.x0, rect.y0 + spare / 2, rect.x1, rect.y1), html(text, s, sfx), css=css(), scale_low=1)
            return s
        s -= 0.5
    raise SystemExit(f"text does not fit: {text[:40]}")


def title_html(st, big, small):
    return (f'<div class="c" style="font-family:lilita; font-size:{big}pt; color:#b8121a; line-height:1.0">{st["title"]}</div>'
            + (f'<div class="c" style="font-family:lilita; font-size:{small}pt; color:#2a3f6b; line-height:1.15; margin-top:4pt">'
               f'{smart(st["subtitle"], [])}</div>' if st.get("subtitle") else ""))


def cmd_layout(a):
    st = story(a.slug); d = bdir(a.slug); sfx = st.get("sfx", SFX_DEFAULT)
    if len(st["pages"]) % 4:
        sys.exit(f"{len(st['pages'])} pages: a saddle-stitched booklet needs a multiple of 4")
    doc = fitz.open(); missing = []
    for p in st["pages"]:
        n, kind = p["n"], p.get("kind", "story"); art = f"{d}/art/p{n:02d}.png"
        has = os.path.exists(art)
        if not has and kind != "dedication":
            missing.append(n)
        pg = doc.new_page(width=W, height=HH)
        if kind in ("cover", "back"):
            if has:
                im = Image.open(art); r = im.height / im.width; w = W; h = w * r
                if h < HH:
                    h = HH; w = h / r
                x0 = (W - w) / 2
                pg.insert_image(fitz.Rect(x0, HH - h, x0 + w, HH), stream=img_stream(art, 2000, 0))
            if kind == "cover":
                pg.insert_htmlbox(fitz.Rect(M, 30, W - M, 165), title_html(st, 52, 26), css=css())
        elif kind == "belongs":
            pg.insert_htmlbox(fitz.Rect(M, 70, W - M, 170), '<div class="c" style="font-size:15pt">This book belongs to</div>'
                              f'<div class="c" style="font-family:lilita; font-size:34pt; color:#b8121a; margin-top:6pt">{st["for"]}</div>', css=css())
            if has:
                pg.insert_image(fitz.Rect(W / 2 - 140, 185, W / 2 + 140, 465), stream=img_stream(art), keep_proportion=True)
        elif kind == "title":
            tag = st.get("tagline", f"A story made for {st['for']}")
            pg.insert_htmlbox(fitz.Rect(M, 40, W - M, 190), title_html(st, 34, 19) +
                              f'<div class="c" style="font-size:14pt; margin-top:12pt; color:#2a3f6b">{tag}</div>', css=css())
            if has:
                pg.insert_image(fitz.Rect(W / 2 - 140, 200, W / 2 + 140, 480), stream=img_stream(art), keep_proportion=True)
        elif kind == "dedication":
            pg.insert_htmlbox(fitz.Rect(M + 20, 190, W - M - 20, 420),
                              f'<div class="c" style="font-size:14pt; line-height:1.4">{smart(st.get("dedication", ""), []).replace(chr(10), "<br>")}</div>'
                              f'<div class="c" style="font-size:10pt; margin-top:40pt; color:#4a423d">{smart(st.get("colophon", ""), []).replace(chr(10), "<br>")}</div>', css=css())
        else:  # story / end: square art on top, text below
            side = W - 2 * M
            if has:
                pg.insert_image(fitz.Rect(M, M, M + side, M + side), stream=img_stream(art), keep_proportion=True)
            tr = fitz.Rect(M + 8, M + side + 6, W - M - 8, HH - M - 4)
            if kind == "end":
                pg.insert_htmlbox(tr, f'<div class="c" style="font-family:lilita; font-size:30pt; color:#b8121a; margin-top:14pt">{p.get("text", "The End")}</div>', css=css())
            else:
                fit_text(pg, tr, p.get("text", ""), sfx)
    doc.save(f"{d}/book.pdf", garbage=3, deflate=True)
    print(f"{d}/book.pdf  {len(doc)} pages" + (f"  MISSING ART: {missing}" if missing else ""))


# ---------------------------------------------------------------- booklet + QA
def booklet_name(st):
    return re.sub(r"[^\w' -]", "", st["title"] + (" " + st["subtitle"] if st.get("subtitle") else "")).strip() + " - BOOKLET print duplex short-edge.pdf"


def cmd_booklet(a):
    st = story(a.slug); d = bdir(a.slug); out = f"{d}/{booklet_name(st)}"
    r = subprocess.run([BOOKLET, f"{d}/book.pdf", "--crop-marks", "-o", out], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip().splitlines()[-1])
    # verify: every half-sheet must render like the source page that belongs there
    src, bk = fitz.open(f"{d}/book.pdf"), fitz.open(out)
    pw, ph = src[0].rect.width, src[0].rect.height; y0 = (612 - ph) / 2
    L = fitz.Rect(5.2 * 72 - pw, y0, 5.2 * 72, y0 + ph); R = fitz.Rect(5.8 * 72, y0, 5.8 * 72 + pw, y0 + ph)
    g = lambda page, clip=None: page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25), clip=clip, colorspace=fitz.csGRAY)
    S = [g(p) for p in src]; n = len(src); bad = 0
    def dist(x, y, k=30):
        return sum(abs(x.pixel(int(i * x.width / k), int(j * x.height / k))[0] - y.pixel(int(i * y.width / k), int(j * y.height / k))[0]) for i in range(k) for j in range(k))
    for si, p in enumerate(bk):
        i = si // 2; exp = (n - 2 * i, 2 * i + 1) if si % 2 == 0 else (2 * i + 2, n - 1 - 2 * i)
        got = tuple(min(range(n), key=lambda k: dist(g(p, r), S[k])) + 1 for r in (L, R))
        if got != exp:
            bad += 1; print(f"  sheet {i + 1} {'front' if si % 2 == 0 else 'back'}: got {got}, expected {exp}")
    print(out); print("IMPOSITION OK" if not bad else f"IMPOSITION PROBLEMS: {bad}")


def contact(images, out, labels, cols=3, tw=420):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    ims = []
    for f in images:
        im = Image.open(f).convert("RGB"); im.thumbnail((tw, int(tw * 1.45))); ims.append(im)
    th = max(i.height for i in ims); rows = (len(ims) + cols - 1) // cols
    c = Image.new("RGB", (cols * (tw + 12) + 12, rows * (th + 46) + 12), "#777"); dr = ImageDraw.Draw(c)
    for k, (im, lab) in enumerate(zip(ims, labels)):
        x = 12 + (k % cols) * (tw + 12); y = 12 + (k // cols) * (th + 46)
        dr.text((x, y), lab, fill="yellow", font=font); c.paste(im, (x, y + 38))
    c.save(out, quality=85); return out


def cmd_sheets(a):
    d = bdir(a.slug); outdir = f"{d}/qa"; os.makedirs(outdir, exist_ok=True); made = []
    doc = fitz.open(f"{d}/book.pdf")
    pngs = []
    for i, p in enumerate(doc):
        f = f"{outdir}/page{i + 1:02d}.png"; p.get_pixmap(dpi=60).save(f); pngs.append(f)
    for k in range(0, len(pngs), 8):
        made.append(contact(pngs[k:k + 8], f"{outdir}/pages_{k // 8 + 1}.jpg", [f"p{j + 1}" for j in range(k, min(k + 8, len(pngs)))], cols=4, tw=380))
    print("\n".join(made))


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("cast-add"); x.add_argument("id"); x.add_argument("--name", required=True); x.add_argument("--role", required=True)
    x.add_argument("--desc", required=True, help="the look (face, skin, hair, build), used on every page")
    x.add_argument("--outfit", default="", help="default outfit; a book can override it in story.json outfits"); x.add_argument("--photo")
    x.add_argument("--series", help="paint the sheet in this series' style"); x.add_argument("--ref", nargs="*", help="images showing the character (e.g. an approved page)"); x.add_argument("--sheet", help="use an existing sheet image")
    x = sp.add_parser("series-add"); x.add_argument("id"); x.add_argument("--name", required=True); x.add_argument("--style", required=True)
    x.add_argument("--rules", help="series-wide rules"); x.add_argument("--ref-pdf"); x.add_argument("--pages", default="")
    x.add_argument("--ref-img", nargs="*")
    x = sp.add_parser("new"); x.add_argument("slug"); x.add_argument("--title", required=True); x.add_argument("--subtitle")
    x.add_argument("--for", dest="for_", required=True); x.add_argument("--series"); x.add_argument("--cast", required=True)
    x = sp.add_parser("art"); x.add_argument("slug"); x.add_argument("pages", nargs="*", type=int); x.add_argument("--model")
    x = sp.add_parser("bake"); x.add_argument("slug"); x.add_argument("pages", nargs="+", type=int); x.add_argument("--models", required=True)
    x.add_argument("--size", default="1K")
    for c in ("layout", "booklet", "sheets"):
        sp.add_parser(c).add_argument("slug")
    sp.add_parser("cost")
    a = ap.parse_args()
    {"cast-add": cmd_cast_add, "series-add": cmd_series_add, "new": cmd_new, "art": cmd_art, "bake": cmd_bake,
     "layout": cmd_layout, "booklet": cmd_booklet, "sheets": cmd_sheets, "cost": cmd_cost}[a.cmd](a)


if __name__ == "__main__":
    main()
