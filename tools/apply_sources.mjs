// 把參選人的選舉公報連結（sourceUrl）寫進 election.json。
//
// 用法：
//   node tools/apply_sources.mjs tools/ballot_numbers/bulletin_links.tsv
//
// TSV 欄位（第一列為標題）：office, county, district, name, sourceUrl
// 由 tools/bulletin_links.py 產生。已有不同 sourceUrl（人工填的）的參選人不覆蓋，只列出來。
// 名單裡任何一人對不到資料就整批不寫入。執行後請跑 node check.mjs，通過再 commit、push。

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');
const tsvPath = process.argv[2];
if (!tsvPath) {
  console.error('用法：node tools/apply_sources.mjs <公報連結.tsv>');
  process.exit(1);
}

const data = JSON.parse(readFileSync(DATA, 'utf8'));
const rows = readFileSync(tsvPath, 'utf8')
  .trim()
  .split(/\r?\n/)
  .slice(1)
  .map((line) => {
    const [office, county, district, name, sourceUrl] = line.split('\t');
    return { office, county, district: district || undefined, name, sourceUrl };
  });

const errors = [];
const updates = [];
for (const row of rows) {
  if (!/^https:\/\//.test(row.sourceUrl ?? '')) errors.push(`網址不正確：${row.county} ${row.name} ${row.sourceUrl}`);
  const race = data.races.find(
    (r) => r.office === row.office && r.county === row.county && (r.district ?? undefined) === row.district,
  );
  const cand = race?.candidates.find((c) => c.name === row.name);
  if (!cand) errors.push(`找不到：${row.office} ${row.county} ${row.district ?? ''} ${row.name}`);
  else updates.push([cand, row]);
}
if (errors.length) {
  console.error(errors.join('\n'));
  console.error(`共 ${errors.length} 個問題，未寫入。`);
  process.exit(1);
}

let changed = 0;
const kept = [];
// 同一份公報先前自動填過的連結（含不同頁碼）可以更新；其他網址視為人工填寫，保留
const base = (u) => u.split('#')[0];
for (const [cand, row] of updates) {
  if (cand.sourceUrl && base(cand.sourceUrl) !== base(row.sourceUrl)) {
    kept.push(`${row.county} ${row.district ?? ''} ${row.name}：保留 ${cand.sourceUrl}`);
    continue;
  }
  if (cand.sourceUrl !== row.sourceUrl) changed++;
  cand.sourceUrl = row.sourceUrl;
}
data.updated = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
writeElection(DATA, data);
console.log(`寫入 ${changed} 人的公報連結（清單 ${rows.length} 人）`);
if (kept.length) console.log(`已有其他網址、未覆蓋 ${kept.length} 人：\n  ${kept.join('\n  ')}`);
