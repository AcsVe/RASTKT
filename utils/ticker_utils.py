import json
import time
import xml.etree.ElementTree as ET
import requests

from models import get_setting, set_setting

DEFAULT_CONFIG = {
    'enabled': False,
    'html': '',           # rich HTML from the Quill editor (paragraphs, links, inline styles)
    'speedSeconds': 25,   # seconds for one full loop across the screen — lower = faster
    'pulse': False,       # blinking/pulsing show-hide effect
    'logoBetween': False, # insert the org logo between each segment
    'rssUrl': '',         # optional RSS feed to pull extra items from
}

_rss_cache = {}  # url -> (fetched_at, items)
_RSS_CACHE_SECONDS = 300


def get_ticker_config():
    raw = get_setting('ticker_config')
    if not raw:
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(raw)
    except Exception:
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})
    return merged


def set_ticker_config(cfg):
    merged = get_ticker_config()
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})
    set_setting('ticker_config', json.dumps(merged, ensure_ascii=False))
    return merged


def fetch_rss_items(url, limit=12):
    """Fetch and lightly parse an RSS 2.0 (or Atom-ish) feed into
    [{title, link}, ...]. Cached for a few minutes so every page view on
    the site doesn't re-fetch the feed. Fails soft (returns []) on any
    network/parse error — a broken feed should never take the ticker (or
    the page) down."""
    if not url:
        return []

    now = time.time()
    cached = _rss_cache.get(url)
    if cached and (now - cached[0]) < _RSS_CACHE_SECONDS:
        return cached[1]

    items = []
    try:
        r = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0 (TicketingTicker/1.0)'})
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            # RSS 2.0: rss/channel/item ; Atom: feed/entry
            for item in root.findall('.//item')[:limit]:
                title_el = item.find('title')
                link_el = item.find('link')
                title = (title_el.text or '').strip() if title_el is not None else ''
                link = (link_el.text or '').strip() if link_el is not None else ''
                if title:
                    items.append({'title': title, 'link': link})
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('.//atom:entry', ns)[:limit]:
                    title_el = entry.find('atom:title', ns)
                    link_el = entry.find('atom:link', ns)
                    title = (title_el.text or '').strip() if title_el is not None else ''
                    link = (link_el.get('href') if link_el is not None else '') or ''
                    if title:
                        items.append({'title': title, 'link': link})
    except Exception as e:
        print(f"[ticker] RSS fetch/parse failed for {url}: {e}", flush=True)
        items = []

    _rss_cache[url] = (now, items)
    return items


def build_ticker_payload():
    """What the frontend needs to render the ticker: the config plus any
    resolved RSS items."""
    cfg = get_ticker_config()
    payload = dict(cfg)
    if cfg.get('enabled') and cfg.get('rssUrl'):
        payload['rssItems'] = fetch_rss_items(cfg['rssUrl'])
    else:
        payload['rssItems'] = []
    return payload
