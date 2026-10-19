"""把中選會「候選人登記彙總表」PDF 轉成 election.json。

用法：
    pip install pdfplumber
    python tools/import_cec.py <PDF 資料夾> [--updated YYYY-MM-DD] [--source "說明"]

PDF 來源：https://web.cec.gov.tw/central/article/64709（下載各類的「x-1 候選人登記彙總表」）。
檔名需以下列編號開頭：1-1 直轄市長、2-1 直轄市議員、3-1 縣市長、4-1 縣市議員、
5 直轄市山地原住民區長、6 直轄市山地原住民區民代表、7 鄉鎮市長、8 鄉鎮市民代表、9 村里長。

既有 election.json 裡的人工欄位（現任、照片、政見、學經歷等）會依「職位＋縣市＋選區＋姓名」保留下來。
"""

import argparse
import json
import os
import re
import sys
from datetime import date

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'election.json')

# 檔名開頭編號 → 職位
OFFICE_BY_PREFIX = {
    '1-1': 'mayor', '3-1': 'mayor',
    '2-1': 'council', '4-1': 'council',
    '5': 'township', '7': 'township',
    '6': 'township_rep', '8': 'township_rep',
    '9': 'village',
}

COUNTIES = [
    '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
    '基隆市', '新竹市', '新竹縣', '苗栗縣', '彰化縣', '南投縣',
    '雲林縣', '嘉義市', '嘉義縣', '屏東縣', '宜蘭縣', '花蓮縣',
    '臺東縣', '澎湖縣', '金門縣', '連江縣',
]

# 由人工維護、匯入時要保留的欄位
MANUAL_FIELDS = ['number', 'incumbent', 'photo', 'photoCredit', 'photoSourceUrl', 'education', 'experience', 'platform', 'sourceUrl']
# 選區層級、由其他來源補上的欄位（import_districts.py）
RACE_FIELDS = ['area', 'seats', 'womenSeats', 'indigenous']

LATIN = re.compile(r'[A-Za-z]')


def join_cell(cell):
    """合併表格中被換行切開的文字。

    原住民族語拼音被欄寬切斷時，下一段若是 1–3 個小寫字母（如 n、ng、nan），
    是同一個字被切斷的尾巴（不補空格）；大寫開頭或較長的小寫段落是新的字（補空格）。
    名冊中偶有誤植的反引號一併去除。
    """
    parts = [p.strip() for p in (cell or '').split('\n') if p.strip()]
    out = ''
    for p in parts:
        if out and LATIN.match(out[-1]) and LATIN.match(p[0]):
            first_word = re.match(r'[A-Za-z]+', p).group(0)
            if p[0].isupper() or len(first_word) >= 4:
                out += ' '
        out += p
    return out.strip(' `')


def office_for(filename):
    for prefix in sorted(OFFICE_BY_PREFIX, key=len, reverse=True):
        if re.match(re.escape(prefix) + r'(?![\d-])', filename):
            return OFFICE_BY_PREFIX[prefix]
    return None


def read_rows(path):
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 4:
                        continue
                    area, _date, name, party = (join_cell(c) for c in row[:4])
                    note = join_cell(row[4]) if len(row) > 4 else ''
                    if area == '選舉區' or not area:
                        continue
                    yield area, name, party, note


