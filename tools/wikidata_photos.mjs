// 從維基數據／維基共享資源比對參選人的自由授權照片，寫入 election.json。
//
// 用法：node tools/wikidata_photos.mjs [--dry-run]
//
// 比對規則（寧缺勿錯）：
// - 只處理縣市長、縣市議員、鄉鎮市長（含原住民區長）；村里長、代表同名機率太高不處理
// - 維基數據條目必須是「人」、有照片（P18）、標籤與姓名完全相同、與臺灣有關
// - 必須有從政的證據（描述或曾任職位）
// - 議員、鄉鎮市長還要在描述或職位中出現同一個縣市
// - 同一個姓名符合條件的條目超過一個就跳過
// 結果另存 tools/photo_matches.tsv 供人工逐筆檢查。

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');
const UA = 'vote-tw-2026-data/1.0 (https://github.com/hsiehcaleb00114-wq/vote-tw-2026-data)';
const DRY = process.argv.includes('--dry-run');
const OFFICES = new Set(['mayor', 'council', 'township']);
const THUMB_WIDTH = 320;

const COUNTY_ALIASES = {
  臺北市: ['臺北', '台北', 'Taipei'], 新北市: ['新北', 'New Taipei'], 桃園市: ['桃園', 'Taoyuan'],
  臺中市: ['臺中', '台中', 'Taichung'], 臺南市: ['臺南', '台南', 'Tainan'], 高雄市: ['高雄', 'Kaohsiung'],
  基隆市: ['基隆', 'Keelung'], 新竹市: ['新竹市', 'Hsinchu City'], 新竹縣: ['新竹縣', 'Hsinchu County'],
  苗栗縣: ['苗栗', 'Miaoli'], 彰化縣: ['彰化', 'Changhua'], 南投縣: ['南投', 'Nantou'],
  雲林縣: ['雲林', 'Yunlin'], 嘉義市: ['嘉義市', 'Chiayi City'], 嘉義縣: ['嘉義縣', 'Chiayi County'],
  屏東縣: ['屏東', 'Pingtung'], 宜蘭縣: ['宜蘭', 'Yilan'], 花蓮縣: ['花蓮', 'Hualien'],
  臺東縣: ['臺東', '台東', 'Taitung'], 澎湖縣: ['澎湖', 'Penghu'], 金門縣: ['金門', 'Kinmen'],
  連江縣: ['連江', '馬祖', 'Lienchiang', 'Matsu'],
};
const TAIWAN = /臺灣|台灣|中華民國|Taiwan|Republic of China/;
const POLITICAL = /政治|議員|市長|縣長|鄉長|鎮長|區長|立法委員|立委|國大|politician|legislator|mayor|magistrate|councillor|councilor|council/i;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url, init = {}) {
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(url, { ...init, headers: { 'User-Agent': UA, Accept: 'application/json', ...init.headers } });
    if (res.ok) return res.json();
    if (attempt >= 4 || ![429, 500, 502, 503, 504].includes(res.status)) throw new Error(`${res.status} ${url.slice(0, 120)}`);
    await sleep(2000 * attempt);
  }
}

