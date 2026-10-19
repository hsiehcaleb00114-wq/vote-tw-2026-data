"""把中選會「選舉資料庫」批次檔轉成 App 用的歷屆選舉 JSON。

用法：python tools/import_history.py <votedata.zip>

資料來源：中選會選舉資料庫 https://db.cec.gov.tw/
批次下載：https://data.cec.gov.tw/選舉資料庫/votedata.zip（政府資料開放授權條款第 1 版）
格式說明：壓縮檔內 voteData/選舉資料庫格式.odt

輸出（history/）：
  index.json                 歷屆選舉清單
  <id>.json                  各屆結果：總統／縣市長（含各縣市）、議員與立委政黨席次
  trends.json                政黨席次與得票趨勢
  villages/<縣市>.json       各村里歷屆投票（我的地區）
  referendums.json           公投結果
"""

import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'history')
VD = 'votedata/votedata/voteData/'
SOURCE = '中選會選舉資料庫'

# 每屆選舉要轉換的資料夾（相對 voteData/）
ELECTIONS = [
    {
        'id': '2024', 'title': '2024 總統副總統及立法委員選舉', 'date': '2024-01-13', 'kind': 'national',
        'president': ['2024總統立委/總統'],
        'legislator': ['2024總統立委/區域立委', '2024總統立委/平地立委', '2024總統立委/山地立委'],
        'partylist': '2024總統立委/不分區政黨',
    },
    {
        'id': '2022', 'title': '2022 地方公職人員選舉', 'date': '2022-11-26', 'kind': 'local',
        'mayor': ['2022-111年地方公職人員選舉/C1/city', '2022-111年地方公職人員選舉/C1/prv'],
        # 嘉義市長因候選人過世延至 2022/12/18 重行選舉，資料另放一個資料夾、格式不同
        'rerun': 'votedata/votedata/2022年_嘉義市長重行選舉/',
        'council': [f'2022-111年地方公職人員選舉/{t}/{p}' for t in ('T1', 'T2', 'T3') for p in ('city', 'prv')],
    },
    {
        'id': '2020', 'title': '2020 總統副總統及立法委員選舉', 'date': '2020-01-11', 'kind': 'national',
        'president': ['2020總統立委/總統'],
        'legislator': ['2020總統立委/區域立委', '2020總統立委/平地立委', '2020總統立委/山地立委'],
        'partylist': '2020總統立委/不分區政黨',
    },
    {
        'id': '2018', 'title': '2018 地方公職人員選舉', 'date': '2018-11-24', 'kind': 'local',
        'mayor': ['2018-107年地方公職人員選舉/直轄市市長', '2018-107年地方公職人員選舉/縣市市長'],
        'council': [
            f'2018-107年地方公職人員選舉/{x}'
            for x in ('直轄市區域議員', '直轄市平原議員', '直轄市山原議員', '縣市區域議員', '縣市平原議員', '縣市山原議員')
        ],
    },
    {
        'id': '2016', 'title': '2016 總統副總統及立法委員選舉', 'date': '2016-01-16', 'kind': 'national',
        'president': ['2016總統立委/總統'],
        'legislator': ['2016總統立委/區域立委', '2016總統立委/平地立委', '2016總統立委/山地立委'],
        'partylist': '2016總統立委/不分區政黨',
    },
    {
        'id': '2014', 'title': '2014 地方公職人員選舉', 'date': '2014-11-29', 'kind': 'local',
        'mayor': ['2014-103年地方公職人員選舉/直轄市市長', '2014-103年地方公職人員選舉/縣市市長'],
        'council': [
            f'2014-103年地方公職人員選舉/{x}'
            for x in ('直轄市區域議員', '直轄市平原議員', '直轄市山原議員', '縣市區域議員', '縣市平原議員', '縣市山原議員')
        ],
    },
    {
        'id': '2012', 'title': '2012 總統副總統及立法委員選舉', 'date': '2012-01-14', 'kind': 'national',
        'president': ['20120114-總統及立委/總統'],
        'legislator': [f'20120114-總統及立委/{x}' for x in ('區域立委', '平地立委', '山地立委')],
        'partylist': '20120114-總統及立委/不分區政黨',
    },
    {
        'id': '2009-10', 'label': '2009–10', 'title': '2009 縣市長及 2010 五都選舉', 'date': '2009-12-05', 'kind': 'local',
        'note': '2009/12/5 縣市長與縣市議員、2010/11/27 五都市長與議員',
        'mayor': ['20091205-縣市長縣市議員及鄉鎮長/縣市長', '20101127-五都市長議員及里長/市長'],
        'council': [
            f'{d}/{x}'
            for d in ('20091205-縣市長縣市議員及鄉鎮長', '20101127-五都市長議員及里長')
            for x in ('區域議員', '平地議員', '山地議員')
        ],
    },
    {
        'id': '2008', 'title': '2008 立法委員及總統選舉', 'date': '2008-01-12', 'kind': 'national',
        'note': '2008/1/12 立法委員（首次單一選區兩票制）、2008/3/22 總統',
        'president': ['20080322-總統'],
        'legislator': ['2008立委/區域', '2008立委/平原', '2008立委/山原'],
        'partylist': '2008立委/不分區政黨',
    },
    {
        'id': '2005-06', 'label': '2005–06', 'title': '2005 縣市長及 2006 北高市長選舉', 'date': '2005-12-03', 'kind': 'local',
        'note': '2005/12/3 縣市長與縣市議員、2006/12/9 臺北市與高雄市市長與議員',
        'mayor': ['2005縣市長', '2006直轄市長'],
        'council': ['2005縣市議員/區域', '2005縣市議員/平原', '2005縣市議員/山原', '2006直轄市議員(區域)', '2006直轄市議員(原住民)'],
    },
    {
        'id': '2004', 'title': '2004 總統副總統選舉', 'date': '2004-03-20', 'kind': 'national',
        'president': ['2004   11任總統'],
    },
    {
        'id': '2001-02', 'label': '2001–02', 'title': '2001 縣市長及 2002 北高市長選舉', 'date': '2001-12-01', 'kind': 'local',
        'note': '2001/12/1 縣市長、2002/12/7 縣市議員與臺北市、高雄市市長與議員',
        'mayor': ['2001縣市長', '2002直轄市長'],
        'council': ['2002縣市議員/區域', '2002縣市議員/平原', '2002縣市議員/山原', '2002直轄市議員(區域)', '2002直轄市議員(原住民)'],
    },
    {
        'id': '2000', 'title': '2000 總統副總統選舉', 'date': '2000-03-18', 'kind': 'national',
        'president': ['2000年10任總統'],
    },
    {
        'id': '1997-98', 'label': '1997–98', 'title': '1997 縣市長及 1998 北高市長選舉', 'date': '1997-11-29', 'kind': 'local',
        'note': '1997/11/29 縣市長、1998 縣市議員與臺北市、高雄市市長與議員',
        'mayor': ['1997縣市長', '1998直轄市長'],
        'council': ['1998縣市議員/區域', '1998縣市議員/平原', '1998縣市議員/山原', '1998直轄市議員/區域', '1998直轄市議員/原住民'],
    },
    {
        'id': '1996', 'title': '1996 總統副總統選舉', 'date': '1996-03-23', 'kind': 'national',
        'note': '第一次總統直選',
        'president': ['9任總統'],
    },
]

