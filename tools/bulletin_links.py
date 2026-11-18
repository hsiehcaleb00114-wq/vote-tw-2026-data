"""每位參選人對應的選舉公報 PDF（給 App「查看原始資料（選舉公報）」用），輸出 TSV 給 apply_sources.mjs。

用法：python tools/bulletin_links.py <快取資料夾> <村里清單.txt> <輸出.tsv> [<OCR 整頁結果資料夾>]
  快取資料夾：bulletin_extract.py 的輸出
  OCR 整頁結果：tools/bulletin_ocr 的 pages/（掃描檔用，可省略）

依序判斷，找到就停：
  1. 參選人姓名出現在同縣市、同職位、涵蓋該鄉鎮的公報檔裡，而且只出現在一個檔 → 該檔，加上 #page=頁碼
  2. 同選區其他人的姓名只出現在同一個檔 → 該檔
  3. 檔名含村里名（村里長）且只有一個檔 → 該檔
  4. 涵蓋該鄉鎮（或全縣市）的檔只有一個 → 該檔
  都不符合就不輸出，寧缺勿錯。
"""
import csv
import hashlib
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bulletin_match as bm  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def main():
    cache, village_list, out = sys.argv[1:4]
    ocr_dir = sys.argv[4] if len(sys.argv) > 4 else None
    data = json.load(open(os.path.join(ROOT, 'election.json'), encoding='utf-8'))
    towns_of = bm.load_towns(village_list)

    ocr = {}
    if ocr_dir:
        for f in os.listdir(ocr_dir):
            if f.endswith('.json'):
                key, pi = f[:-5].rsplit('_', 1)
                words = json.load(open(os.path.join(ocr_dir, f), encoding='utf-8'))['words']
                ocr[(key, int(pi))] = bm.cjk(''.join(w[5] for w in words))

    files = defaultdict(dict)  # (縣市, 職位) -> url -> {label, scope, pages: [文字]}
    for f in os.listdir(cache):
        if not f.endswith('.json'):
            continue
        doc = json.load(open(os.path.join(cache, f), encoding='utf-8'))
        office, county = bm.office_of(doc['office']), bm.county_of(doc['county'])
        if not office or doc['url'] in files[(county, office)]:
            continue
        key = hashlib.md5(doc['url'].encode()).hexdigest()[:12]
        text_ok = sum(len(p) for p in doc['pages']) >= 20 and not bm.garbled(doc['pages'])
        pages = []
        for i, p in enumerate(bm.glyph_digits(doc['pages'])):
            t = ''
            if text_ok:
                t = ''.join(bm.cjk(s[3]) for s in p) + '|' + ''.join(
                    bm.cjk(w[3]) for w in bm.spaced_words(p) + bm.vertical_words(p))
            pages.append(t + '|' + ocr.get((key, i), ''))
        files[(county, office)][doc['url']] = {
            'label': (doc.get('sub') or '') + doc['file'],
            'scope': bm.file_scope(doc, towns_of[county]),
            'pages': pages,
        }

    rows, stats = [], defaultdict(int)
    for r in data['races']:
        county, office, district = r['county'], r['office'], r.get('district') or ''
        town = bm.town_of(district, towns_of[county]) if office not in ('mayor', 'council') else None
        cands = {u: f for u, f in files[(county, office)].items()
                 if town is None or f['scope'] is None or town in f['scope']}
        village = district[len(town):] if office == 'village' and town else ''

        def where(name):
            key = bm.cjk(name)
            hits = {}
            for u, f in cands.items():
                for i, t in enumerate(f['pages']):
                    if len(key) >= 2 and key in t:
                        hits.setdefault(u, i + 1)
            if len(hits) > 1 and village:
                hits = {u: p for u, p in hits.items() if village in cands[u]['label']} or hits
            return hits

        found = {c['name']: where(c['name']) for c in r['candidates']}
        race_urls = {next(iter(h)) for h in found.values() if len(h) == 1}
        for c in r['candidates']:
            h = found[c['name']]
            if len(h) == 1:
                u, p = next(iter(h.items()))
                rows.append([office, county, district, c['name'], f'{u}#page={p}'])
                stats['name'] += 1
                continue
            if len(h) > 1:
                stats['ambiguous'] += 1
                continue
            if len(race_urls) == 1:
                rows.append([office, county, district, c['name'], next(iter(race_urls))])
                stats['race'] += 1
                continue
            labelled = [u for u, f in cands.items() if village and village in f['label']]
            if len(labelled) == 1:
                rows.append([office, county, district, c['name'], labelled[0]])
                stats['label'] += 1
                continue
            if len(cands) == 1:
                rows.append([office, county, district, c['name'], next(iter(cands))])
                stats['only'] += 1
                continue
            stats['none'] += 1
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['office', 'county', 'district', 'name', 'sourceUrl'])
        w.writerows(rows)
    print(f'{len(rows)} 人有公報連結', dict(stats))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
