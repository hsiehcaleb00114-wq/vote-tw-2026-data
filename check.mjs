// 檢查 election.json 格式，推上 GitHub 前執行：node check.mjs
import { readFileSync } from 'node:fs';

const OFFICES = ['mayor', 'council', 'township', 'township_rep', 'village'];
const COUNTIES = [
  '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市',
  '基隆市', '新竹市', '新竹縣', '苗栗縣', '彰化縣', '南投縣',
  '雲林縣', '嘉義市', '嘉義縣', '屏東縣', '宜蘭縣', '花蓮縣',
  '臺東縣', '澎湖縣', '金門縣', '連江縣',
];
const LIST_FIELDS = ['education', 'experience', 'platform'];

const file = process.argv[2] ?? 'election.json';
const errors = [];
const err = (where, msg) => errors.push(`${where}：${msg}`);

let data;
try {
  data = JSON.parse(readFileSync(file, 'utf8'));
} catch (e) {
  console.error(`✗ 無法解析 ${file}：${e.message}`);
  process.exit(1);
}

if (!Number.isInteger(data.version)) err('根', 'version 必須是整數');
if (!/^\d{4}-\d{2}-\d{2}$/.test(data.updated ?? '')) err('根', 'updated 必須是 YYYY-MM-DD');
if (!Array.isArray(data.races)) err('根', 'races 必須是陣列');

const raceKeys = new Set();
let people = 0;
for (const [i, r] of (data.races ?? []).entries()) {
  const where = `races[${i}] ${r.county ?? '?'} ${r.district ?? ''}`.trim();
  if (!OFFICES.includes(r.office)) err(where, `office「${r.office}」不是 ${OFFICES.join('/')} 之一`);
  if (!COUNTIES.includes(r.county)) err(where, `county「${r.county}」不在縣市清單（注意用「臺」不是「台」）`);
  if (r.office !== 'mayor' && !r.district) err(where, '非縣市長的選舉需要 district（選區名稱）');

  if (r.indigenous !== undefined && !['plain', 'mountain'].includes(r.indigenous)) err(where, 'indigenous 只能是 plain 或 mountain');
  for (const f of ['seats', 'womenSeats']) {
    if (r[f] !== undefined && !(Number.isInteger(r[f]) && r[f] >= 0)) err(where, `${f} 必須是非負整數`);
  }
  if (r.office === 'council' && !r.area) err(where, '議員選區缺少 area（選區範圍），請執行 tools/import_districts.py');

  const key = [r.office, r.county, r.district ?? ''].join('~');
  if (raceKeys.has(key)) err(where, '同一職位、縣市、選區重複出現');
  raceKeys.add(key);

  if (!Array.isArray(r.candidates)) {
    err(where, 'candidates 必須是陣列');
    continue;
  }
  const names = new Set();
  for (const c of r.candidates) {
    people++;
    const who = `${where} / ${c.name ?? '?'}`;
    if (!c.name?.trim()) err(who, '缺少 name');
    if (!c.party?.trim()) err(who, '缺少 party（無黨籍請填「無黨籍」）');
    if (names.has(c.name)) err(who, '同選區姓名重複');
    names.add(c.name);
    if (c.number !== undefined && !Number.isInteger(c.number)) err(who, 'number 必須是整數');
    if (c.photo !== undefined && !/^https:\/\//.test(c.photo)) err(who, 'photo 必須是 https 網址');
    if (c.photo && !c.photoCredit) err(who, '有照片時必須填 photoCredit（照片來源）');
    if (c.sourceUrl !== undefined && !/^https:\/\//.test(c.sourceUrl)) err(who, 'sourceUrl 必須是 https 網址');
    if (c.photoSourceUrl !== undefined && !/^https:\/\//.test(c.photoSourceUrl)) err(who, 'photoSourceUrl 必須是 https 網址');
    for (const f of LIST_FIELDS) {
      if (c[f] !== undefined && !(Array.isArray(c[f]) && c[f].every((s) => typeof s === 'string' && s.trim())))
        err(who, `${f} 必須是非空字串的陣列`);
    }
  }
}

if (errors.length) {
  console.error(`✗ 發現 ${errors.length} 個問題：`);
  for (const e of errors) console.error('  - ' + e);
  process.exit(1);
}
console.log(`✓ ${file} 格式正確：${data.races.length} 個選區、${people} 位參選人，更新日期 ${data.updated}`);
