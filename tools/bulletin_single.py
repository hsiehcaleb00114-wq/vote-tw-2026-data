"""只有一位候選人、但姓名是圖片或號次讀不到位置的村里長選區：用該村里自己的公報檔確認號次是 1。

用法：python tools/bulletin_single.py <快取資料夾> <村里清單.txt> <輸出.csv>

同時符合下列條件才列入：
  - 檔名含鄉鎮名與村里名，而且只有這一個檔
  - 檔案有文字層，號次欄（「號次」表頭下方、同一表頭區塊）裡的數字只有 1
  - 候選人姓名（或去掉姓氏後的名字，罕用字姓氏常是亂碼）出現在檔案文字裡
號次欄是完整 1..n（n > 1）的單一候選人選區會印出來：公報人數可能和登記名冊不符，需要人工確認。
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bulletin_match as bm  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def column_digits(raw):
    cols = bm.number_columns(raw)
    out = []
    for x, y, size, text in (s[:4] for s in raw):
        t = text.strip().rstrip(bm.NUM_PUNCT)
        if not bm.DIGITS.match(t) or size < 12:
            continue
        dcx = x + len(t) * size * 0.3
        for c in cols:
            if c[0] - 15 <= dcx <= c[1] + 15 and c[2] < y < c[2] + 900 and bm.header_of(cols, dcx, y, 15) == c:
                out.append(int(t))
                break
    return out, cols


def main():
    cache, village_list, out = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.load(open(os.path.join(ROOT, 'election.json'), encoding='utf-8'))
    towns_of = bm.load_towns(village_list)
    singles = {
        (r['county'], r['district']): r['candidates'][0]['name']
        for r in data['races']
        if r['office'] == 'village' and len(r['candidates']) == 1 and r['candidates'][0].get('number') is None
    }
    files = {k: [] for k in singles}
    for f in os.listdir(cache):
        doc = json.load(open(os.path.join(cache, f), encoding='utf-8'))
        if bm.office_of(doc['office']) != 'village':
            continue
        county = bm.county_of(doc['county'])
        label = (doc.get('sub') or '') + doc['file']
        for (cty, dist) in singles:
            if cty != county:
                continue
            town = bm.town_of(dist, towns_of[county])
            if not town:
                continue
            village = dist[len(town):]
            if village in label and (town in label or (len(town) >= 3 and town[:-1] in label)):
                files[(cty, dist)].append(doc)
    rows = []
    for (county, dist), docs in sorted(files.items()):
        if len(docs) != 1:
            continue
        doc = docs[0]
        if sum(len(p) for p in doc['pages']) < 20 or bm.garbled(doc['pages']):
            continue
        pages = bm.glyph_digits(doc['pages'])
        nums, ncols = [], 0
        for raw in pages:
            n, cols = column_digits(raw)
            nums += n
            ncols += len(cols)
        name = singles[(county, dist)]
        if nums and set(nums) != {1}:
            if set(nums) == set(range(1, max(nums) + 1)):  # 像是完整的 1..n：公報人數可能和名冊不符
                print(f'公報號次欄有 1～{max(nums)}，名冊只有 1 人：{county} {dist} {name}  {doc["url"]}')
            continue
        if not ncols or not nums:
            continue
        text = ''.join(bm.cjk(s[3]) for p in pages for s in p) + '|' + ''.join(
            bm.cjk(w[3]) for p in pages for w in bm.spaced_words(p) + bm.vertical_words(p))
        key = bm.cjk(name)
        if key in text or (len(key) >= 3 and key[1:] in text):
            rows.append(['village', county, dist, name, 1])
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['office', 'county', 'district', 'name', 'number'])
        w.writerows(rows)
    print(f'{len(rows)} 個選區')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
