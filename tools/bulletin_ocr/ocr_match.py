"""把掃描公報的 OCR 結果對到 election.json 的候選人，輸出號次 CSV。

來源：
  results.json   直排版型：每格 OCR 文字＝號次＋姓名（compose.py）
  results_b.json 橫排版型：整頁 OCR 找到的姓名＋上方／左方號次字（anchor.py）

規則：
  - 直排格子的姓名要和候選人完全相同；若同一檔案已有其他格子完全對中某選區，
    該檔其餘格子可在「同一選區」內容許差一個字（OCR 漏字或錯字），且只能對中唯一一人
  - 橫排：上方找不到號次才用左方
  - 選區每位候選人都讀到、每人只讀到一個號次、號次恰為 1..n 才輸出
用法：python ocr_match.py <villages.txt> <out.csv> <results.json> [<results_b.json> ...]
"""
import csv
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, 'C:/VoteTW/vote-tw-2026-data/tools')
import bulletin_match as bm  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
ROOT = 'C:/VoteTW/vote-tw-2026-data'
CELL = re.compile(r'^[^\d\u3400-\u9fff]{0,2}(\d{1,2})(?!\d)(.*)$')


def parse(words):
    text = ''.join(words)
    m = CELL.match(text)
    if not m:
        return None, bm.cjk(text)
    return int(m.group(1)), bm.cjk(m.group(2))


def close(a, b):
    """編輯距離不超過 1"""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))


def main():
    villages, out_csv = sys.argv[1:3]
    res_a = sys.argv[3]
    res_bs = sys.argv[4:]
    data = json.load(open(f'{ROOT}/election.json', encoding='utf-8'))
    towns_of = bm.load_towns(villages)
    pool = defaultdict(lambda: defaultdict(list))
    race_of = {}
    for r in data['races']:
        rk = (r['office'], r['county'], r.get('district') or '')
        race_of[rk] = r
        for c in r['candidates']:
            pool[(r['county'], r['office'])][bm.cjk(c['name'])].append(rk)

    found = defaultdict(lambda: defaultdict(set))  # rk -> 名字 -> {號次}
    how = defaultdict(lambda: defaultdict(set))
    stats = defaultdict(int)

    # 直排格子
    by_url = defaultdict(list)
    for cell in json.load(open(res_a, encoding='utf-8')):
        n, name = parse(cell['words'])
        stats['cells'] += 1
        if n is None or not name:
            stats['unparsed'] += 1
            continue
        office = bm.office_of(cell['office'])
        county = bm.county_of(cell['county'])
        scope = bm.file_scope(cell, towns_of[county])
        clean = bool(re.fullmatch(r'\d{1,2}[㐀-鿿]{2,}', ''.join(cell['words'])))
        by_url[cell['url']].append((county, office, scope, n, name, clean))
    for url, cells in by_url.items():
        races_here = set()
        pending = []
        for county, office, scope, n, name, clean in cells:
            rks = pool[(county, office)].get(name, [])
            if len(rks) > 1 and scope:
                rks = [rk for rk in rks if bm.town_of(rk[2], scope)]
            if len(rks) == 1:
                found[rks[0]][name].add(n)
                how[rks[0]][name].add('exact')
                races_here.add(rks[0])
                stats['exact'] += 1
            elif clean:
                pending.append((n, name))  # 只有乾淨的格子（號次後面全是漢字）才容許差一字
        for n, name in pending:
            cands = [(rk, bm.cjk(c['name'])) for rk in races_here for c in race_of[rk]['candidates']
                     if close(name, bm.cjk(c['name']))]
            if len(cands) == 1:
                rk, real = cands[0]
                found[rk][real].add(n)
                how[rk][real].add('fuzzy')
                stats['fuzzy'] += 1
            else:
                stats['nomatch'] += 1

    # 橫排姓名＋號次字
    per = defaultdict(dict)  # (page, rk, name, box) -> how -> number
    for res_b in res_bs:
        for a in json.load(open(res_b, encoding='utf-8')):
            per[(a['page'], tuple(a['rk']), a['name'], tuple(a['box']))][a['how']] = a.get('number')
    for (page, rk, name, box), d in per.items():
        n = d.get('above')
        if n is None:
            n = d.get('left')
        if n is None:
            stats['b_nonumber'] += 1
            continue
        found[rk][name].add(n)
        how[rk][name].add('anchor')
        stats['b_number'] += 1

    rows, partial, bad = [], [], []
    for rk, names in found.items():
        cs = race_of[rk]['candidates']
        got = {c['name']: names.get(bm.cjk(c['name']), set()) for c in cs}
        if any(len(v) > 1 for v in got.values()):
            bad.append((rk, 'conflict', {k: sorted(v) for k, v in got.items()}))
            continue
        if any(not v for v in got.values()):
            partial.append((rk, {k: sorted(v) for k, v in got.items()}))
            continue
        nums = {k: next(iter(v)) for k, v in got.items()}
        if sorted(nums.values()) != list(range(1, len(cs) + 1)):
            bad.append((rk, 'not1n', nums))
            continue
        for name, num in nums.items():
            rows.append([rk[0], rk[1], rk[2] if rk[0] != 'mayor' else '', name, num])
    with open(out_csv, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['office', 'county', 'district', 'name', 'number'])
        w.writerows(sorted(rows))
    print(dict(stats))
    print('races ok', len({tuple(r[:3]) for r in rows}), 'cands', len(rows), 'partial', len(partial), 'bad', len(bad))
    with open(out_csv + '.report.txt', 'w', encoding='utf-8') as fh:
        for x in bad:
            fh.write(f'bad {x}\n')
        for x in partial:
            fh.write(f'partial {x}\n')


if __name__ == '__main__':
    main()