COUNTY_ORDER = [
    '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
    '基隆市', '新竹市', '新竹縣', '苗栗縣', '彰化縣', '南投縣',
    '雲林縣', '嘉義市', '嘉義縣', '屏東縣', '宜蘭縣', '花蓮縣',
    '臺東縣', '澎湖縣', '金門縣', '連江縣',
]
# 2010 年前已改制或合併的縣市，排在現行縣市之後
LEGACY_COUNTIES = ['臺北縣', '桃園縣', '臺中縣', '臺南縣', '高雄縣']
INDEPENDENT = '無黨籍'


def is_county(name):
    name = name.replace('台', '臺')
    return name in COUNTY_ORDER or name in LEGACY_COUNTIES or (name.endswith(('縣', '市')) and '省' not in name)


class Archive:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        # 檔名是 Big5 但沒有 UTF-8 旗標，zipfile 會當成 cp437 解讀
        # 部分檔案（如 2016）有 UTF-8 旗標，名稱已正確解讀，不能再轉換
        self.names = {}
        for info in self.z.infolist():
            n = info.filename
            if info.flag_bits & 0x800:
                self.names[n] = n
                continue
            try:
                self.names[n.encode('cp437').decode('cp950')] = n
            except (UnicodeEncodeError, UnicodeDecodeError):
                self.names[n] = n

    def rows(self, path):
        raw = self.z.read(self.names[path])
        text = raw.decode('utf-8-sig')
        for row in csv.reader(io.StringIO(text)):
            # 2018 年的代碼前面多一個單引號，例如 '10
            yield [c.strip().lstrip("'").strip() for c in row]

    def has(self, path):
        return path in self.names

    def find(self, folder, stem):
        """資料夾內的 stem.csv；2016 年的檔名帶後綴（如 elbase_T1.csv）"""
        if folder + stem + '.csv' in self.names:
            return folder + stem + '.csv'
        for n in self.names:
            if n.startswith(folder + stem + '_') and n.endswith('.csv') and '/' not in n[len(folder):]:
                return n
        return None


