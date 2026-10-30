// 把候選人號次寫進 election.json。號次抽籤後、各選委會公告名單後執行。
//
// 用法：
//   node tools/apply_numbers.mjs tools/ballot_numbers/mayor.csv [--source "中央社 10/27 整理各縣市抽籤結果"]
//
// CSV 欄位（第一列為標題）：
//   office,county,district,name,number
//   - office：mayor / council / township / township_rep / village
//   - district：縣市長留空；其他職位同 election.json 的 district（如「第1選舉區」「松山區莊敬里」）
//
// 名單裡任何一人對不到資料、或號次在同一選區重複，就整批不寫入。
// 執行後請跑 node check.mjs，通過再 commit、push。

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');

const args = process.argv.slice(2);
const csvPath = args.find((a) => !a.startsWith('--'));
const si = args.indexOf('--source');
const source = si === -1 ? undefined : args[si + 1];
if (!csvPath) {
  console.error('用法：node tools/apply_numbers.mjs <號次.csv> [--source "來源"]');
  process.exit(1);
}

const data = JSON.parse(readFileSync(DATA, 'utf8'));
const rows = readFileSync(csvPath, 'utf8')
  .trim()
  .split(/\r?\n/)
  .slice(1)
  .map((line) => {
    const [office, county, district, name, number] = line.split(',').map((s) => s.trim());
    return { office, county, district: district || undefined, name, number: Number(number) };
  });

const errors = [];
const updates = [];
const seen = new Map();
for (const row of rows) {
  if (!Number.isInteger(row.number) || row.number < 1) errors.push(`號次不正確：${row.county} ${row.name} ${row.number}`);
  const race = data.races.find(
    (r) => r.office === row.office && r.county === row.county && (r.district ?? undefined) === row.district,
  );
  const cand = race?.candidates.find((c) => c.name === row.name);
  if (!cand) {
    errors.push(`找不到：${row.office} ${row.county} ${row.district ?? ''} ${row.name}`);
    continue;
  }
  const key = `${row.office}|${row.county}|${row.district ?? ''}|${row.number}`;
  if (seen.has(key)) errors.push(`號次重複：${row.county} ${row.district ?? ''} ${row.number} 號（${seen.get(key)}、${row.name}）`);
  seen.set(key, row.name);
  updates.push([cand, row.number]);
}

if (errors.length) {
  console.error(errors.join('\n'));
  console.error(`共 ${errors.length} 個問題，未寫入。`);
  process.exit(1);
}

let changed = 0;
for (const [cand, number] of updates) {
  if (cand.number !== number) changed++;
  cand.number = number;
}
// 整個選區都有號次後，依號次排序，App 列表就和選票順序一致
for (const race of data.races) {
  if (race.candidates.length && race.candidates.every((c) => c.number !== undefined)) {
    race.candidates.sort((a, b) => a.number - b.number);
  }
}
data.updated = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
if (source && !data.source.includes(source)) data.source += `；號次：${source}`;
writeElection(DATA, data);
console.log(`寫入 ${updates.length} 人號次（${changed} 筆有變動），updated = ${data.updated}`);
