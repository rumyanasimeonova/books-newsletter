#!/usr/bin/env python3
"""Retrieve verified cover images from each book's linked product page."""
from pathlib import Path
from urllib.parse import urljoin
import json, re, time
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"
OUT = ROOT / "images"
OUT.mkdir(exist_ok=True)
html = PAGE.read_text(encoding="utf-8")
pattern = re.compile(r'(<article class="book">.*?<div class="cover"[^>]*>)(.*?)(</div>.*?<h3>(.*?)</h3>.*?<a class="button" href="([^"]+)")', re.S)
matches = list(pattern.finditer(html))
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; BooksNewsletter/1.0)"})
report = []
replacements = []
for i, match in enumerate(matches, 1):
    prefix, inner, suffix, title, link = match.groups()
    path = OUT / f"book-{i:02d}.jpg"
    state = "existing" if path.exists() else "missing"
    if not path.exists():
        try:
            response = session.get(link.replace("&amp;", "&"), timeout=22)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            candidates = []
            for key in ("og:image", "twitter:image"):
                tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
                if tag and tag.get("content"):
                    candidates.append(tag["content"])
            for node in soup.find_all("script", type="application/ld+json"):
                try:
                    obj = json.loads(node.string or node.get_text())
                    objs = obj if isinstance(obj, list) else [obj]
                    for item in objs:
                        if isinstance(item, dict):
                            val = item.get("image")
                            if isinstance(val, str): candidates.append(val)
                            elif isinstance(val, list): candidates.extend(v for v in val if isinstance(v,str))
                except (ValueError, TypeError): pass
            for tag in soup.find_all("img", limit=35):
                if any(t in (tag.get("alt") or "").lower() for t in [title.lower()[:18], "корица"]):
                    for key in ("data-src", "src"):
                        if tag.get(key): candidates.append(tag[key])
            for candidate in dict.fromkeys(candidates):
                if candidate.startswith("data:"): continue
                try:
                    pic = session.get(urljoin(response.url, candidate), timeout=18, headers={"Referer": response.url})
                    pic.raise_for_status()
                    from PIL import Image
                    from io import BytesIO
                    im = Image.open(BytesIO(pic.content)).convert("RGB")
                    if im.width < 110 or im.height < 150 or im.width > im.height * 1.35: continue
                    im.thumbnail((600, 900))
                    im.save(path, "JPEG", quality=87, optimize=True)
                    state = "downloaded"
                    break
                except Exception: continue
        except Exception as ex:
            state = "unavailable: " + str(ex)[:90]
    if path.exists():
        new_inner = f'<img src="images/book-{i:02d}.jpg" alt="Корица на {title}" loading="lazy" decoding="async">'
        replacements.append((match.start(2), match.end(2), new_inner))
    report.append({"number": i, "title": BeautifulSoup(title, "html.parser").get_text(), "status": state, "source": link})
    print(f"{i:02d}: {state}: {title[:50]}", flush=True)
    time.sleep(.2)
for start, end, value in reversed(replacements):
    html = html[:start] + value + html[end:]
if replacements:
    html = html.replace('</style>', '.cover:has(img){background:transparent;box-shadow:none;padding:0;min-height:0;height:auto;display:block}.cover img{width:100%;height:auto;max-height:270px;object-fit:contain;object-position:top center;display:block}@media(max-width:520px){.cover img{max-height:190px}} </style>')
    html = html.replace('Временно са използвани типографски изображения на кориците до добавяне на оригиналните изображения.', 'Показани са наличните корици от издателските страници. При липса на изображение е използвана икона.')
    PAGE.write_text(html, encoding="utf-8")
(ROOT / "cover-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Downloaded/present: {len(replacements)}/{len(matches)}", flush=True)