class Dataset:
    """一個資料夾（elbase / elcand / elctks / elpaty / elprof）"""

    def __init__(self, ar, folder):
        p = VD + folder + '/'
        f = lambda stem: ar.find(p, stem)
        self.party = {r[0]: r[1] for r in ar.rows(f('elpaty')) if r}
        self.base = {tuple(r[:5]): r[5] for r in ar.rows(f('elbase')) if len(r) >= 6}
        self.cands = [r for r in ar.rows(f('elcand')) if len(r) >= 15]
        # 只取彙總層級（投開票所 = 0）的得票
        self.tks = [r for r in ar.rows(f('elctks')) if len(r) >= 9 and int(r[5] or 0) == 0]
        self.prof = [r for r in ar.rows(f('elprof')) if len(r) >= 10 and int(r[5] or 0) == 0]
        self.retks = [r for r in ar.rows(f('elretks')) if len(r) >= 5] if f('elretks') else []

        # 總統、立委資料的得票檔在村里列帶有選區代碼，但行政區檔沒有，查名稱時忽略選區
        self.village = {(k[0], k[1], k[3], k[4]): name for k, name in self.base.items() if k[4] != '0000'}
        self.county = {}
        self.town = {}
        for k, name in self.base.items():
            prv, city, area, dept, li = k
            if prv == '00' or li != '0000':
                continue
            if dept == '000' and area == '00' and is_county(name):
                self.county[(prv, city)] = name.replace('台', '臺')
            elif dept != '000':
                self.town[(prv, city, dept)] = name

    def party_name(self, code):
        name = self.party.get(code, '')
        # 早年資料的無黨籍寫作「無」、總統選舉的連署參選人寫作「連署」
        if code == '999' or not name or '無黨' in name or '未經政黨推薦' in name or name in ('無', '連署'):
            return INDEPENDENT
        return name

    def county_of(self, key):
        return self.county.get((key[0], key[1]), '')


def pct(n, d):
    return round(n * 100 / d, 2) if d else 0.0


def candidates_of(ds):
    """依選區整理候選人（副手併入同號次）"""
    races = defaultdict(dict)
    for r in ds.cands:
        prv, city, area, dept, li = r[:5]
        no, name, party = r[5], r[6], r[7]
        deputy = len(r) > 15 and r[15] == 'Y'
        race = races[(prv, city, area, dept, li)]
        c = race.setdefault(no, {'no': int(no), 'name': name, 'party': ds.party_name(party)})
        if deputy:
            c['name'] = f"{c['name']}／{name}"
            continue
        c['name'] = name if '／' not in c['name'] else c['name']
        c['party'] = ds.party_name(party)
        c['elected'] = r[14] in ('*', '!')
        c['incumbent'] = r[13] == 'Y'
    return races


