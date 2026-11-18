// 依 tools/added.json 補上登記彙總表漏列、但選舉公報有刊登的參選人。
//   node tools/apply_added.mjs
// 選區不存在就新增（依職位、縣市、選區排序插入）；已存在的參選人不重複加入。
// 執行後請跑 node check.mjs，通過再 commit、push。
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');
const data = JSON.parse(readFileSync(DATA, 'utf8'));
const { added } = JSON.parse(readFileSync(join(ROOT, 'tools', 'added.json'), 'utf8'));

const OFFICES = ['mayor', 'council', 'township', 'township_rep', 'village'];
const COUNTIES = [
  '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市', '基隆市', '新竹市', '新竹縣', '苗栗縣', '彰化縣',
  '南投縣', '雲林縣', '嘉義市', '嘉義縣', '屏東縣', '宜蘭縣', '花蓮縣', '臺東縣', '澎湖縣', '金門縣', '連江縣',
];
const order = (r) => [OFFICES.indexOf(r.office), COUNTIES.indexOf(r.county), r.district ?? ''];
const before = (a, b) => {
  const x = order(a);
  const y = order(b);
  return x[0] - y[0] || x[1] - y[1] || (x[2] < y[2] ? -1 : x[2] > y[2] ? 1 : 0);
};

let count = 0;
for (const x of added) {
  let race = data.races.find(
    (r) => r.office === x.office && r.county === x.county && (r.district ?? '') === (x.district ?? ''),
  );
  if (!race) {
    race = { office: x.office, county: x.county, ...(x.district ? { district: x.district } : {}), candidates: [] };
    const i = data.races.findIndex((r) => before(race, r) < 0);
    data.races.splice(i === -1 ? data.races.length : i, 0, race);
  }
  for (const c of x.candidates) {
    if (race.candidates.some((o) => o.name === c.name)) continue;
    race.candidates.push({ ...c });
    count++;
  }
  if (race.candidates.every((c) => c.number !== undefined)) race.candidates.sort((a, b) => a.number - b.number);
}
// 補上參選人的村里不再是「無人登記」
const filled = new Set(added.filter((x) => x.office === 'village').map((x) => x.county + x.district));
data.vacantVillages = (data.vacantVillages ?? []).filter((v) => !filled.has(v.county + v.district));
data.updated = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
writeElection(DATA, data);
console.log(`補入 ${count} 人，updated = ${data.updated}`);
