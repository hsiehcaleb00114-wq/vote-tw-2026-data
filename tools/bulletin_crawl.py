"""列出中選會選舉公報網站（eebulletin.cec.gov.tw）115 年的所有 PDF。

用法：python tools/bulletin_crawl.py <輸出.tsv>
輸出欄位：縣市資料夾、職位資料夾、子資料夾（鄉鎮市區，可空）、檔名、網址
"""
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = 'https://eebulletin.cec.gov.tw/'
UA = {'User-Agent': 'vote-tw-2026-data bulletin crawler'}


def listing(path):
    url = BASE + '?dir=' + urllib.parse.quote(path)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                html = r.read().decode('utf-8', 'replace')
            break
        except Exception:
            time.sleep(2 + attempt * 3)
    else:
        raise RuntimeError(f'無法讀取 {url}')
    dirs = sorted({urllib.parse.unquote(m) for m in re.findall(r'href="\?dir=([^"]+)"', html)})
    dirs = [d for d in dirs if d.startswith(path + '/')]
    pdfs = sorted({m for m in re.findall(r'href="(115/[^"]+\.pdf)"', html)})
    return dirs, pdfs


def walk(path, out):
    dirs, pdfs = listing(path)
    for p in pdfs:
        parts = p.split('/')
        county, office = parts[1], parts[2]
        sub = parts[3] if len(parts) > 4 else ''
        out.write('\t'.join([county, office, sub, parts[-1], BASE + urllib.parse.quote(p)]) + '\n')
    for d in dirs:
        if '有聲公報' in d:
            continue
        walk(d, out)


if __name__ == '__main__':
    with open(sys.argv[1], 'w', encoding='utf-8', newline='\n') as fh:
        walk('115', fh)
