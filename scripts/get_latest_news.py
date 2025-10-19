import os
import re
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

BASE_URL = os.getenv("FOLLOWIN_NEWS_URL", "https://followin.io/zh-Hant/news")
OUTPUT_PATH = os.getenv("LATEST_NEWS_FILE", "./data/latest_news.txt")
TIMEOUT = float(os.getenv("LATEST_NEWS_TIMEOUT", "30"))
UA = os.getenv("LATEST_NEWS_UA", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _clean(t: str | None) -> str:
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()


def fetch_html(url: str) -> str:
    headers = {"User-Agent": UA, "Accept-Language": "zh-Hant,zh;q=0.9,en;q=0.8"}
    with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def extract_items(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    def add_item(title: str, url: str, source: str, published: str, summary: str):
        if url in seen:
            return
        seen.add(url)
        items.append({
            "title": title or "N/A",
            "url": url,
            "source": source or "N/A",
            "published": published or "N/A",
            "summary": summary or "N/A",
        })

    # Strategy 1: parse cards
    for card in soup.select('article, div[class*="card"], li[class*="news"], div[class*="news"], section[class*="news"]'):
        a = card.find('a', href=True)
        if not a:
            continue
        href = a.get('href', '')
        if '/news/' not in href:
            continue
        url = urljoin(BASE_URL, href)
        title_el = card.find(['h1','h2','h3']) or a
        title = _clean(title_el.get_text())
        src_el = card.select_one('.source, [class*="source"], [class*="publisher"], [class*="from"]')
        time_el = card.select_one('time, [class*="time"], [class*="date"]')
        desc_el = card.select_one('.desc, [class*="desc"], [class*="summary"], [class*="snippet"], p')
        source = _clean(src_el.get_text()) if src_el else ""
        published = _clean(time_el.get_text()) if time_el else ""
        summary = _clean(desc_el.get_text()) if desc_el else ""
        add_item(title, url, source, published, summary)

    # Strategy 2: generic anchors
    for a in soup.select('a[href]'):
        href = a.get('href', '')
        if '/news/' not in href:
            continue
        url = urljoin(BASE_URL, href)
        title = _clean(a.get_text())
        parent = a
        source = published = summary = ""
        for _ in range(3):
            parent = parent.parent
            if not parent:
                break
            t = parent.find(['h1','h2','h3'])
            if t and not title:
                title = _clean(t.get_text())
            src = parent.find(attrs={"class": re.compile("source|publisher|from", re.I)})
            tm = parent.find(attrs={"class": re.compile("time|date", re.I)})
            ds = parent.find(attrs={"class": re.compile("desc|summary|snippet", re.I)})
            if src and not source:
                source = _clean(src.get_text())
            if tm and not published:
                published = _clean(tm.get_text())
            if ds and not summary:
                summary = _clean(ds.get_text())
        add_item(title, url, source, published, summary)

    # Strategy 3: JSON-LD (schema.org)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            import json
            data = json.loads(script.string or "{}")
            if isinstance(data, dict):
                ld_items = data.get("@graph") or data.get("itemListElement") or [data]
            elif isinstance(data, list):
                ld_items = data
            else:
                ld_items = []
            for it in ld_items:
                if not isinstance(it, dict):
                    continue
                if it.get("@type") in ("NewsArticle", "Article", "BlogPosting"):
                    title = _clean(it.get("headline") or it.get("name"))
                    url = it.get("url") or ""
                    url = urljoin(BASE_URL, url) if url else url
                    source = _clean((it.get("publisher") or {}).get("name")) if isinstance(it.get("publisher"), dict) else _clean(str(it.get("publisher") or ""))
                    published = _clean(it.get("datePublished") or it.get("dateModified") or "")
                    summary = _clean(it.get("description") or "")
                    if url:
                        add_item(title, url, source, published, summary)
        except Exception:
            pass

    return items


def save_text(items: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Source: {BASE_URL}\n")
        f.write(f"Total: {len(items)}\n")
        f.write("="*80 + "\n")
        for i, it in enumerate(items, 1):
            f.write(f"{i}. {it['title']}\n")
            f.write(f"Link: {it['url']}\n")
            f.write(f"Source: {it['source']}\n")
            f.write(f"Published: {it['published']}\n")
            f.write(f"Summary: {it['summary']}\n")
            f.write("-"*80 + "\n")


def main():
    html = fetch_html(BASE_URL)
    items = extract_items(html)
    save_text(items, OUTPUT_PATH)
    print(f"Saved {len(items)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()