"""下載選舉公報 PDF，擷取文字片段（含位置與字級）存成快取，PDF 本身不保留。

用法：python tools/bulletin_extract.py <bulletin_crawl 輸出.tsv> <快取資料夾> [並行數，預設 4]
每個 PDF 產生一個 JSON：{"file": 檔名, "pages": [[[x0, top, size, text], ...], ...]}
已有快取的檔案會略過，可以中斷後重跑。需要 PyMuPDF（pip install pymupdf）。
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pymupdf

UA = {'User-Agent': 'vote-tw-2026-data bulletin extractor'}


def fetch(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception:
            time.sleep(3 + attempt * 5)
    raise RuntimeError(f'下載失敗：{url}')


def extract(data):
    pages = []
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        for page in doc:
            spans = []
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for s in line['spans']:
                        text = s['text'].strip()
                        if text:
                            x0, top = s['bbox'][0], s['bbox'][1]
                            spans.append([round(x0, 1), round(top, 1), round(s['size'], 1), text])
            pages.append(spans)
    return pages


def work(row, cache):
    county, office, sub, name, url = row
    out = os.path.join(cache, hashlib.sha1(url.encode()).hexdigest() + '.json')
    if os.path.exists(out):
        return 'cached'
    pages = extract(fetch(url))
    tmp = out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump({'county': county, 'office': office, 'sub': sub, 'file': name, 'url': url, 'pages': pages}, fh, ensure_ascii=False)
    os.replace(tmp, out)
    return 'ok'


def main():
    rows = [line.rstrip('\n').split('\t') for line in open(sys.argv[1], encoding='utf-8') if line.strip()]
    cache = sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    os.makedirs(cache, exist_ok=True)
    done = failed = 0
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(work, r, cache): r for r in rows}
        for f in futures:
            try:
                f.result()
                done += 1
            except Exception as e:
                failed += 1
                print(f'✗ {futures[f][3]}：{e}', file=sys.stderr)
            if (done + failed) % 250 == 0:
                print(f'{done + failed}/{len(rows)}', flush=True)
    print(f'完成 {done}，失敗 {failed}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    main()