def votes_at(ds, key):
    return {int(r[6]): int(r[7] or 0) for r in ds.tks if tuple(r[:5]) == key}


def turnout_at(ds, key):
    # 部分年份候選人與得票檔帶選區代碼（如 01），投票概況檔的縣市總計則為 00
    for k in (key, (key[0], key[1], '00', key[3], key[4])):
        for r in ds.prof:
            if tuple(r[:5]) == k:
                valid, invalid, votes, electors = (int(x or 0) for x in r[6:10])
                return {'electors': electors, 'votes': votes, 'turnout': pct(votes, electors)}
    return None


def build_race(ds, race_key, cands, at_key=None):
    v = votes_at(ds, at_key or race_key)
    total = sum(v.values())
    out = []
    for no, c in sorted(cands.items(), key=lambda kv: -v.get(int(kv[0]), 0)):
        votes = v.get(int(no), 0)
        out.append({**c, 'votes': votes, 'pct': pct(votes, total)})
    return out


def seats_by_party(races_list):
    seats = defaultdict(int)
    for cands in races_list:
        for c in cands.values():
            if c.get('elected'):
                seats[c['party']] += 1
    return ranked(seats)


def ranked(d):
    """依數量排序並去掉 0"""
    return {k: v for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v}


def sort_counties(items, key='county'):
    order = {c: i for i, c in enumerate(COUNTY_ORDER + LEGACY_COUNTIES)}
    return sorted(items, key=lambda x: order.get(x[key], 99))


def convert(ar, e):
    label = e.get('label', e['id'])
    out = {'id': e['id'], 'label': label, 'title': e['title'], 'date': e['date'], 'kind': e['kind'], 'offices': {}}
    if e.get('note'):
        out['note'] = e['note']
    trend = {'id': e['id'], 'label': label, 'date': e['date'], 'kind': e['kind']}

    if 'president' in e:
        ds = Dataset(ar, e['president'][0])
        races = candidates_of(ds)
        (race_key, cands), = races.items()
        national = ('00', '000', '00', '000', '0000')
        by_county = []
        for (prv, city), county in ds.county.items():
            key = (prv, city, '00', '000', '0000')
            by_county.append({
                'county': county,
                **(turnout_at(ds, key) or {}),
                'candidates': [{'no': c['no'], 'votes': c['votes'], 'pct': c['pct']} for c in build_race(ds, race_key, cands, key)],
            })
        president = build_race(ds, race_key, cands, national)
        out['offices']['president'] = {
            'national': {**(turnout_at(ds, national) or {}), 'candidates': president},
            'byCounty': sort_counties(by_county),
        }
        trend['turnout'] = out['offices']['president']['national'].get('turnout')
        # 同一政黨（如多位無黨籍）的得票率加總，避免互相覆蓋
        share = defaultdict(float)
        for c in president:
            share[c['party']] += c['pct']
        trend['presidentShare'] = {k: round(v, 2) for k, v in sorted(share.items(), key=lambda kv: -kv[1])}

    if 'legislator' in e:
        all_races = []
        by_county = defaultdict(lambda: defaultdict(int))
        for folder in e['legislator']:
            ds = Dataset(ar, folder)
            for key, cands in candidates_of(ds).items():
                all_races.append(cands)
                county = ds.county_of(key) or '原住民（全國）'
                for c in cands.values():
                    if c.get('elected'):
                        by_county[county][c['party']] += 1
        district_seats = seats_by_party(all_races)
        pl = Dataset(ar, e['partylist']) if e.get('partylist') else None
        partylist = []
        for r in (pl.retks if pl else []):
            code, share1, _share2, _n, won = r[:5]
            partylist.append({'party': pl.party_name(code), 'pct': round(float(share1), 2), 'seats': int(won)})
        partylist.sort(key=lambda p: -p['pct'])
        seats = defaultdict(int, district_seats)
        for p in partylist:
            seats[p['party']] += p['seats']
        out['offices']['legislator'] = {
            'seats': ranked(seats),
            'districtSeats': district_seats,
            'partyList': [p for p in partylist if p['pct'] >= 0.5],
            'byCounty': sort_counties([{'county': c, 'seats': dict(s)} for c, s in by_county.items()]),
        }
        trend['legislatorSeats'] = out['offices']['legislator']['seats']
        trend['partyListShare'] = {p['party']: p['pct'] for p in partylist if p['pct'] >= 0.5}

    if 'mayor' in e:
        races_out = []
        for folder in e['mayor']:
            ds = Dataset(ar, folder)
            for key, cands in candidates_of(ds).items():
                races_out.append({
                    'county': ds.county_of(key),
                    **(turnout_at(ds, key) or {}),
                    'candidates': build_race(ds, key, cands),
                })
        if e.get('rerun'):
            race, _villages = chiayi_rerun(ar, e['rerun'])
            races_out.append(race)
        races_out = sort_counties(races_out)
        out['offices']['mayor'] = {'races': races_out}
        mayors = defaultdict(int)
        for r in races_out:
            for c in r['candidates']:
                if c.get('elected'):
                    mayors[c['party']] += 1
        trend['mayorsByParty'] = ranked(mayors)
        electors = sum(r.get('electors', 0) for r in races_out)
        votes = sum(r.get('votes', 0) for r in races_out)
        trend['turnout'] = pct(votes, electors)

    if 'council' in e:
        all_races = []
        by_county = defaultdict(lambda: defaultdict(int))
        for folder in e['council']:
            if not ar.find(VD + folder + '/', 'elcand'):
                continue
            ds = Dataset(ar, folder)
            for key, cands in candidates_of(ds).items():
                all_races.append(cands)
                for c in cands.values():
                    if c.get('elected'):
                        by_county[ds.county_of(key)][c['party']] += 1
        seats = seats_by_party(all_races)
        out['offices']['council'] = {
            'seats': seats,
            'byCounty': sort_counties(
                [{'county': c, 'seats': dict(sorted(s.items(), key=lambda kv: -kv[1]))} for c, s in by_county.items()]
            ),
        }
        trend['councilSeats'] = seats

    return out, trend


