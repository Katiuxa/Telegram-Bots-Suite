"""Extracción universal de artículos: HTML, JSON-LD, trafilatura + anti-bot."""
from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8,en-US;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

GOOGLEBOT_HEADERS = {
    **DEFAULT_HEADERS,
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

# Selectores universales (orden = preferencia; se puntúan todos)
UNIVERSAL_SELECTORS = (
    "#post-content",
    "#post_content",
    ".article-main",
    "[itemprop=articleBody]",
    "[itemprop=articlebody]",
    "article",
    "main article",
    "[role=main]",
    "main",
    ".article-body",
    ".article__body",
    ".article-content",
    ".article-text",
    ".article-detail__body",
    ".entry-content",
    ".post-content",
    ".story-body",
    ".news-body",
    ".content-article",
    ".text-content",
    ".voc-detail__body",
    ".a_c",
    ".articulo-cuerpo",
    ".node-content",
    ".field-body",
    "#article-body",
    "#content-body",
)

DOMAIN_SELECTORS: dict[str, tuple[str, ...]] = {
    "elpais.com": ("[itemprop=articleBody]", ".a_c", "article"),
    "cincodias.elpais.com": ("[itemprop=articleBody]", ".a_c", "article"),
    "abc.es": ("article", ".voc-detail__body"),
    "nationalgeographic.com.es": (".article-body", ".article-content", "article"),
    "elconfidencial.com": (
        "#news-body-cc",
        ".newsType__content.news-body-complete",
        ".news-body-complete",
        ".newsType__content",
        ".bodyContent",
    ),
}

NOISE_STARTS = (
    "basado en hechos observados",
    "please enable js",
    "enable javascript",
    "suscríbete",
    "suscribete",
    "inicia sesión",
    "inicia sesion",
    "seguir en google",
    "síguenos",
    "siguenos",
    "© ",
    "cookies",
    "publicidad",
    "te puede interesar",
    "el redactor recomienda",
    "ec exclusivo",
    "conforme a los criterios",
    "logo trust project",
    "¿por qué confiar",
    "descuentos de verano",
    "puedes ver aquí el diálogo",
    "puedes ver aqui el dialogo",
    "temas /",
    "lectura:",
    "actualizado a",
    "diario abc",
    "regala esta noticia",
    "añádenos en google",
    "compartir en",
    "leer más",
    "related articles",
    "artículos relacionados",
    "photos from this story",
    "on exposure",
)

EMBED_HOSTS = (
    "exposure.co",
    "cdn.ampproject.org",
    "scribd.com",
    "datawrapper",
)

STOP_HEADINGS = (
    "el redactor recomienda",
    "te puede interesar",
    "más información sobre",
    "comentarios",
    "tags relacionados",
    "noticias relacionadas",
    "newsletter",
    "temas",
    "lo más leído",
    "reportar un error",
    "más noticias",
    "también te puede interesar",
)

AUTHOR_LINE = re.compile(
    r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3}$"
)
DATELINE = re.compile(r"^[A-ZÁÉÍÓÚÑ][\w\s\-]+?\([^)]+\)$")
PHOTO_CREDIT = re.compile(r"\s*\((?:EP|EFE|Reuters|AFP|GTRES)\)\s*", re.I)
QA_PREFIX = re.compile(r"^(Pregunta|Respuesta)\.\s*(.*)$", re.DOTALL | re.IGNORECASE)
SITE_SUFFIX = re.compile(
    r"\s*[\|\-–—]\s*(?:EL PAÍS|El País|ABC|Heraldo|EL CONFIDENCIAL|El Confidencial|"
    r"El Mundo|La Vanguardia|20minutos|Público|elDiario\.es|BBC News|Reuters).*$"
    r"|\s+by\s+National Geographic[^.]*on Exposure.*$",
    re.I,
)
# Metadatos / embeds que El Confidencial pega al cuerpo del artículo
POR_BYLINE = re.compile(
    r"^POR\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+){0,5}\s*$"
)
RELATED_TITLE = re.compile(
    r".{20,220}\s+POR\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.\-]+){0,5}\s*$"
)
AUTHOR_DATE_PREFIX = re.compile(
    r"^(?:Por\s+.+?\s+)?"
    r"\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}:\d{2}"
    r"(?:\s*Actualizado:\s*\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}:\d{2})?"
    r"(?:\s*Seguir en Google)?"
    r"(?:\s*Síguenos)?"
    r"(?:\s*EC EXCLUSIVO)?"
    r"(?:\s*Seguir en Google)?"
    r"(?:\s*Síguenos)?"
    r"\s*",
    re.I,
)
INLINE_RELATED = re.compile(
    r"\s*TE PUEDE INTERESAR\s+.+?(?=(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,}\s+[a-záéíóúñ])|$)",
    re.I | re.DOTALL,
)
TAG_CLOUD = re.compile(
    r"^(?:[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ.\-]*)(?:\s+[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ.\-]*){1,12}$"
)
BLOCKED_SECTION_HINTS = (
    "related", "recommend", "promo", "newsletter", "banner", "advert",
    "social", "tags", "sidebar", "widget", "comments", "compartir",
    "share", "breadcrumb", "menu", "footer", "header",
    "intextnews", "in-text-news", "articleaside", "redactor",
    "revunit", "piano", "paywall", "subscription",
)

