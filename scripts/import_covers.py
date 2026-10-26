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
# Alternative product pages for publishers that block automated access.
FALLBACKS = {
  16: ["https://academicabooks.bg/product/%D1%82%D0%B5%D1%85%D0%BD%D0%B8%D0%BA%D0%B0%D1%82%D0%B0-%D0%BD%D0%B0-%D0%BF%D1%81%D0%B8%D1%85%D0%BE%D0%B0%D0%BD%D0%B0%D0%BB%D0%B8%D0%B7%D0%B0%D1%82%D0%B0/", "https://bulpedagogika.com/book-3229-tehnikata-na-psihoanalizata"],
  18: ["https://espacepsy-bg.org/library/"],
  19: ["https://espacepsy-bg.org/events/presentation-of-a-collection-of-works-by-claude-noele-pickmann/"],
  21: ["https://stenobooks.com/product/5932/poslednite-lektsii-1958-k-g-yung.html"],
  22: ["https://www.ozone.bg/product/bremennata-devitsa/", "https://www.bookpoint.bg/%D0%BA%D0%BD%D0%B8%D0%B3%D0%B8/%D0%91%D1%80%D0%B5%D0%BC%D0%B5%D0%BD%D0%BD%D0%B0%D1%82%D0%B0-%D0%B4%D0%B5%D0%B2%D0%B8%D1%86%D0%B0-155374.htm"],
  26: ["https://kx-publishing.org/shop/%d0%b0%d0%bd%d1%82%d0%b8-%d0%b5%d0%b4%d0%b8%d0%bf/"],
  28: ["https://potayniche.merchsolution.net/shop/%D0%BF%D1%80%D0%BE%D0%B1%D0%B8%D1%82%D0%B8%D1%82%D0%B5-%D0%B3%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B8-%D0%B2-%D1%82%D0%B5%D1%80%D0%B0%D0%BF%D0%B8%D1%8F%D1%82%D0%B0-%D0%BD%D0%B0-%D0%B3%D1%80%D0%B0%D0%BD/", "https://www.book.store.bg/p230450/probitite-granici-v-terapiata-na-granichnostta-i-borderlajn-petyr-kralev.html"],
}
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; BooksNewsletter/1.0)"})
report = []
replacements = []
for position, match in enumerate(matches, 1):
    # Preserve original cover numbering; additions are books 27, 28, and 29.
    i = 27 if position == 20 else 28 if position == 21 else 29 if position == 29 else (position if position <= 19 else position - 2)
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
        if not path.exists():
            for fallback in FALLBACKS.get(i, []):
                try:
                    res = session.get(fallback, timeout=22)
                    res.raise_for_status()
                    page = BeautifulSoup(res.text, "html.parser")
                    images = []
                    if i not in (18,19):
                        for meta in page.select('meta[property="og:image"], meta[name="twitter:image"]'):
                            if meta.get("content"): images.append(meta["content"])
                    for img in page.find_all("img", limit=100):
                        alt = (img.get("alt") or "").lower()
                        if i in (18,19) and not any(q in alt for q in (["особени майчинства"] if i==18 else ["какво иска жената", "пикман"])): continue
                        if img.get("data-src"): images.append(img["data-src"])
                        if img.get("src"): images.append(img["src"])
                    for url in dict.fromkeys(images):
                        try:
                            pic = session.get(urljoin(res.url, url), timeout=18, headers={"Referer": res.url})
                            pic.raise_for_status()
                            from PIL import Image
                            from io import BytesIO
                            im = Image.open(BytesIO(pic.content)).convert("RGB")
                            if im.width < 110 or im.height < 150 or im.width > im.height * 1.35: continue
                            im.thumbnail((600,900))
                            im.save(path, "JPEG", quality=87, optimize=True)
                            state = "downloaded via fallback"
                            break
                        except Exception: continue
                    if path.exists(): break
                except Exception: continue
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