def chiayi_rerun(ar, folder):
    """2022 嘉義市長重行選舉：每列一個投開票所，各號次得票分欄"""
    header, *cand_rows = list(ar.rows(folder + 'cand.csv'))
    header, *rows = list(ar.rows(folder + 'prof.csv'))
    col = {name: i for i, name in enumerate(header)}
    n = len(cand_rows)
    vote_col = next(i for name, i in col.items() if name.startswith('投票數'))
    elector_col = next(i for name, i in col.items() if name.startswith('選舉人數'))
    total = defaultdict(int)
    villages = defaultdict(lambda: defaultdict(int))
    electors = votes = 0
    for r in rows:
        town, village = r[0], r[1]
        for i in range(n):
            v = int(r[col[f'號次{i + 1}']] or 0)
            total[i] += v
            villages[f'{town}|{village}'][i] += v
        votes += int(r[vote_col] or 0)
        electors += int(r[elector_col] or 0)
    s = sum(total.values())
    winner = max(total, key=total.get)
    out = []
    for i, c in enumerate(cand_rows):
        out.append({
            'no': int(c[0]), 'name': c[1], 'party': INDEPENDENT if '無黨' in c[2] else c[2],
            'elected': i == winner, 'incumbent': False, 'votes': total[i], 'pct': pct(total[i], s),
        })
    race = {
        'county': '嘉義市', 'electors': electors, 'votes': votes, 'turnout': pct(votes, electors),
        'candidates': sorted(out, key=lambda c: -c['votes']), 'note': '2022/12/18 重行選舉',
    }
    cands = [{'no': c['no'], 'name': c['name'], 'party': c['party']} for c in out]
    vres = {k: [pct(v[i], sum(v.values())) for i in range(n)] for k, v in villages.items()}
    return race, (cands, vres)


# ---------- 我的地區：各村里歷屆投票 ----------

