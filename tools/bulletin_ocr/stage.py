"""掃描公報 OCR 流程（可重跑，已完成的步驟會跳過）。

python -I stage.py fetch   下載 PDF、轉成 150dpi PNG（轉完刪 PDF）
python -I stage.py pages   整頁 OCR 清單 -> ocr.ps1
python -I stage.py cells   依表頭切格、拼字 -> cells/，並產生格子 OCR 清單
python -I stage.py collect 輸出 results.json：每格 OCR 文字
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, 'C:/VoteTW/.pylib')
HERE = 'C:/VoteTW/.ocr'
WORK = os.environ.get('OCR_WORK', 'C:/VoteTW/.ocr/w2')
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf-8')
SCANNED = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'scanned.tsv')


def items():
    for line in open(SCANNED, encoding='utf-8'):
        if line.strip():
            url = line.split('\t')[0]
            yield hashlib.md5(url.encode()).hexdigest()[:12], line.rstrip('\n').split('\t')


def fetch_one(arg):
    import pymupdf
    key, row = arg
    done = os.path.join(WORK, 'png', f'{key}.done')
    if os.path.exists(done):
        return
    pdf = os.path.join(WORK, 'pdf', f'{key}.pdf')
    if not os.path.exists(pdf) or os.path.getsize(pdf) < 1000:
        for attempt in range(3):
            try:
                req = urllib.request.Request(row[0], headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=180) as r:
                    body = r.read()
                open(pdf, 'wb').write(body)
                break
            except Exception as e:
                print('retry', key, e, flush=True)
    doc = pymupdf.open(pdf)
    for i, p in enumerate(doc):
        # 盡量 250dpi，但 OCR 圖片最長邊上限 10000px
        dpi = min(250, int(9800 / (max(p.rect.width, p.rect.height) / 72)))
        p.get_pixmap(dpi=dpi).save(os.path.join(WORK, 'png', f'{key}_{i}.png'))
    n = len(doc)
    doc.close()
    open(done, 'w').write(str(n))
    print('ok', key, n, row[4], flush=True)


def run_ocr(pairs, name):
    lst = os.path.join(WORK, f'list_{name}.txt')
    with open(lst, 'w', encoding='utf-8') as fh:
        for a, b in pairs:
            if not os.path.exists(b):
                fh.write(f'{a}\t{b}\n')
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    os.path.join(HERE, 'ocr.ps1'), lst], check=True)


def pages_of(key):
    done = os.path.join(WORK, 'png', f'{key}.done')
    if not os.path.exists(done):
        return []
    return [f'{key}_{i}' for i in range(int(open(done).read()))]


def main():
    step = sys.argv[1]
    for d in ('pdf', 'png', 'pages', 'cells'):
        pass
    for d in ('pdf', 'png', 'pages', 'cells'):
        os.makedirs(os.path.join(WORK, d), exist_ok=True)
    all_items = list(items())
    if step == 'fetch':
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(fetch_one, all_items))
    elif step == 'pages':
        pairs = [(f'{WORK}/png/{p}.png', f'{WORK}/pages/{p}.json') for k, _ in all_items for p in pages_of(k)]
        run_ocr(pairs, 'pages')
    elif step == 'cells':
        import compose
        pairs = []
        for k, _ in all_items:
            for p in pages_of(k):
                cj = f'{WORK}/cells/{p}_cells.json'
                if not os.path.exists(cj):
                    sys.argv = ['', f'{WORK}/pages/{p}.json', f'{WORK}/png/{p}.png', f'{WORK}/cells', p]
                    try:
                        compose.main()
                    except Exception as e:
                        print('compose fail', p, e)
                        continue
                for i in range(len(json.load(open(cj, encoding='utf-8')))):
                    png = f'{WORK}/cells/{p}_{i}.png'
                    if os.path.exists(png):
                        pairs.append((png, f'{WORK}/cells/{p}_{i}.json'))
        run_ocr(pairs, 'cells')
    elif step == 'collect':
        out = []
        for k, row in all_items:
            for p in pages_of(k):
                cj = f'{WORK}/cells/{p}_cells.json'
                if not os.path.exists(cj):
                    continue
                for i, c in enumerate(json.load(open(cj, encoding='utf-8'))):
                    f = f'{WORK}/cells/{p}_{i}.json'
                    words = json.load(open(f, encoding='utf-8'))['words'] if os.path.exists(f) else []
                    out.append({'key': k, 'page': p, 'cell': i, 'url': row[0], 'county': row[1], 'office': row[2],
                                'sub': row[3], 'file': row[4], 'words': [w[5] for w in words],
                                'n_num': c.get('n_num'), 'n_name': c.get('n_name')})
        json.dump(out, open(os.path.join(WORK, 'results.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        print(len(out), 'cells')


if __name__ == '__main__':
    main()
