"""從中選會選舉公告 PDF 擷取議員選舉區範圍與應選名額，寫入 election.json 的議員選區。

用法：python tools/import_districts.py <公告.pdf>

來源：中選會 115/8/20 中選務字第1153150253號公告
https://web.cec.gov.tw/api/file/45d8e965-f63a-46d5-b636-7d81e47cf4d1.pdf
"""

import json
import os
import re
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_cec import COUNTIES, OUT, write_compact  # noqa: E402

clean = lambda s: re.sub(r'\s+', '', (s or '')).replace('巿', '市')


def parse(path):
    blocks, cur = [], None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if len(row) < 5:
                        continue
                    first, district, area, seats, women = (clean(c) for c in row[:5])
                    if district == '第1選舉區':
                        cur = {'label': '', 'districts': []}
                        blocks.append(cur)
                    if cur is None:
                        continue
                    cur['label'] += first
                    if re.fullmatch(r'第\d+選舉區', district) and seats.isdigit():
                        cur['districts'].append(
                            {'district': district, 'area': area, 'seats': int(seats), 'women': int(women or 0)}
                        )
                    elif not district and area and cur['districts']:
                        # 跨頁的儲存格會被切成沒有選舉區欄的一列，接回上一個選舉區
                        cur['districts'][-1]['area'] += area
                    if district == '合計':
                        cur = None
    result = {}
    for b in blocks:
        county = next((c for c in COUNTIES if c in b['label']), None)
        if not county:
            raise ValueError(f'無法辨識縣市：{b["label"]}')
        result[county] = b['districts']
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    districts = parse(sys.argv[1])
    data = json.load(open(OUT, encoding='utf-8'))
    total = matched = 0
    missing = []
    for county, rows in districts.items():
        for d in rows:
            total += 1
            race = next(
                (r for r in data['races'] if r['office'] == 'council' and r['county'] == county and r.get('district') == d['district']),
                None,
            )
            if race is None:
                missing.append(f'{county}{d["district"]}（{d["area"]}）')
                continue
            matched += 1
            race['area'] = d['area'].replace(f'{county}之', '')
            race['seats'] = d['seats']
            if d['women']:
                race['womenSeats'] = d['women']
            if '平地原住民' in d['area']:
                race['indigenous'] = 'plain'
            elif '山地原住民' in d['area']:
                race['indigenous'] = 'mountain'
    write_compact(data, OUT)
    print(f'{len(districts)} 個縣市、{total} 個議員選舉區，對應到 {matched} 個')
    print(f'應選名額合計 {sum(d["seats"] for rows in districts.values() for d in rows)} 名')
    for m in missing:
        print('  沒有登記參選人的選區：' + m)


if __name__ == '__main__':
    main()