async function sparql(query) {
  const body = new URLSearchParams({ query, format: 'json' });
  const j = await getJson('https://query.wikidata.org/sparql', {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return j.results.bindings;
}

/** 姓名中的漢字部分（原住民族語拼音另外列在後面，維基數據標籤通常只有漢字） */
const hanName = (name) => name.match(/^[㐀-鿿\u{20000}-\u{3134f}]+/u)?.[0] ?? name;

async function lookup(names) {
  const values = names.flatMap((n) => ['zh-tw', 'zh-hant', 'zh'].map((l) => `${JSON.stringify(n)}@${l}`)).join(' ');
  const rows = await sparql(`
    SELECT ?p (SAMPLE(STR(?l)) AS ?name) (SAMPLE(?image) AS ?img)
      (GROUP_CONCAT(DISTINCT ?d; separator=" | ") AS ?descs)
      (GROUP_CONCAT(DISTINCT ?posL; separator=" | ") AS ?positions)
      (GROUP_CONCAT(DISTINCT STR(?cit); separator=" ") AS ?cits)
    WHERE {
      VALUES ?l { ${values} }
      ?p rdfs:label ?l ; wdt:P31 wd:Q5 ; wdt:P18 ?image .
      OPTIONAL { ?p wdt:P27 ?cit }
      OPTIONAL { ?p schema:description ?d FILTER(LANG(?d) IN ("zh-tw", "zh-hant", "zh", "en")) }
      OPTIONAL { ?p wdt:P39 ?pos . ?pos rdfs:label ?posL FILTER(LANG(?posL) IN ("zh-tw", "zh-hant", "zh")) }
    } GROUP BY ?p`);
  return rows.map((r) => ({
    qid: r.p.value.split('/').pop(),
    name: r.name.value,
    image: decodeURIComponent(r.img.value.split('/').pop()),
    descs: r.descs?.value ?? '',
    positions: r.positions?.value ?? '',
    taiwan: (r.cits?.value ?? '').includes('Q865'),
  }));
}

const stripHtml = (s) => (s ?? '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();

async function imageInfo(files) {
  const out = {};
  for (let i = 0; i < files.length; i += 40) {
    const titles = files.slice(i, i + 40).map((f) => 'File:' + f).join('|');
    const url =
      'https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo' +
      `&iiprop=url|extmetadata&iiurlwidth=${THUMB_WIDTH}&titles=${encodeURIComponent(titles)}`;
    const j = await getJson(url);
    const normalized = Object.fromEntries((j.query.normalized ?? []).map((n) => [n.to, n.from]));
    for (const page of Object.values(j.query.pages)) {
      const info = page.imageinfo?.[0];
      if (!info) continue;
      const m = info.extmetadata ?? {};
      const file = (normalized[page.title] ?? page.title).replace(/^File:/, '');
      out[file] = {
        thumb: info.thumburl,
        page: info.descriptionurl,
        artist: stripHtml(m.Artist?.value),
        license: stripHtml(m.LicenseShortName?.value),
      };
    }
    await sleep(300);
  }
  return out;
}

function writeCompact(data, path) {
  const dump = (v) => JSON.stringify(v);
  const lines = ['{', `  "version": ${dump(data.version)},`, `  "updated": ${dump(data.updated)},`];
  if (data.source) lines.push(`  "source": ${dump(data.source)},`);
  lines.push('  "races": [');
  data.races.forEach((r, i) => {
    const { candidates, ...head } = r;
    lines.push('    ' + dump(head).slice(0, -1) + ', "candidates": [');
    candidates.forEach((c, j) => lines.push('      ' + dump(c) + (j < candidates.length - 1 ? ',' : '')));
    lines.push('    ]}' + (i < data.races.length - 1 ? ',' : ''));
  });
  lines.push('  ]', '}');
  writeFileSync(path, lines.join('\n') + '\n');
}

const data = JSON.parse(readFileSync(DATA, 'utf8'));
const targets = data.races
  .filter((r) => OFFICES.has(r.office))
  .flatMap((r) => r.candidates.map((c) => ({ race: r, c, han: hanName(c.name) })));
const names = [...new Set(targets.map((t) => t.han))];
console.log(`比對 ${targets.length} 位參選人（${names.length} 個不重複姓名）…`);

const byName = {};
for (let i = 0; i < names.length; i += 120) {
  for (const e of await lookup(names.slice(i, i + 120))) (byName[e.name] ??= []).push(e);
  process.stdout.write(`  ${Math.min(i + 120, names.length)}/${names.length}\r`);
  await sleep(500);
}
console.log();

const matches = [];
const skipped = [];
for (const t of targets) {
  const text = (e) => `${e.descs} ${e.positions}`;
  const inCounty = (e) => COUNTY_ALIASES[t.race.county].some((a) => text(e).includes(a));
  let ok = (byName[t.han] ?? []).filter((e) => {
    if (!e.taiwan && !TAIWAN.test(text(e))) return false;
    if (!POLITICAL.test(text(e)) && !e.positions) return false;
    return t.race.office === 'mayor' || inCounty(e);
  });
  // 縣市長候選人有同名政治人物時，改用縣市區分
  if (ok.length > 1 && t.race.office === 'mayor') ok = ok.filter(inCounty);
  if (ok.length === 1) matches.push({ ...t, e: ok[0] });
  else if (ok.length > 1) skipped.push(`${t.c.name}（${t.race.county}）：${ok.length} 個同名條目，跳過`);
}

const infos = await imageInfo([...new Set(matches.map((m) => m.e.image))]);
const tsv = ['職位\t縣市\t選區\t姓名\tWikidata\t描述\t曾任職位\t授權\t作者'];
let applied = 0;
for (const m of matches) {
  const info = infos[m.e.image];
  if (!info?.thumb || !info.license) {
    skipped.push(`${m.c.name}：照片缺少授權資訊，跳過`);
    continue;
  }
  tsv.push([m.race.office, m.race.county, m.race.district ?? '', m.c.name, m.e.qid, m.e.descs, m.e.positions, info.license, info.artist].join('\t'));
  m.c.photo = info.thumb;
  m.c.photoCredit = `${info.artist || '佚名'}／${info.license}（維基共享資源）`;
  m.c.photoSourceUrl = info.page;
  applied++;
}

writeFileSync(join(ROOT, 'tools', 'photo_matches.tsv'), tsv.join('\n') + '\n');
console.log(`找到 ${applied} 張照片，另有 ${skipped.length} 筆跳過`);
for (const s of skipped) console.log('  - ' + s);
if (!DRY) {
  writeCompact(data, DATA);
  console.log('已寫入 election.json');
}