ArticleBlock = tuple[str, str]  # paragraph | subtitle | section | image

# Contenedores de imagen habituales en prensa digital
MEDIA_CONTAINER_HINTS = (
    "figure", "photo", "image", "media", "gallery", "picture", "a_m", "voc-image",
    "articulo-imagen", "img_", "foto", "thumbnail", "visual", "story-image",
    "article-image", "content-image", "media-image", "photo-container",
)

IMG_SKIP_HINTS = (
    "logo", "icon", "avatar", "badge", "pixel", "tracking", "spinner", "placeholder",
    "newsletter", "banner", "advert", "promo", "social", "share", "author",
    "gravatar", "emoji", "sprite", "1x1",
)


def _is_embed_noise(text: str) -> bool:
    low = text.lower().strip()
    if "untitled story" in low and "exposure" in low:
        return True
    if low in ("photos from this story", "button label"):
        return True
    return False


def _node_text(node) -> str:
    """Texto inline respetando espacios del HTML (sin partir ni pegar palabras)."""
    if getattr(node, "name", None) in ("script", "style"):
        return ""
    text = "".join(node.strings)
    return re.sub(r"\s+", " ", text).strip()


def _norm(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _norm_key(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


def _is_noise(text: str) -> bool:
    low = text.lower().strip()
    if len(low) < 20:
        return True
    if _is_embed_noise(text):
        return True
    if any(low.startswith(s) for s in NOISE_STARTS):
        return True
    if "te puede interesar" in low and len(text) < 280:
        return True
    if "el redactor recomienda" in low:
        return True
    if POR_BYLINE.match(text.strip()):
        return True
    if RELATED_TITLE.match(text.strip()) and "te puede interesar" not in low:
        # Título de noticia embebida: "... POR Autor"
        if not text.strip().endswith(".") and len(text) < 240:
            return True
    if TAG_CLOUD.match(text.strip()) and "." not in text and len(text) < 120:
        # Nube de tags al final del artículo
        words = text.split()
        if len(words) >= 3 and sum(1 for w in words if w[:1].isupper()) >= len(words) - 1:
            return True
    return False


def _is_stop_heading(text: str) -> bool:
    low = text.lower().strip()
    return any(stop in low for stop in STOP_HEADINGS)


def _clean_heading(text: str) -> str | None:
    text = _norm(text)
    if not text or _is_stop_heading(text):
        return None
    if any(text.lower().startswith(s) for s in NOISE_STARTS):
        return None
    return text


def _strip_article_chrome(text: str) -> str:
    """Quita bylines, 'Seguir en Google' y 'TE PUEDE INTERESAR' pegados al cuerpo."""
    text = AUTHOR_DATE_PREFIX.sub("", text).strip()
    text = INLINE_RELATED.sub(" ", text)
    text = re.sub(r"\s*(?:Seguir en Google|Síguenos|EC EXCLUSIVO)\s*", " ", text, flags=re.I)
    return _norm(text)


def _clean_paragraph(text: str) -> str | None:
    text = _norm(text)
    text = re.sub(r"(?<=[a-záéíóúñ,])\s*\.\.\.\s*(?=[a-záéíóúñ])", " ", text, flags=re.I)
    text = re.sub(r"\s*\.\.\.\s*", " ", text)
    text = PHOTO_CREDIT.sub(" ", text)
    text = _strip_article_chrome(text)
    text = _norm(text)
    if _is_noise(text):
        return None
    return text


def _is_kicker(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters or len(text) > 120:
        return False
    return sum(c.isupper() for c in letters) / len(letters) > 0.82


def _is_metadata(text: str) -> bool:
    text = text.strip()
    if len(text) < 3:
        return True
    if text.lower() in ("newsletter", "diario abc", "abc", "ec exclusivo"):
        return True
    if _is_kicker(text):
        return True
    if POR_BYLINE.match(text):
        return True
    if RELATED_TITLE.match(text) and len(text) < 240 and not text.endswith("."):
        return True
    if len(text) < 50 and AUTHOR_LINE.match(text):
        return True
    if len(text) < 60 and DATELINE.match(text):
        return True
    if TAG_CLOUD.match(text) and "." not in text and len(text) < 120:
        words = text.split()
        if len(words) >= 3 and sum(1 for w in words if w[:1].isupper()) >= len(words) - 1:
            return True
    return False


def _dedupe_paragraphs(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        key = _norm_key(paragraph)
        if not key or key in seen:
            continue
        if out and key == _norm_key(out[-1]):
            continue
        seen.add(key)
        out.append(paragraph)
    if len(out) >= 2 and _norm_key(out[0]) == _norm_key(out[-1]):
        out.pop()
    return out


def _domain_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _domain_selectors(url: str) -> tuple[str, ...]:
    host = _domain_key(url)
    for domain, sels in DOMAIN_SELECTORS.items():
        if host == domain or host.endswith("." + domain):
            return sels
    return ()


def _selectors_for(url: str) -> tuple[str, ...]:
    extra = list(_domain_selectors(url))
    # dominio primero, luego universales sin duplicar
    seen: set[str] = set()
    out: list[str] = []
    for sel in (*extra, *UNIVERSAL_SELECTORS):
        if sel not in seen:
            seen.add(sel)
            out.append(sel)
    return tuple(out)


def _in_blocked_section(node) -> bool:
    for parent in node.parents:
        name = getattr(parent, "name", None)
        if name in ("aside", "nav", "footer", "header", "form", "figure"):
            return True
        cls = " ".join(parent.get("class") or []).lower()
        pid = (parent.get("id") or "").lower()
        blob = f"{cls} {pid}"
        if any(x in blob for x in BLOCKED_SECTION_HINTS):
            return True
    return False


def _container_score(el) -> int:
    if not el:
        return 0
    ps = [
        p for p in el.find_all("p", recursive=True)
        if not _in_blocked_section(p) and len(p.get_text(strip=True)) > 35
    ]
    if not ps:
        return 0
    text_len = sum(len(p.get_text(strip=True)) for p in ps)
    score = text_len + len(ps) * 120
    # Penaliza contenedores que mezclan cuerpo con módulos relacionados / ads
    cls = " ".join(el.get("class") or []).lower()
    pid = (el.get("id") or "").lower()
    blob = f"{cls} {pid}"
    noise_nodes = el.select(
        ".inTextNews, .in-text-news, [class*='related'], [class*='recommend'], "
        ".articleAside, .revUnit, [class*='newsletter']"
    )
    score -= min(len(noise_nodes) * 900, 5000)
    # Preferir contenedores de cuerpo explícitos
    if any(x in blob for x in ("news-body", "articlebody", "article-body", "bodycontent", "newsType__content")):
        score += 1500
    if el.name in ("article", "main") and "news-body" not in blob and "bodycontent" not in blob:
        score -= 800
    return max(score, 0)


def _find_best_container(soup: BeautifulSoup, url: str):
    best_el = None
    best_score = 0
    domain_sels = _domain_selectors(url)

    # Preferir selectores del dominio si dan cuerpo usable
    for sel in domain_sels:
        for el in soup.select(sel):
            if _in_blocked_section(el):
                continue
            score = _container_score(el) + 2500  # boost dominio
            if score > best_score:
                best_score = score
                best_el = el
    if best_el and best_score >= 800:
        return best_el

    for sel in _selectors_for(url):
        for el in soup.select(sel):
            if _in_blocked_section(el):
                continue
            score = _container_score(el)
            if score > best_score:
                best_score = score
                best_el = el
    if best_el:
        return best_el
    return soup.find("article") or soup.find("main")


def _node_is_nested(node) -> bool:
    """Evita contar el mismo texto varias veces (p dentro de p, etc.)."""
    parent_names = [p.name for p in node.parents if getattr(p, "name", None)]
    if node.name == "p" and "p" in parent_names:
        return True
    if node.name == "figure" and "figure" in parent_names:
        return True
    return False


def _best_img_url(img, base_url: str = "") -> str | None:
    """URL de imagen: srcset (mayor resolución), data-*, src."""
    candidates: list[tuple[int, str]] = []

    def add(url: str | None, width: int = 0) -> None:
        if not url or url.startswith("data:") or url.startswith("blob:"):
            return
        url = unescape(url.strip())
        if base_url:
            url = urljoin(base_url, url)
        if not url.startswith("http"):
            return
        candidates.append((width, url))

    for attr in ("data-srcset", "data-src", "data-original", "data-lazy-src", "data-url"):
        raw = img.get(attr)
        if not raw:
            continue
        if " " in raw and ("w" in raw or "," in raw):
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                bits = part.rsplit(None, 1)
                if len(bits) == 2 and bits[1].endswith("w"):
                    try:
                        add(bits[0], int(bits[1][:-1]))
                    except ValueError:
                        add(bits[0])
                else:
                    add(part)
        else:
            add(raw, 1200)

    srcset = img.get("srcset") or ""
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.rsplit(None, 1)
        if len(bits) == 2 and bits[1].endswith("w"):
            try:
                add(bits[0], int(bits[1][:-1]))
            except ValueError:
                add(bits[0])
        else:
            add(part)

    add(img.get("src"), 400)
    add(img.get("data-src"), 800)

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _is_decorative_img(img) -> bool:
    src = (img.get("src") or img.get("data-src") or "").lower()
    alt = (img.get("alt") or "").lower()
    cls = " ".join(img.get("class") or []).lower()
    blob = f"{src} {alt} {cls}"
    if any(h in blob for h in IMG_SKIP_HINTS):
        return True
    try:
        w = int(img.get("width") or 0)
        h = int(img.get("height") or 0)
        if 0 < w <= 48 and 0 < h <= 48:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _caption_from_media(node, img) -> str | None:
    for cap in node.find_all("figcaption", recursive=True):
        text = _clean_paragraph(_node_text(cap))
        if text:
            return text
    for sel in (".caption", ".photo-caption", ".a_m_p", ".media-caption", "[class*='caption']"):
        cap = node.select_one(sel)
        if cap:
            text = _clean_paragraph(_node_text(cap))
            if text:
                return text
    for attr in ("aria-label", "title"):
        text = _clean_paragraph(img.get(attr, ""))
        if text:
            return text
    text = _clean_paragraph(img.get("alt", ""))
    if text:
        return text
    # Pie en hermano siguiente (ABC, Heraldo, etc.)
    sib = node.find_next_sibling(["p", "span", "div", "figcaption"])
    if sib:
        text = _clean_paragraph(_node_text(sib))
        if text and len(text) < 220 and not _is_metadata(text):
            return text
    return None


def _is_media_container(node) -> bool:
    if not node or not getattr(node, "name", None):
        return False
    if node.name in ("figure", "picture"):
        return True
    if node.name not in ("div", "section", "span", "a"):
        return False
    if not node.find("img"):
        return False
    cls = " ".join(node.get("class") or []).lower()
    pid = (node.get("id") or "").lower()
    blob = f"{cls} {pid}"
    return any(h in blob for h in MEDIA_CONTAINER_HINTS)


def _figure_block(node, base_url: str = "") -> ArticleBlock | None:
    img = node.find("img")
    if not img or _is_decorative_img(img):
        source = node.find("source")
        if source and source.get("srcset"):
            src = _best_img_url(source, base_url)
            caption = _caption_from_media(node, img) if img else None
            if src:
                cap = caption or "Imagen del artículo"
                return ("image", f"{cap}\n{src}")
        return None
    src = _best_img_url(img, base_url)
    if not src:
        return None
    caption = _caption_from_media(node, img) or "Imagen del artículo"
    return ("image", f"{caption}\n{src}")


def _blocks_from_container(container, base_url: str = "") -> list[ArticleBlock]:
    if not container:
        return []

    blocks: list[ArticleBlock] = []
    seen_imgs: set[str] = set()
    # Solo etiquetas de contenido real. Los div/section genéricos mezclan
    # chrome de la página (byline, relacionados, tags) en un solo bloque.
    walk_tags = ["h2", "h3", "p", "figure", "picture", "blockquote", "div", "section"]

    for node in container.find_all(walk_tags, recursive=True):
        if _in_blocked_section(node) or _node_is_nested(node):
            continue

        if node.name in ("figure", "picture") or (
            node.name in ("div", "section") and _is_media_container(node)
        ):
            if node.name in ("div", "section") and node.find_parent(["figure", "picture"]):
                continue
            if node.find_parent("figcaption"):
                continue
            fb = _figure_block(node, base_url)
            if fb:
                img_url = fb[1].split("\n", 1)[-1]
                key = _norm_key(img_url.split("?")[0])
                if key not in seen_imgs:
                    seen_imgs.add(key)
                    blocks.append(fb)
            continue

        # div/section no mediáticos: no convertir su texto agregado en párrafo
        if node.name in ("div", "section"):
            continue

        if node.find_parent(["figure", "picture"]) and node.name == "p":
            continue
        if node.find_parent(lambda t: t and _is_media_container(t)) and node.name == "p":
            parent = node.find_parent(lambda t: t and _is_media_container(t))
            if parent and node in parent.find_all("p", recursive=False):
                continue

        if node.name in ("h2", "h3"):
            heading = _clean_heading(_node_text(node))
            if not heading:
                continue
            kind = "subtitle" if node.name == "h2" else "section"
            blocks.append((kind, heading))
            continue

        if node.name == "blockquote":
            text = _clean_paragraph(_node_text(node))
            if text:
                blocks.append(("paragraph", f"«{text}»"))
            continue

        text = _clean_paragraph(_node_text(node))
        if not text or _is_metadata(text):
            continue
        blocks.append(("paragraph", text))

    # Imágenes sueltas no envueltas en figure (El Mundo, 20minutos, etc.)
    for img in container.find_all("img"):
        if _in_blocked_section(img) or _is_decorative_img(img):
            continue
        if img.find_parent(["figure", "picture"]) or img.find_parent(_is_media_container):
            continue
        src = _best_img_url(img, base_url)
        if not src:
            continue
        key = _norm_key(src.split("?")[0])
        if key in seen_imgs:
            continue
        seen_imgs.add(key)
        cap = _clean_paragraph(img.get("alt", "")) or "Imagen del artículo"
        blocks.append(("image", f"{cap}\n{src}"))

    deduped: list[ArticleBlock] = []
    seen: set[str] = set()
    for kind, text in blocks:
        if kind == "paragraph":
            key = _norm_key(text)
            if not key or key in seen:
                continue
            # Evitar párrafos que son prefijo/duplicado casi total de otro ya visto
            if any(key in s or s in key for s in seen if min(len(key), len(s)) > 80):
                if any(len(key) <= len(s) for s in seen if key in s or s in key):
                    continue
            seen.add(key)
        deduped.append((kind, text))
    return deduped


def _opening_image_block(soup: BeautifulSoup, base_url: str = "") -> ArticleBlock | None:
    """Foto de apertura (p. ej. .innerArticle__opening en El Confidencial)."""
    for sel in (
        ".innerArticle__opening figure",
        ".innerArticle__opening",
        "article .opening figure",
        "article header figure",
        ".article-header figure",
        ".articleHeader figure",
    ):
        node = soup.select_one(sel)
        if not node:
            continue
        fb = _figure_block(node if node.name in ("figure", "picture", "div", "section") else node, base_url)
        if fb:
            return fb
        fig = node.find(["figure", "picture"]) or node
        fb = _figure_block(fig, base_url)
        if fb:
            return fb
    return None


def _blocks_from_noscript(soup: BeautifulSoup) -> list[ArticleBlock]:
    best: list[ArticleBlock] = []
    for ns in soup.find_all("noscript"):
        inner = ns.decode_contents()
        if len(inner) < 400:
            continue
        inner_soup = BeautifulSoup(inner, "html.parser")
        blocks = _blocks_from_container(inner_soup, base_url="")
        if len(blocks) > len(best):
            best = blocks
    return best


def _discover_embed_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for iframe in soup.find_all("iframe", src=True):
        src = urljoin(base_url, iframe["src"])
        if not any(h in src.lower() for h in EMBED_HOSTS):
            continue
        if "exposure.co" in src:
            src = src.split("?")[0]
        if src not in seen:
            seen.add(src)
            urls.append(src)
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if "exposure.co/" in href and href not in seen:
            clean = href.split("?")[0]
            seen.add(clean)
            urls.append(clean)
    return urls


def _format_paragraph(text: str) -> str:
    text = _norm(text)
    match = QA_PREFIX.match(text)
    if match:
        label = match.group(1).capitalize() + "."
        rest = match.group(2).strip()
        if len(rest) > 50:
            return f"{label}\n\n{rest}"
    return text


def _format_article(
    blocks: list[ArticleBlock] | list[str],
    *,
    headline: str | None = None,
) -> str:
    if blocks and isinstance(blocks[0], str):
        blocks = [("paragraph", p) for p in blocks]

    parts: list[str] = []
    if headline:
        headline = SITE_SUFFIX.sub("", _norm(headline))
        if headline:
            parts.append(headline)

    for kind, text in blocks:
        text = _norm(text)
        if not text:
            continue
        if kind == "subtitle":
            if not parts or _norm_key(text) not in _norm_key(parts[-1]):
                parts.append(text)
        elif kind == "section":
            parts.append(text)
        elif kind == "image":
            lines = text.split("\n", 1)
            if len(lines) == 2:
                parts.append(f"🖼 {lines[0]}\n{lines[1]}")
            else:
                parts.append(f"🖼 {text}")
        else:
            parts.append(_format_paragraph(text))

    return "\n\n".join(parts)


def _split_text_into_paragraphs(text: str) -> list[str]:
    text = _norm(text)
    if not text:
        return []

    chunks = re.split(r"(?<=\.)\s+(?=(?:Pregunta|Respuesta)\.\s)", text)
    paragraphs: list[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer.strip():
            paragraphs.append(buffer.strip())
        buffer = ""

    for chunk in chunks:
        sentences = re.split(r"(?<=[.!?…»\"])\s+(?=[A-ZÁÉÍÓÚÑ«\"(])", chunk.strip())
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if QA_PREFIX.match(sentence):
                flush()
                paragraphs.append(sentence)
                continue
            if not buffer:
                buffer = sentence
            elif len(buffer) + len(sentence) < 520:
                buffer = f"{buffer} {sentence}"
            else:
                flush()
                buffer = sentence
        flush()

    return _dedupe_paragraphs(paragraphs) if paragraphs else [text]


def _json_ld_bodies(soup: BeautifulSoup) -> list[str]:
    bodies: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if "Article" not in str(item.get("@type", "")):
                continue
            body = item.get("articleBody") or item.get("description") or ""
            if isinstance(body, str):
                body = _norm(body)
                if len(body) > 80:
                    bodies.append(body)
    return bodies


def _extract_headline(soup: BeautifulSoup) -> str | None:
    for prop in ("og:title", "twitter:title"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            title = SITE_SUFFIX.sub("", _norm(tag["content"]))
            if len(title) > 15:
                return title
    h1 = soup.find("h1")
    if h1:
        title = _clean_paragraph(h1.get_text(" ", strip=True))
        if title and len(title) > 15:
            return title
    return None


def _merge_lead(blocks: list[ArticleBlock], soup: BeautifulSoup) -> list[ArticleBlock]:
    if any(k == "subtitle" for k, _ in blocks):
        return blocks
    if not blocks:
        return blocks
    root = soup.find("article") or soup.find("main")
    if not root:
        return blocks
    body_key = _norm_key(" ".join(t for _, t in blocks))
    for p in root.find_all("p", limit=8):
        lead = _clean_paragraph(p.get_text(" ", strip=True))
        if not lead or len(lead) < 40 or _is_metadata(lead):
            continue
        if _norm_key(lead) not in body_key:
            return [("subtitle", lead)] + blocks
        break
    return blocks


def _similar(a: str, b: str) -> bool:
    ka, kb = _norm_key(a), _norm_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    shorter, longer = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    return shorter in longer and len(shorter) / len(longer) > 0.75


def _clean_block_list(blocks: list[ArticleBlock], headline: str | None) -> list[ArticleBlock]:
    out: list[ArticleBlock] = []
    for kind, text in blocks:
        text = _norm(text)
        if not text:
            continue
        if headline and _similar(text, headline):
            continue
        if _is_embed_noise(text):
            continue
        if kind == "paragraph" and _is_metadata(text):
            continue
        if kind in ("subtitle", "section") and _is_kicker(text):
            continue
        if kind == "subtitle" and headline and _similar(text, headline):
            continue
        out.append((kind, text))
    return out


def _score_result(text: str, block_count: int, *, html_paragraphs: int = 0, images: int = 0) -> float:
    if not text:
        return 0.0
    low = text.lower()
    if any(x in low for x in ("please enable js", "enable javascript", "access denied", "captcha")):
        return 0.0
    length = len(text)
    if length < 120:
        return length * 0.3
    para_bonus = min(block_count, 25) * 80
    wall_penalty = 400 if block_count <= 1 and length > 600 else 0
    html_bonus = 2500 if html_paragraphs >= 3 else (1200 if html_paragraphs >= 2 else 0)
    image_bonus = images * 600
    return length + para_bonus + html_bonus + image_bonus - wall_penalty


def _merge_images(primary: list[ArticleBlock], donor: list[ArticleBlock]) -> list[ArticleBlock]:
    """Inserta imágenes del donor en primary si este no tiene ninguna."""
    if any(k == "image" for k, _ in primary):
        return primary
    images = [(i, b) for i, b in enumerate(donor) if b[0] == "image"]
    if not images:
        return primary
    # Insertar en orden relativo: tras el párrafo anterior del donor
    donor_paras = [i for i, (k, _) in enumerate(donor) if k == "paragraph"]
    merged = list(primary)
    insert_offset = 0
    for img_idx, (donor_idx, block) in enumerate(images):
        paras_before = sum(1 for i in range(donor_idx) if donor[i][0] == "paragraph")
        target = min(paras_before + insert_offset, len(merged))
        # Avanzar hasta después del párrafo N en merged
        para_count = 0
        pos = 0
        for pos, (k, _) in enumerate(merged):
            if k == "paragraph":
                para_count += 1
            if para_count >= paras_before:
                break
        insert_at = pos + 1 if paras_before > 0 else min(img_idx, len(merged))
        merged.insert(insert_at, block)
        insert_offset += 1
    return merged


def _paragraphs_from_plain(text: str) -> list[str]:
    """Convierte texto plano o multilínea en párrafos limpios."""
    text = _norm(text)
    if not text:
        return []
    raw_parts = re.split(r"\n{2,}", text) if "\n" in text else [text]
    paragraphs: list[str] = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        if "\n" in part:
            for line in part.split("\n"):
                line = _clean_paragraph(line)
                if line and not _is_metadata(line):
                    paragraphs.append(line)
        else:
            for p in _split_text_into_paragraphs(part):
                if p and not _is_metadata(p):
                    paragraphs.append(p)
    return _dedupe_paragraphs(paragraphs)


def _body_from_html(soup: BeautifulSoup, url: str) -> tuple[list[ArticleBlock], str | None]:
    headline = _extract_headline(soup)
    block_sets: list[list[ArticleBlock]] = []

    container = _find_best_container(soup, url)
    if container:
        block_sets.append(_blocks_from_container(container, url))

    ns_blocks = _blocks_from_noscript(soup)
    if ns_blocks:
        block_sets.append(ns_blocks)

    for sel in ("#post-content", "#post_content", ".article-main", "#news-body-cc", ".news-body-complete"):
        el = soup.select_one(sel)
        if el and el is not container:
            block_sets.append(_blocks_from_container(el, url))

    def _set_quality(blocks: list[ArticleBlock]) -> tuple[int, int]:
        paras = sum(1 for k, _ in blocks if k == "paragraph")
        chars = sum(len(t) for k, t in blocks if k == "paragraph")
        # Preferir más párrafos reales, no un único muro contaminado
        return (paras, chars)

    blocks = max(block_sets, key=_set_quality, default=[])

    opening = _opening_image_block(soup, url)
    if opening and blocks and not any(k == "image" for k, _ in blocks[:2]):
        img_key = _norm_key(opening[1].split("\n", 1)[-1].split("?")[0])
        existing = {
            _norm_key(t.split("\n", 1)[-1].split("?")[0])
            for k, t in blocks if k == "image"
        }
        if img_key not in existing:
            blocks = [opening] + blocks

    blocks = _merge_lead(blocks, soup)
    return blocks, headline


def _collect_candidates(
    html: str,
    page_url: str,
    fallback_headline: str | None,
) -> list[tuple[float, list[ArticleBlock], str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    headline = _extract_headline(soup) or fallback_headline
    if "exposure.co" in urlparse(page_url).netloc and fallback_headline:
        headline = fallback_headline
    out: list[tuple[float, list[ArticleBlock], str | None]] = []

    html_blocks, h = _body_from_html(soup, page_url)
    h = h or headline
    if html_blocks:
        html_blocks = _clean_block_list(html_blocks, h)
        html_paras = sum(1 for k, _ in html_blocks if k == "paragraph")
        html_imgs = sum(1 for k, _ in html_blocks if k == "image")
        text = _format_article(html_blocks, headline=h)
        out.append((
            _score_result(text, len(html_blocks), html_paragraphs=html_paras, images=html_imgs),
            html_blocks,
            h,
        ))

    for ld in _json_ld_bodies(soup):
        if _is_embed_noise(ld):
            continue
        paras = [("paragraph", p) for p in _paragraphs_from_plain(ld)]
        paras = _clean_block_list(paras, h)
        if not paras:
            continue
        text = _format_article(paras, headline=h)
        out.append((_score_result(text, len(paras)), paras, h))

    tf = _trafilatura_text(html, page_url)
    if tf and not _is_embed_noise(tf):
        paras = [("paragraph", p) for p in _paragraphs_from_plain(tf)]
        paras = _clean_block_list(paras, h)
        if paras:
            text = _format_article(paras, headline=h)
            out.append((_score_result(text, len(paras)), paras, h))

    return out


def _trafilatura_text(html: str, url: str) -> str | None:
    if not trafilatura:
        return None
    for favor in (True, False):
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=favor,
        )
        if text:
            text = _norm(text)
            if len(text) > 80 and "please enable js" not in text.lower():
                return text
    return None


def _find_amp_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel=lambda v: v and "amphtml" in v)
    if link and link.get("href"):
        return urljoin(base_url, link["href"])
    parsed = urlparse(base_url)
    if "/amp/" not in parsed.path:
        amp_path = parsed.path.rstrip("/") + "/amp"
        return parsed._replace(path=amp_path).geturl()
    return None


def _fetch_once(url: str, *, mode: str, impersonate: str | None, timeout: int) -> tuple[int, str]:
    headers = GOOGLEBOT_HEADERS if mode == "googlebot" else DEFAULT_HEADERS
    if mode == "cffi" and cffi_requests and impersonate:
        resp = cffi_requests.get(
            url, impersonate=impersonate, timeout=timeout, headers=headers, allow_redirects=True,
        )
        text = resp.text or resp.content.decode("utf-8", errors="replace")
        return resp.status_code, text
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    return resp.status_code, resp.text


def _referer_for_image(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "elpais.com" in host:
        return "https://elpais.com/"
    if "abc.es" in host:
        return "https://www.abc.es/"
    if "nationalgeographic" in host or "exposure" in host:
        return "https://historia.nationalgeographic.com.es/"
    parts = host.replace("www.", "").split(".")
    if len(parts) >= 2:
        return f"https://www.{parts[-2]}.{parts[-1]}/"
    return "https://www.google.com/"


def _looks_like_image(data: bytes, content_type: str = "") -> bool:
    if len(data) < 200:
        return False
    ct = content_type.lower()
    if ct.startswith("image/"):
        return True
    return data[:3] in (b"\xff\xd8\xff", b"\x89PN", b"GIF") or data[:4] == b"RIFF"


def fetch_image_bytes(url: str, *, referer: str | None = None, timeout: int = 25) -> bytes | None:
    """Descarga bytes de imagen para subirla a Telegram (visor nativo, sin navegador)."""
    referer = referer or _referer_for_image(url)
    headers = {
        **DEFAULT_HEADERS,
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    strategies: list[tuple[str, str | None]] = []
    if cffi_requests:
        for browser in ("chrome131", "chrome120", "safari17_0"):
            strategies.append(("cffi", browser))
    strategies.append(("default", None))

    for mode, impersonate in strategies:
        try:
            if mode == "cffi" and cffi_requests and impersonate:
                resp = cffi_requests.get(
                    url, impersonate=impersonate, timeout=timeout,
                    headers=headers, allow_redirects=True,
                )
            else:
                resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code >= 400:
                continue
            data = resp.content
            ct = resp.headers.get("content-type", "")
            if _looks_like_image(data, ct):
                return data
        except Exception:
            continue
    return None


def fetch_html(url: str, *, timeout: int = 35) -> str:
    """Descarga HTML probando varias estrategias anti-bot."""
    strategies: list[tuple[str, str | None]] = []
    if cffi_requests:
        for browser in ("chrome131", "chrome120", "safari17_0", "edge101"):
            strategies.append(("cffi", browser))
    strategies.extend([("googlebot", None), ("default", None)])

    last_error: Exception | None = None
    best_status = 0
    best_text = ""

    for mode, impersonate in strategies:
        try:
            status, text = _fetch_once(url, mode=mode, impersonate=impersonate, timeout=timeout)
            if status >= 400:
                continue
            if len(text) > len(best_text):
                best_status = status
                best_text = text
            # 200 con contenido razonable: suficiente
            if status == 200 and len(text) > 500 and "<p" in text.lower():
                return text
        except Exception as exc:
            last_error = exc
            continue

    if best_text:
        return best_text

    # AMP como último recurso de fetch
    try:
        _, probe = _fetch_once(url, mode="default", impersonate=None, timeout=timeout)
        amp_url = _find_amp_url(probe, url)
        if amp_url and amp_url != url:
            for mode, impersonate in strategies[:3]:
                try:
                    status, text = _fetch_once(amp_url, mode=mode, impersonate=impersonate, timeout=timeout)
                    if status == 200 and len(text) > 300:
                        return text
                except Exception:
                    continue
    except Exception as exc:
        last_error = exc

    if last_error:
        raise last_error
    raise requests.HTTPError(f"No se pudo descargar {url} (status {best_status})")


def blocks_to_segments(blocks: list[ArticleBlock], *, headline: str | None = None) -> list[dict]:
    """Convierte bloques en segmentos para Telegram (texto / imagen)."""
    segments: list[dict] = []
    if headline:
        headline = SITE_SUFFIX.sub("", _norm(headline))
        if headline:
            segments.append({"type": "text", "content": headline})

    for kind, text in blocks:
        text = _norm(text)
        if not text:
            continue
        if kind == "image":
            lines = text.split("\n", 1)
            if len(lines) == 2:
                segments.append({"type": "image", "caption": lines[0], "url": lines[1]})
            else:
                segments.append({"type": "image", "caption": "Imagen del artículo", "url": text})
        elif kind == "subtitle":
            if not segments or _norm_key(text) not in _norm_key(segments[-1].get("content", "")):
                segments.append({"type": "text", "content": text})
        elif kind == "section":
            segments.append({"type": "text", "content": text})
        else:
            segments.append({"type": "text", "content": _format_paragraph(text)})
    return segments


def extract_article_blocks(url: str, html: str | None = None) -> tuple[list[ArticleBlock], str | None] | None:
    html = html or fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    headline = _extract_headline(soup)

    candidates: list[tuple[float, list[ArticleBlock], str | None]] = []
    candidates.extend(_collect_candidates(html, url, headline))

    for embed_url in _discover_embed_urls(soup, url):
        if embed_url.rstrip("/") == url.rstrip("/"):
            continue
        try:
            embed_html = fetch_html(embed_url)
            candidates.extend(_collect_candidates(embed_html, embed_url, headline))
        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_blocks, best_headline = candidates[0]
    if best_score < 100:
        return None

    # Si el ganador no tiene imágenes, fusionar del candidato HTML con más fotos
    if not any(k == "image" for k, _ in best_blocks):
        img_donors = [
            b for s, b, _ in candidates
            if any(k == "image" for k, _ in b)
        ]
        if img_donors:
            donor = max(img_donors, key=lambda b: sum(1 for k, _ in b if k == "image"))
            best_blocks = _merge_images(best_blocks, donor)

    return best_blocks, best_headline


def extract_article(url: str, html: str | None = None) -> str | None:
    result = extract_article_blocks(url, html=html)
    if not result:
        return None
    blocks, headline = result
    return _format_article(blocks, headline=headline)
