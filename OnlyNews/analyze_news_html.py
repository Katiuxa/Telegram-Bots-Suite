"""Temporary script to analyze news site HTML structures."""
import json
import re
import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}


def analyze(url: str) -> None:
    print("=" * 80)
    print(url)
    r = requests.get(url, headers=HEADERS, timeout=25)
    print("status", r.status_code, "len", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            raw = s.string or s.get_text()
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                t = item.get("@type", "")
                if "Article" in str(t):
                    ab = item.get("articleBody", "")
                    print(f"  json-ld @type={t} articleBody={len(ab)} headline={item.get('headline','')[:80]}")
        except Exception as exc:
            print("  json-ld err", exc)

    selectors = [
        "article",
        ".article-body",
        ".article__body",
        ".article-content",
        ".article-text",
        ".entry-content",
        ".news-body",
        "[itemprop=articleBody]",
        ".articulo-cuerpo",
        ".a_c",
        ".content-article",
        ".story-body",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            ps = el.find_all("p")
            print(f"  {sel}: {len(ps)} p, text={len(el.get_text())}")

    art = soup.find("article")
    if art:
        for i, p in enumerate(art.find_all("p")):
            print(f"  art p[{i}]: {p.get_text()[:120]}")

    for s in soup.find_all("script"):
        txt = s.string or ""
        if "articleBody" in txt and len(txt) > 500:
            m = re.search(r'"articleBody"\s*:\s*"([^"]{50,})', txt)
            if m:
                print(f"  inline articleBody snippet: {m.group(1)[:120]}...")


if __name__ == "__main__":
    urls = sys.argv[1:] or [
        "https://www.heraldo.es/noticias/aragon/2026/07/03/medico-zaragoza-carcel-cobrar-horas-extras-no-justificadas-2032704.html",
        "https://elpais.com/espana/2026-07-03/juan-manuel-moreno-de-gobernar-con-vox-es-imposible-a-asumir-todos-sus-postulados-por-dos-votos.html",
        "https://historia.nationalgeographic.com.es/a/lobos-aprendiendo-mundo-salvaje_26133",
        "https://www.elconfidencial.com/espana/2026-07-03/zapatero-cobro-premios-apoyados-alianza-civilizaciones-moratinos_4382657/",
    ]
    for u in urls:
        try:
            analyze(u)
        except Exception as exc:
            print("ERR", exc)