# 每屆選取代表性的選舉：地方選舉看縣市長，總統大選看總統與不分區政黨票
VILLAGE_SOURCES = [
    ('2014-mayor', '2014 縣市長', ['2014-103年地方公職人員選舉/直轄市市長', '2014-103年地方公職人員選舉/縣市市長']),
    ('2016-president', '2016 總統', ['2016總統立委/總統']),
    ('2016-party', '2016 政黨票', ['2016總統立委/不分區政黨']),
    ('2018-mayor', '2018 縣市長', ['2018-107年地方公職人員選舉/直轄市市長', '2018-107年地方公職人員選舉/縣市市長']),
    ('2020-president', '2020 總統', ['2020總統立委/總統']),
    ('2020-party', '2020 政黨票', ['2020總統立委/不分區政黨']),
    ('2022-mayor', '2022 縣市長', ['2022-111年地方公職人員選舉/C1/city', '2022-111年地方公職人員選舉/C1/prv']),
    ('2024-president', '2024 總統', ['2024總統立委/總統']),
    ('2024-party', '2024 政黨票', ['2024總統立委/不分區政黨']),
]
PARTY_MIN_PCT = 1.0  # 政黨票只列全國得票率 1% 以上的政黨，其餘併為「其他」
NATIONAL = ('00', '000', '00', '000', '0000')


def village_results(ar):
    """回傳 {縣市: {'cands': {選舉: [候選人]}, 'villages': {鄉鎮|村里: {選舉: [得票率]}}}}

    得票率的順序與 cands 相同。跨村里的投開票所在名冊中以「甲里、乙里」表示，各村里都計入該所選票。
    """
    out = defaultdict(lambda: {'cands': {}, 'villages': defaultdict(dict)})
    for eid, _title, folders in VILLAGE_SOURCES:
        for folder in folders:
            ds = Dataset(ar, folder)
            races = candidates_of(ds)
            is_party = eid.endswith('party')
            is_national = is_party or eid.endswith('president')
            if is_party:
                nat = votes_at(ds, NATIONAL)
                nat_total = sum(nat.values())
                keep = {no for no, v in nat.items() if pct(v, nat_total) >= PARTY_MIN_PCT}

            agg = defaultdict(lambda: defaultdict(int))
            for r in ds.tks:
                key = tuple(r[:5])
                if key[4] == '0000':
                    continue
                county = ds.county_of(key)
                town = ds.town.get((key[0], key[1], key[3]), '')
                if not county or not town:
                    continue
                for village in (ds.village.get((key[0], key[1], key[3], key[4])) or '').split('、'):
                    if village:
                        agg[(county, f'{town}|{village}')][int(r[6])] += int(r[7] or 0)

            for (county, vkey), votes in agg.items():
                c = out[county]
                if eid not in c['cands']:
                    if is_national:
                        (race_cands,) = races.values()
                    else:
                        race_cands = next(v for k, v in races.items() if ds.county_of(k) == county)
                    if is_party:
                        lst = [{'no': int(no), 'name': rc['name']} for no, rc in race_cands.items() if int(no) in keep]
                        lst.sort(key=lambda x: -nat.get(x['no'], 0))
                        lst.append({'no': 0, 'name': '其他'})
                    else:
                        lst = sorted(
                            ({'no': int(no), 'name': rc['name'], 'party': rc['party']} for no, rc in race_cands.items()),
                            key=lambda x: x['no'],
                        )
                    c['cands'][eid] = lst
                lst = c['cands'][eid]
                total = sum(votes.values())
                listed = [x['no'] for x in lst if x['no']]
                shares = [pct(votes.get(no, 0), total) for no in listed]
                if is_party:
                    shares.append(pct(sum(v for no, v in votes.items() if no not in listed), total))
                c['villages'][vkey][eid] = shares
    return out


# ---------- 公投 ----------

RF_ROOT = 'votedata/votedata/2018_2021公投_2022修憲複決/'
FULLWIDTH = str.maketrans('０１２３４５６７８９', '0123456789')


