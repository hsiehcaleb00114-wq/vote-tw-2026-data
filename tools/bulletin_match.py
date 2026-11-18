"""比對選舉公報快取與 election.json：找出每位參選人的號次，以及公報裡找不到的參選人。

用法：python tools/bulletin_match.py <快取資料夾> <輸出資料夾> <村里清單.txt>
  快取資料夾：bulletin_extract.py 的輸出
  村里清單：內政部國土測繪中心村里界圖匯出檔，每行「縣市|鄉鎮市區|村里|備註」，
            用來判斷每個公報檔涵蓋哪些鄉鎮
輸出：
  numbers.csv   可交給 apply_numbers.mjs 的號次（號次在選區內不重複才列入）
  report.txt    找不到姓名、無法自動核對、號次衝突等需要人工確認的項目

部分公報是掃描圖片、沒有文字；這些檔案涵蓋的參選人列為「無法自動核對」，不算找不到。
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

OFFICE_OF_FOLDER = [
    ('原住民區民代表', 'township_rep'),
    ('區民代表', 'township_rep'),
    ('鄉鎮市民代表', 'township_rep'),
    ('原住民區長', 'township'),
    ('鄉鎮市長', 'township'),
    ('區長', 'township'),
    ('議員', 'council'),
    ('村里長', 'village'),
    ('里長', 'village'),
    ('縣長', 'mayor'),
    ('市長', 'mayor'),
]
DIGITS = re.compile(r'^\d{1,2}$')
NUM_PUNCT = '·.、．:：'  # 號次後面接的標點，如「1·」
SPACE = re.compile(r'[\s\x00-\x1f]+')  # 部分公報在字與字之間夾控制字元
CJK_CHAR = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\u2e80-\u2fdf]')

# 公報與登記名冊常見的異體字寫法不同，比對前統一
VARIANTS = str.maketrans({
    '眞': '真', '峯': '峰', '勲': '勳', '啓': '啟', '温': '溫', '敎': '教', '淸': '清', '靑': '青',
    '鷄': '雞', '寛': '寬', '黄': '黃', '呉': '吳', '徳': '德', '恵': '惠', '琍': '莉', '晧': '皓',
    '册': '冊', '强': '強', '舘': '館', '綫': '線', '湧': '涌', '麪': '麵', '玆': '茲', '飮': '飲',
    '臺': '台', '羣': '群', '粧': '妝', '銹': '鏽', '濓': '濂',
    # NFKC 不會轉換的 CJK 部首補充字元，部分公報用來代替整個漢字
    '⺠': '民', '⻑': '長', '⻄': '西', '⺝': '月', '⻘': '青', '⻝': '食', '⻁': '虎', '⺯': '糸',
})
LATIN = re.compile(r"[A-Za-z'’\-‧．·・•.\s]+")


def office_of(folder):
    name = re.sub(r'^\d+', '', folder)
    for key, office in OFFICE_OF_FOLDER:
        if name.endswith(key):
            return office
    return None


def county_of(folder):
    return re.sub(r'^\d+', '', folder).replace('台', '臺')


def norm(s):
    # NFKC：部分公報用康熙部首字（如「⽂」）代替一般漢字
    return SPACE.sub('', unicodedata.normalize('NFKC', s)).translate(VARIANTS)


def cjk(s):
    """只留漢字部分：原住民姓名的羅馬拼音在公報裡寫法常不同。
    括號字（如「㈮」）經 NFKC 會變成「(金)」，括號一併去掉"""
    return LATIN.sub('', norm(s)).replace('(', '').replace(')', '')


def resolve_name(key, names):
    """公報用「●」代替罕用字：其他字都相同、字數相同、而且只有一人符合時才算"""
    if key in names:
        return key
    if '●' not in key or len(key) < 2 or key.count('●') > 1:
        return None
    hits = [n for n in names if len(n) == len(key) and all(a == b or a == '●' for a, b in zip(key, n))]
    return hits[0] if len(hits) == 1 else None


def merge_lines(page):
    """同一列、緊鄰的片段合併：罕用字或異體字常用別的字型，會被拆成獨立片段"""
    # 先依高度分列（相差 4 點以內算同一列），列內再依水平位置排序
    lines = []
    for s in sorted(page, key=lambda s: s[1]):
        if lines and abs(lines[-1][-1][1] - s[1]) <= 4:
            lines[-1].append(s)
        else:
            lines.append([s])
    spans = [s for line in lines for s in sorted(line, key=lambda s: s[0])]
    merged = []
    for s in spans:
        if merged:
            p = merged[-1]
            same_line = abs(p[1] - s[1]) <= 4 and abs(p[2] - s[2]) <= 3
            gap = s[0] - (p[0] + p[4] * p[2])
            if same_line and -p[2] < gap < p[2] * 0.9:
                p[3] += s[3]
                p[4] += len(s[3])
                continue
        merged.append([s[0], s[1], s[2], s[3], len(s[3])])
    return [m[:4] for m in merged]


def garbled(pages):
    """文字層是亂碼（字型沒有對應表、或內嵌的劣質 OCR）：漢字比例太低，當掃描檔處理"""
    text = ''.join(s[3] for p in pages for s in p)
    text = SPACE.sub('', text)
    return len(text) > 0 and len(CJK_CHAR.findall(text)) < 0.5 * len(text)


def glyph_digits(pages):
    """部分公報（如雲林縣口湖鄉）的號次用自訂字型，U+0200 起依序代表 1、2、3…。
    檔案裡單獨成片段的這類字元若剛好是從 U+0200 起連續的一段，就換成阿拉伯數字"""
    lone = {s[3].strip() for p in pages for s in p if len(s[3].strip()) == 1 and 0x200 <= ord(s[3].strip()) < 0x264}
    codes = sorted(ord(c) for c in lone)
    if not codes or codes != list(range(0x200, 0x200 + len(codes))):
        return pages
    fix = lambda s: s[:3] + [str(ord(s[3].strip()) - 0x1FF)] + s[4:] if s[3].strip() in lone else s
    return [[fix(s) for s in p] for p in pages]


def spaced_words(raw):
    """字距拉開的橫排姓名：同一列、同字級、間距一致的單字片段連成一個詞，回傳 [x, y, size, text, None, 右緣]"""
    singles = [s for s in raw if len(norm(s[3])) == 1 and CJK_CHAR.match(norm(s[3]))]
    singles.sort(key=lambda s: (round(s[1]), s[0]))
    out, run = [], []
    def flush():
        if 2 <= len(run) <= 4:
            out.append([run[0][0], run[0][1], run[0][2], ''.join(r[3] for r in run), None, run[-1][0] + run[-1][2]])
    for s in singles:
        if run:
            p = run[-1]
            gap = s[0] - p[0]
            same = abs(p[1] - s[1]) <= 1 and abs(p[2] - s[2]) <= 0.5 and p[2] < gap <= 4 * p[2]
            if same and (len(run) < 2 or abs(gap - (run[1][0] - run[0][0])) <= 0.15 * gap):
                run.append(s)
                continue
            flush()
        run = [s]
    if run:
        flush()
    return out


def vertical_words(raw):
    """直排姓名：同一 x、同字級的單字片段，上下間距不大的連成一個詞，回傳 [x, y0, size, text, y1]"""
    singles = [s for s in raw if len(norm(s[3])) == 1 and CJK_CHAR.match(norm(s[3]))]
    singles.sort(key=lambda s: (round(s[0]), s[1]))
    out, cur = [], None
    for s in singles:
        if cur and abs(cur[0] - s[0]) <= 2 and abs(cur[2] - s[2]) <= 1 and 0 < s[1] - cur[4] < 2.6 * s[2] - s[2]:
            cur[3] += s[3]
            cur[4] = s[1] + s[2]
            continue
        if cur and len(cur[3]) >= 2:
            out.append(cur)
        cur = [s[0], s[1], s[2], s[3], s[1] + s[2]]
    if cur and len(cur[3]) >= 2:
        out.append(cur)
    return out


def number_columns(raw):
    """「號次」表頭：(左, 右, 上緣)。「號次、姓名」合併表頭取整個表頭寬"""
    cols = []
    for x, y, size, text in (s[:4] for s in raw):
        t = SPACE.sub('', text)
        i = t.find('號次')
        if i >= 0:
            if '姓名' in t:  # 號次常印在合併表頭的左緣外
                cols.append((x - 2 * size, x + len(t) * size, y))
            else:
                cols.append((x + i * size, x + (i + 2) * size, y))
        elif t == '號':
            cols.append((x, x + size, y))
    return cols


def header_of(cols, x, y, reach):
    """某位置所屬的表頭：在它上方（容許 10 點）、左緣不超過 reach 的表頭中，
    垂直距離加水平距離最近的那個（並排的區塊表頭高度不一定對齊）"""
    best, best_d = None, 1e9
    for c in cols:
        if c[2] > y + 10 or c[0] > x + reach:
            continue
        d = (y - c[2]) + abs(x - c[0])
        if d < best_d:
            best, best_d = c, d
    return best


def find_number_in_column(raw, cols, box):
    """號次欄裡、和姓名屬於同一個表頭區塊、而且同一列的數字。box = (x0, y0, x1, y1, 字級)"""
    x0, y0, x1, y1, ns = box
    head = header_of(cols, x0, y0, 2 * ns)
    if head is None:
        return None
    cy = (y0 + y1) / 2
    best, best_score = None, 1e9
    for x, y, size, text in (s[:4] for s in raw):
        t = text.strip().rstrip(NUM_PUNCT)
        if t in ('I', 'l', '|') and size >= 30:  # 內嵌 OCR 文字層把大字「1」讀成 I
            t = '1'
        if not DIGITS.match(t) or size < 12:
            continue
        dcx = x + len(t) * size * 0.3
        if not (head[0] - 15 <= dcx <= head[1] + 15):
            continue
        if header_of(cols, dcx, y, 15) != head:
            continue
        dcy = y + size / 2
        if not (y0 - 4 * ns - size <= dcy <= y1 + 3 * ns):
            continue
        score = abs(dcy - cy) + 0.3 * abs(dcx - (x0 + x1) / 2)
        if score < best_score:
            best, best_score = int(t), score
    return best


def find_number(page, name_span):
    """名字附近最可能的號次：上方或同列、水平距離不遠的 1～2 位數字"""
    nx, ny, _, _ = name_span
    best, best_score = None, 1e9
    for x, y, size, text in page:
        if not DIGITS.match(text) or size < 10:
            continue
        dy = ny - y
        dx = abs(x - nx)
        if dy < -8 or dy > 140 or dx > 160:
            continue
        score = max(dy, 0) + 0.6 * dx - size
        if score < best_score:
            best, best_score = int(text), score
    return best


def load_towns(path):
    towns = defaultdict(set)
    for line in open(path, encoding='utf-8'):
        parts = [p.strip() for p in line.rstrip('\n').split('|')]
        if len(parts) >= 3 and not (len(parts) > 3 and parts[3]):
            towns[parts[0].replace('台', '臺')].add(parts[1])
    return towns


def town_of(district, towns):
    best = ''
    for t in towns:
        if district.startswith(t) and len(t) > len(best):
            best = t
    return best or None


def file_scope(doc, towns):
    """公報檔涵蓋的鄉鎮（依資料夾與檔名判斷）；判斷不出來時回傳 None，代表可能涵蓋全縣市"""
    label = (doc.get('sub') or '') + doc['file']
    hit = {t for t in towns if t in label or (len(t) >= 3 and t[:-1] in label)}
    return hit or None


def main():
    cache, out_dir, village_list = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    data = json.load(open(os.path.join(ROOT, 'election.json'), encoding='utf-8'))
    towns_of = load_towns(village_list)

    # 參選人索引：(縣市, 職位) -> 名字 -> [選區鍵]
    pool = defaultdict(lambda: defaultdict(list))
    race_of = {}
    for r in data['races']:
        rk = (r['office'], r['county'], r.get('district') or '')
        race_of[rk] = r
        for c in r['candidates']:
            pool[(r['county'], r['office'])][cjk(c['name'])].append(rk)

    image_scopes = defaultdict(list)  # (縣市, 職位) -> 掃描圖片檔涵蓋的鄉鎮（None 為全縣市）
    found_numbers = defaultdict(lambda: defaultdict(set))  # rk -> 名字 -> {號次}
    seen_text = defaultdict(list)  # (縣市, 職位) -> 公報文字
    files = 0
    garbled_files = []
    for f in os.listdir(cache):
        if not f.endswith('.json'):
            continue
        doc = json.load(open(os.path.join(cache, f), encoding='utf-8'))
        office = office_of(doc['office'])
        county = county_of(doc['county'])
        if not office:
            continue
        files += 1
        names = pool[(county, office)]
        scope = file_scope(doc, towns_of[county])
        if sum(len(p) for p in doc['pages']) < 20 or garbled(doc['pages']):
            image_scopes[(county, office)].append(scope)
            if sum(len(p) for p in doc['pages']) >= 20:
                garbled_files.append(doc)
            continue
        for raw in glyph_digits(doc['pages']):
            page = merge_lines(raw)
            cols = number_columns(raw)
            verticals = vertical_words(raw) if cols else []
            verticals += spaced_words(raw)
            seen_text[(county, office)].append(''.join(cjk(s[3]) for s in page))
            seen_text[(county, office)].append(''.join(cjk(s[3]) for s in raw))
            for span in page + verticals:
                key = resolve_name(cjk(span[3]), names)
                if key is None:
                    continue
                rks = names[key]
                if len(rks) > 1 and scope:
                    rks = [rk for rk in rks if town_of(rk[2], scope)] or rks
                if len(rks) != 1:
                    continue  # 同縣市同職位同名，無法單靠姓名判斷
                if len(span) == 5:  # 直排
                    box = (span[0], span[1], span[0] + span[2], span[4], span[2])
                elif len(span) == 6:  # 字距拉開的橫排
                    box = (span[0], span[1], span[5], span[1] + span[2], span[2])
                else:
                    box = (span[0], span[1], span[0] + span[2] * len(key), span[1] + span[2], span[2])
                n = find_number_in_column(raw, cols, box) if cols else None
                if n is None and len(span) != 5:
                    n = find_number(page, span[:4])
                if n is not None:
                    found_numbers[rks[0]][key].add(n)

    def checkable(county, office, district):
        town = town_of(district, towns_of[county]) if office not in ('mayor', 'council') else None
        for scope in image_scopes.get((county, office), []):
            if scope is None or town is None or town in scope:
                return False
        return True

    absent, unverifiable = [], []
    for (county, office), names in pool.items():
        text = '|'.join(seen_text.get((county, office), []))
        for key, rks in names.items():
            if not key or key in text:
                continue
            for rk in rks:
                line = f'{rk[1]} {rk[2]} {key}（{office}）'
                (absent if text and checkable(county, office, rk[2]) else unverifiable).append(line)

    rows, conflict, bad_race = [], [], []
    complete = partial = 0
    for rk, r in race_of.items():
        nums = {}
        ok = True
        for c in r['candidates']:
            got = found_numbers.get(rk, {}).get(cjk(c['name']), set())
            if len(got) == 1:
                nums[c['name']] = next(iter(got))
            elif len(got) > 1:
                conflict.append(f'{rk[1]} {rk[2]} {c["name"]}：{sorted(got)}')
                ok = False
            else:
                ok = False
        values = list(nums.values())
        if len(values) != len(set(values)):
            bad_race.append(f'{rk[1]} {rk[2]}（{rk[0]}）號次重複：{nums}')
            continue
        if ok and nums:
            complete += 1
        elif nums:
            partial += 1
        for name, n in nums.items():
            rows.append([rk[0], rk[1], rk[2] if rk[0] != 'mayor' else '', name, n])

    with open(os.path.join(out_dir, 'numbers.csv'), 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(['office', 'county', 'district', 'name', 'number'])
        w.writerows(sorted(rows))
    images = sum(len(v) for v in image_scopes.values())
    with open(os.path.join(out_dir, 'garbled.tsv'), 'w', encoding='utf-8') as fh:
        for d in garbled_files:
            fh.write('\t'.join([d['url'], d['county'], d['office'], d.get('sub') or '', d['file'], str(len(d['pages']))]) + '\n')
    summary = (
        f'公報 {files} 檔（掃描圖片 {images}）；號次全部找到的選區 {complete}、部分 {partial}、共 {len(rows)} 人；'
        f'找不到 {len(absent)}、無法核對 {len(unverifiable)}、衝突 {len(conflict)}、重複 {len(bad_race)}'
    )
    with open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8') as fh:
        fh.write(summary + '\n\n')
        fh.write(f'## 公報裡找不到姓名（{len(absent)}）\n' + '\n'.join(sorted(absent)) + '\n\n')
        fh.write(f'## 公報是掃描圖片，無法自動核對（{len(unverifiable)}）\n' + '\n'.join(sorted(unverifiable)) + '\n\n')
        fh.write(f'## 同一人找到多個號次（{len(conflict)}）\n' + '\n'.join(conflict) + '\n\n')
        fh.write(f'## 同選區號次重複（{len(bad_race)}）\n' + '\n'.join(bad_race) + '\n')
    print(summary)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