def split_area(area):
    county = area[:3]
    if county not in COUNTIES:
        raise ValueError(f'無法辨識縣市：{area}')
    return county, area[3:] or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf_dir')
    ap.add_argument('--updated', default=date.today().isoformat())
    ap.add_argument('--source', default='中選會「115年地方公職人員選舉候選人登記名冊」')
    args = ap.parse_args()

    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {'races': []}
    keep = {}
    keep_race = {}
    for r in old['races']:
        keep_race[(r['office'], r['county'], r.get('district') or '')] = {k: r[k] for k in RACE_FIELDS if k in r}
        for c in r['candidates']:
            key = (r['office'], r['county'], r.get('district') or '', c['name'])
            keep[key] = {k: c[k] for k in MANUAL_FIELDS if k in c}

    manual = json.load(open(os.path.join(ROOT, 'tools', 'manual_names.json'), encoding='utf-8'))
    manual_note = manual['_note']
    disqualified = json.load(open(os.path.join(ROOT, 'tools', 'disqualified.json'), encoding='utf-8'))
    excluded = []

    races = {}
    notes = []
    counts = {}
    for f in sorted(os.listdir(args.pdf_dir)):
        if not f.lower().endswith('.pdf'):
            continue
        office = office_for(f)
        if not office:
            print(f'略過無法對應職位的檔案：{f}', file=sys.stderr)
            continue
        n = 0
        for area, name, party, note in read_rows(os.path.join(args.pdf_dir, f)):
            flag = None
            if not name:
                # 罕用字姓名在 PDF 中是圖片，改用人工轉錄
                if area not in manual:
                    print(f'✗ {f} {area} 姓名讀不到，也不在 manual_names.json', file=sys.stderr)
                    continue
                name, flag = manual[area], manual_note
            # 村里名含罕用字、PDF 只剩鄉鎮名的，依對照表補正
            area = manual['_areas'].get(f'{area}|{name}', area)
            if disqualified.get(office, {}).get(area) == name:
                excluded.append(f'{area} {name}')
                continue
            county, district = split_area(area)
            key = (office, county, district or '')
            race = races.setdefault(
                key,
                {'office': office, 'county': county, **({'district': district} if district else {}), **keep_race.get(key, {}), 'candidates': []},
            )
            c = {'name': name, 'party': '無黨籍' if party in ('', '無') else party}
            c.update(keep.get((*key, name), {}))
            if flag:
                c['unverified'] = flag
            if note:
                notes.append(f'{f} {area} {name}：{note}')
            race['candidates'].append(c)
            n += 1
        counts[f] = n

    order = {c: i for i, c in enumerate(COUNTIES)}
    office_order = ['mayor', 'council', 'township', 'township_rep', 'village']
    sorted_races = sorted(
        races.values(),
        key=lambda r: (office_order.index(r['office']), order[r['county']], r.get('district') or ''),
    )
    data = {'version': 1, 'updated': args.updated, 'source': args.source, 'races': sorted_races}
    write_compact(data, OUT)

    for f, n in counts.items():
        print(f'{f}: {n} 人')
    print(f'合計 {sum(counts.values())} 人、{len(sorted_races)} 個選區（排除審定不合格 {len(excluded)} 人）')
    expected = sum(len(v) for k, v in disqualified.items() if not k.startswith('_'))
    if len(excluded) != expected:
        print(f'✗ disqualified.json 有 {expected} 人，但只排除了 {len(excluded)} 人，請檢查姓名或選區寫法', file=sys.stderr)
    if notes:
        print('備註欄有內容（請人工確認）：')
        for line in notes:
            print('  ' + line)


def write_compact(data, path):
    """每位參選人一行，方便人工閱讀與在 GitHub 上看差異，也比完整縮排小很多。"""
    dump = lambda v: json.dumps(v, ensure_ascii=False)
    lines = ['{']
    lines.append(f'  "version": {dump(data["version"])},')
    lines.append(f'  "updated": {dump(data["updated"])},')
    lines.append(f'  "source": {dump(data["source"])},')
    lines.append('  "races": [')
    for i, r in enumerate(data['races']):
        head = {k: v for k, v in r.items() if k != 'candidates'}
        lines.append('    ' + dump(head)[:-1] + ', "candidates": [')
        for j, c in enumerate(r['candidates']):
            lines.append('      ' + dump(c) + (',' if j < len(r['candidates']) - 1 else ''))
        lines.append('    ]}' + (',' if i < len(data['races']) - 1 else ''))
    lines.append('  ]')
    lines.append('}')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    main()
