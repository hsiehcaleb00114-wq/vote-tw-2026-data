"""掃描公報（橫排姓名版型）：在整頁 OCR 裡找出候選人姓名，再到姓名上方或左方找大號次字，
把「號次字＋姓名」拼成一行交給 OCR。

python -I anchor.py build <scanned.tsv>   產生 cells_b/*.png 與 anchors.json
python -I anchor.py collect <scanned.tsv> 讀 OCR 結果，輸出 results_b.json
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, 'C:/VoteTW/.pylib')
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, 'C:/VoteTW/.ocr')
sys.path.insert(0, 'C:/VoteTW/vote-tw-2026-data/tools')
import bulletin_match as bm  # noqa: E402
from compose import compose, ink, runs, strip_borders  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
HERE = 'C:/VoteTW/.ocr'
WORK = os.environ.get('OCR_WORK', 'C:/VoteTW/.ocr/w2')
TAG = os.environ.get('ANCHOR_TAG', '')
CJK = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003ffff]')


def char_boxes(words):
    """每個 OCR 行 -> [(字, x0, y0, x1, y1)]，多字的 word 平均切寬度"""
    lines = defaultdict(list)
    for x, y, w, h, li, text in words:
        t = unicodedata.normalize('NFKC', text).translate(bm.VARIANTS)
        n = len(t)
        for i, ch in enumerate(t):
            lines[li].append((ch, x + w * i / n, y, x + w * (i + 1) / n, y + h))
    return lines


def find_names(lines, names):
    """在各行找候選人姓名（只看漢字），姓名前後同一行的字要離得夠遠，避免是內文裡的片段"""
    hits = []
    for li, chars in lines.items():
        cj = [c for c in chars if CJK.match(c[0])]
        text = ''.join(c[0] for c in cj)
        for name in names:
            if len(name) < 2:
                continue
            start = 0
            while True:
                i = text.find(name, start)
                if i < 0:
                    break
                start = i + 1
                seg = cj[i:i + len(name)]
                x0, y0 = min(c[1] for c in seg), min(c[2] for c in seg)
                x1, y1 = max(c[3] for c in seg), max(c[4] for c in seg)
                h = y1 - y0
                if x1 - x0 < h * len(name) * 0.6:
                    continue  # 直排（整行被當成一行）不在這裡處理
                before = cj[i - 1] if i > 0 else None
                after = cj[i + len(name)] if i + len(name) < len(cj) else None
                if before and x0 - before[3] < h * 0.9:
                    continue
                if after and after[1] - x1 < h * 0.9:
                    continue
                hits.append((name, (int(x0), int(y0), int(x1), int(y1))))
    return hits


def digit_above(m, box):
    x0, y0, x1, y1 = box
    h = y1 - y0
    cx = (x0 + x1) / 2
    rx0, rx1 = int(max(0, cx - 3 * h)), int(min(m.shape[1], cx + 3 * h))
    ry0, ry1 = int(max(0, y0 - 5 * h)), int(max(0, y0 - 2))
    if ry1 - ry0 < h:
        return None
    reg = strip_borders(m[ry0:ry1, rx0:rx1])
    for a, b in reversed(runs(reg.any(axis=1), max(2, int(h * 0.15)))):
        if not (0.8 * h <= b - a <= 5 * h):
            continue
        cols = runs(reg[a:b].any(axis=0), max(2, int(h * 0.25)))
        keep = [(c0, c1) for c0, c1 in cols if abs((c0 + c1) / 2 + rx0 - cx) < 2.5 * h]
        if not keep or len(keep) > 3:
            return None
        return tuple(int(v) for v in (rx0 + keep[0][0], ry0 + a, rx0 + keep[-1][1], ry0 + b))
    return None


def digit_left(m, box):
    x0, y0, x1, y1 = box
    h = y1 - y0
    rx0, rx1 = int(max(0, x0 - 5 * h)), int(max(0, x0 - 2))
    ry0, ry1 = int(max(0, y0 - 1.5 * h)), int(min(m.shape[0], y1 + 1.5 * h))
    if rx1 - rx0 < h:
        return None
    reg = strip_borders(m[ry0:ry1, rx0:rx1])
    cols = runs(reg.any(axis=0), max(2, int(h * 0.5)))
    if not cols:
        return None
    c0, c1 = cols[-1]
    rows = runs(reg[:, c0:c1].any(axis=1), max(2, int(h * 0.15)))
    rows = [r for r in rows if 0.8 * h <= r[1] - r[0] <= 5 * h]
    if len(rows) != 1:
        return None
    return tuple(int(v) for v in (rx0 + c0, ry0 + rows[0][0], rx0 + c1, ry0 + rows[0][1]))


def load_pool():
    data = json.load(open('C:/VoteTW/vote-tw-2026-data/election.json', encoding='utf-8'))
    pool = defaultdict(lambda: defaultdict(list))
    for r in data['races']:
        rk = (r['office'], r['county'], r.get('district') or '')
        for c in r['candidates']:
            pool[(r['county'], r['office'])][bm.cjk(c['name'])].append(rk)
    return pool


def build(tsv):
    pool = load_pool()
    towns_of = bm.load_towns(os.path.join(HERE, 'villages.txt'))
    out_dir = os.path.join(WORK, 'cells_b' + TAG)
    os.makedirs(out_dir, exist_ok=True)
    anchors = []
    pairs = []
    # 同一個 PDF 可能放在多個職位資料夾：每頁只做一次，但名字池用所有職位
    by_key = defaultdict(list)
    for line in open(tsv, encoding='utf-8'):
        row = line.rstrip('\n').split('\t')
        if len(row) < 5:
            continue
        key = hashlib.md5(row[0].encode()).hexdigest()[:12]
        by_key[(row[1], row[4], row[3])].append((key, row))
    for (_, _, _), entries in by_key.items():
        key, row = entries[0]
        done = os.path.join(WORK, 'png', f'{key}.done')
        if not os.path.exists(done):
            continue
        county = bm.county_of(row[1])
        names = {}
        for _, r in entries:
            office = bm.office_of(r[2])
            doc = {'sub': r[3], 'file': r[4]}
            scope = bm.file_scope(doc, towns_of[county])
            for nm, rks in pool[(county, office)].items():
                if scope:
                    rks = [rk for rk in rks if bm.town_of(rk[2], scope)]
                if len(rks) == 1:
                    if nm in names and names[nm] and names[nm][0] != rks[0]:
                        names[nm] = None  # 同檔不同職位同名：無法分辨
                    elif nm not in names:
                        names[nm] = (rks[0], r[0])
        names = {k: v for k, v in names.items() if v}
        for pi in range(int(open(done).read())):
            p = f'{key}_{pi}'
            pj = os.path.join(WORK, 'pages', f'{p}.json')
            if not os.path.exists(pj):
                continue
            page = json.load(open(pj, encoding='utf-8'))
            hits = find_names(char_boxes(page['words']), names)
            if not hits:
                continue
            img = Image.open(os.path.join(WORK, 'png', f'{p}.png')).convert('RGB')
            m = ink(img)
            gray = Image.fromarray(np.where(m, 0, 255).astype(np.uint8))
            for name, box in hits:
                for how, fn in (('above', digit_above), ('left', digit_left)):
                    d = fn(m, box)
                    if not d:
                        continue
                    i = len(anchors)
                    png = os.path.join(out_dir, f'{i}.png')
                    compose([gray.crop(d), gray.crop(box)]).save(png)
                    rk, url = names[name]
                    anchors.append({'i': i, 'page': p, 'name': name, 'rk': rk, 'url': url, 'how': how,
                                    'box': box, 'digit': d})
                    pairs.append((png, os.path.join(out_dir, f'{i}.json')))
    json.dump(anchors, open(os.path.join(WORK, f'anchors{TAG}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    with open(os.path.join(WORK, f'list_b{TAG}.txt'), 'w', encoding='utf-8') as fh:
        for a, b in pairs:
            fh.write(f'{a.replace(os.sep, "/")}\t{b.replace(os.sep, "/")}\n')
    print(len(anchors), 'anchors')


def collect():
    anchors = json.load(open(os.path.join(WORK, f'anchors{TAG}.json'), encoding='utf-8'))
    out = []
    for a in anchors:
        f = os.path.join(WORK, 'cells_b' + TAG, f'{a["i"]}.json')
        if not os.path.exists(f):
            continue
        words = json.load(open(f, encoding='utf-8'))['words']
        text = ''.join(w[5] for w in words)
        mt = re.match(r'^(\d{1,2})(?!\d)', text)
        a['ocr'] = text
        a['number'] = int(mt.group(1)) if mt else None
        out.append(a)
    json.dump(out, open(os.path.join(WORK, f'results_b{TAG}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(out), 'read', sum(a['number'] is not None for a in out), 'with number')


if __name__ == '__main__':
    if sys.argv[1] == 'build':
        build(sys.argv[2])
    else:
        collect()