def referendums(ar):
    """全國性公投結果：全國與各縣市的同意率、投票率、是否通過"""
    titles = json.load(open(os.path.join(ROOT, 'tools', 'referendum_titles.json'), encoding='utf-8'))
    folders = {}
    for n in ar.names:
        if n.startswith(RF_ROOT) and '全國性公投' in n and n.endswith('rftckt.csv'):
            no = int(re.search(r'第(\S+?)案', n).group(1).translate(FULLWIDTH))
            folders[no] = n.rsplit('/', 1)[0] + '/'
    out = []
    for case in titles['cases']:
        folder = folders[case['no']]
        areas = {}
        for r in ar.rows(folder + 'rfarea.csv'):
            if r[0] == 'prv_code':
                continue
            areas[tuple(r[:5])] = r[5]
        prof = {}
        for r in ar.rows(folder + 'rfprof.csv'):
            if r[0] == 'prv_code' or int(r[5] or 0) != 0:
                continue
            # valid, agree, disagree, invalid, votes, electors
            prof[tuple(r[:5])] = [int(x or 0) for x in r[6:12]]
        national = ('00', '000', '00', '000', '0000')
        by_county = []
        result = None
        for r in ar.rows(folder + 'rftckt.csv'):
            if r[0] == 'prv_code' or int(r[5] or 0) != 0:
                continue
            key = tuple(r[:5])
            electors, agree, agree_pct, disagree, disagree_pct = int(r[6]), int(r[7]), float(r[8]), int(r[9]), float(r[10])
            votes = prof.get(key, [0] * 6)[4]
            row = {
                'agree': agree, 'disagree': disagree, 'agreePct': agree_pct,
                'electors': electors, 'turnout': pct(votes, electors),
            }
            if key == national:
                # 公投通過門檻：同意票多於不同意票，且達投票權人總額四分之一
                result = {**row, 'passed': r[12] == 'Y', 'agreeOfElectors': pct(agree, electors)}
            elif key[2:] == ('00', '000', '0000') and areas.get(key) in COUNTY_ORDER:
                by_county.append({'county': areas[key], **row})
        out.append({**case, 'national': result, 'byCounty': sort_counties(by_county)})
    return out


def write_json(name, data):
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(',', ':'))
    return os.path.getsize(path)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ar = Archive(sys.argv[1])
    index, trends = [], []
    for e in ELECTIONS:
        data, trend = convert(ar, e)
        data['source'] = SOURCE
        size = write_json(f"{e['id']}.json", data)
        index.append({k: e[k] for k in ('id', 'title', 'date', 'kind')} | {'label': data['label'], 'offices': list(data['offices'])})
        trends.append(trend)
        print(f"{e['id']}: {', '.join(data['offices'])}（{size // 1024} KB）")
    write_json('index.json', {
        'source': SOURCE, 'sourceUrl': 'https://db.cec.gov.tw/', 'elections': index,
        'villageElections': [{'id': i, 'title': t} for i, t, _ in VILLAGE_SOURCES],
    })

    villages = village_results(ar)
    # 嘉義市 2022 重行選舉補進村里資料
    cy = next(e for e in ELECTIONS if e.get('rerun'))
    _race, (cands, vres) = chiayi_rerun(ar, cy['rerun'])
    villages['嘉義市']['cands']['2022-mayor'] = cands
    for k, shares in vres.items():
        villages['嘉義市']['villages'][k]['2022-mayor'] = shares
    total_size = 0
    for county, v in villages.items():
        total_size += write_json(f'villages/{county}.json', {
            'county': county, 'source': SOURCE, 'cands': v['cands'], 'villages': v['villages'],
        })
    n_villages = sum(len(v['villages']) for v in villages.values())
    print(f'villages/: {len(villages)} 個縣市、{n_villages} 個村里，共 {total_size // 1024} KB')
    write_json('trends.json', sorted(trends, key=lambda t: t['date']))
    rf = referendums(ar)
    write_json('referendums.json', {'source': SOURCE, 'titleSource': '公投主文取自維基百科所引中選會公告', 'cases': rf})
    print(f'referendums.json: {len(rf)} 案')
    print('index.json / trends.json 已寫入')


if __name__ == '__main__':
    main()
