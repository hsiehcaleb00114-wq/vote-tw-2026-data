"""把選委會公告的「候選人登記冊（有號次）」或「候選人名單」PDF 轉成號次 CSV（給 apply_numbers.mjs）。

用法：python tools/number_lists.py <office> <輸出.csv> <PDF> [<PDF> ...]
  office：mayor / council / township / township_rep / village

115 年用到的公告與附件網址列在 tools/ballot_numbers/lottery_1027_sources.tsv（各縣市選委會 10/27 抽籤結果）。
表格要有「選舉區」「姓名」和含「號次」的欄位。選舉區寫法同登記彙總表（縣市＋選區）。
只輸出 election.json 裡找得到的人；找不到的、和既有號次不同的，印出來給人工確認。
"""
import csv
import json
import os
import re
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_cec import COUNTIES, join_cell  # noqa: E402
import bulletin_match as bm  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DIGITS = re.compile(r'^\d{1,2}$')


def rows_of(path):
    with pdfplumber.open(path) as pdf:
        cols = None
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    cells = [join_cell(c) for c in row]
                    if '姓名' in cells and any('號次' in c for c in cells):
                        cols = (cells.index('選舉區') if '選舉區' in cells else 0, cells.index('姓名'),
                                next(i for i, c in enumerate(cells) if '號次' in c))
                        continue
                    if not cols or len(cells) <= max(cols):
                        continue
                    area, name, num = (cells[i] for i in cols)
                    num = num.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
                    if area and name and DIGITS.match(num):
                        yield area, name, int(num)


def main():
    office, out = sys.argv[1], sys.argv[2]
    data = json.load(open(os.path.join(ROOT, 'election.json'), encoding='utf-8'))
    known = {}
    real = {}  # (縣市, 選區) -> 只留漢字的姓名 -> 名冊寫法
    for r in data['races']:
        if r['office'] != office:
            continue
        for c in r['candidates']:
            known[(r['county'], r.get('district') or '', c['name'])] = c.get('number')
            real.setdefault((r['county'], r.get('district') or ''), {})[bm.cjk(c['name'])] = c['name']
    rows, missing, differ = [], [], []
    for path in sys.argv[3:]:
        for area, name, num in rows_of(path):
            county = area[:3]
            if county not in COUNTIES:
                missing.append(f'無法辨識縣市：{area} {name}')
                continue
            district = area[3:]
            # 姓名只比漢字（原住民羅馬拼音寫法常不同）；公告用「○」「●」代替罕用字時，其他字都相同才算
            names = real.get((county, district), {})
            hit = bm.resolve_name(bm.cjk(name).replace('○', '●').replace('〇', '●'), names)
            if hit:
                name = names[hit]
            key = (county, district, name)
            if key not in known:
                missing.append(f'{area} {name} {num}')
                continue
            if known[key] is not None and known[key] != num:
                differ.append(f'{area} {name}：公告 {num}，現有 {known[key]}')
            rows.append([office, county, district if office != 'mayor' else '', name, num])
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['office', 'county', 'district', 'name', 'number'])
        w.writerows(rows)
    same = sum(1 for r in rows if known[(r[1], r[2], r[3])] == r[4])
    print(f'{len(rows)} 人（與現有號次相同 {same}、不同 {len(differ)}）；名冊找不到 {len(missing)}')
    for line in differ + missing:
        print('  ' + line)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
