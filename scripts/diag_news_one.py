"""Dev diagnostic: fetch Google News RSS for one company and show gate outcomes."""
from __future__ import annotations

import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, "src")
from norway_company_agent.news import UA, exact_title_match  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "EQUINOR ASA"
query = urllib.parse.quote(f'"{name}" when:2y')
url = f"https://news.google.com/rss/search?q={query}&hl=no&gl=NO&ceid=NO:no"
request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
with urllib.request.urlopen(request, timeout=25) as response:
    raw = response.read(2_000_000)
root = ET.fromstring(raw)
items = root.findall(".//item")
print(f"query={name!r} rss_items={len(items)}")
matched = 0
for node in items[:10]:
    title = str(node.findtext("title") or "")
    hit = exact_title_match(name, title)
    matched += int(hit)
    print(f"  {'PASS' if hit else 'miss'}  {title[:110]}")
print("passed:", matched)
