// 把開票票數寫進 election.json，開票夜每次更新都執行一次。
//
// 用法：
//   node tools/apply_results.mjs <票數.csv> --reported 9500 --total 18000 [--final] [--source "中選會開票資料"]
//
// CSV 欄位（第一列為標題）：
//   office,county,district,name,votes,elected,reported,total
//   - office：mayor / council / township / township_rep / village
//   - district：縣市長留空；其他職位同 election.json 的 district（如「第1選舉區」「松山區莊敬里」）
//   - elected：當選填 Y，其他留空
//   - reported、total：該選區已回報／應回報投開票所數，可留空
//
// 會自動把 results.updatedAt 設成現在時間，App 才會把同一天的多次更新視為新資料。
// 執行後請跑 node check.mjs，通過再 commit、push。

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');

const args = process.argv.slice(2);
const csvPath = args.find((a) => !a.startsWith('--'));
const opt = (name) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? undefined : args[i + 1];
};
if (!csvPath) {
  console.error('用法：node tools/apply_results.mjs <票數.csv> --reported N --total N [--final]');
  process.exit(1);
}

const [header, ...lines] = readFileSync(csvPath, 'utf8').replace(/^﻿/, '').trim().split(/\r?\n/);
const cols = header.split(',').map((s) => s.trim());
const col = (name) => cols.indexOf(name);
for (const need of ['office', 'county', 'name', 'votes']) {
  if (col(need) === -1) {
    console.error(`CSV 缺少欄位：${need}`);
    process.exit(1);
  }
}

const data = JSON.parse(readFileSync(DATA, 'utf8'));
const raceKey = (office, county, district) => `${office}~${county}~${district ?? ''}`;
const races = new Map(data.races.map((r) => [raceKey(r.office, r.county, r.district), r]));

const missing = [];
let updated = 0;
for (const line of lines) {
  const cells = line.split(',').map((s) => s.trim());
  const get = (name) => (col(name) === -1 ? '' : cells[col(name)] ?? '');
  const race = races.get(raceKey(get('office'), get('county'), get('district') || undefined));
  const cand = race?.candidates.find((c) => c.name === get('name'));
  if (!cand) {
    missing.push(`${get('county')}${get('district')} ${get('name')}`);
    continue;
  }
  cand.votes = Number(get('votes')) || 0;
  if (get('elected').toUpperCase() === 'Y') cand.elected = true;
  else delete cand.elected;
  if (get('reported') && get('total')) {
    race.progress = { reported: Number(get('reported')), total: Number(get('total')) };
  }
  updated++;
}

// 台灣時間 ISO 8601，例如 2026-11-28T18:30:00+08:00
const taipei = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 19) + '+08:00';
data.results = {
  updatedAt: taipei,
  final: args.includes('--final'),
  source: opt('source') ?? '中選會開票資料',
  ...(opt('reported') && opt('total') ? { progress: { reported: Number(opt('reported')), total: Number(opt('total')) } } : {}),
};
if (data.updated < taipei.slice(0, 10)) data.updated = taipei.slice(0, 10);

// 沿用 import_cec.py 的排版：每位參選人一行
const dump = (v) => JSON.stringify(v);
const out = ['{', `  "version": ${dump(data.version)},`, `  "updated": ${dump(data.updated)},`];
if (data.source) out.push(`  "source": ${dump(data.source)},`);
out.push(`  "results": ${dump(data.results)},`, '  "races": [');
data.races.forEach((r, i) => {
  const { candidates, ...head } = r;
  out.push('    ' + dump(head).slice(0, -1) + ', "candidates": [');
  candidates.forEach((c, j) => out.push('      ' + dump(c) + (j < candidates.length - 1 ? ',' : '')));
  out.push('    ]}' + (i < data.races.length - 1 ? ',' : ''));
});
out.push('  ]', '}');
writeFileSync(DATA, out.join('\n') + '\n');

console.log(`✓ 更新 ${updated} 位參選人的票數，results.updatedAt = ${taipei}`);
if (missing.length) {
  console.error(`✗ ${missing.length} 筆對不到參選人（請檢查職位、縣市、選區、姓名）：`);
  for (const m of missing.slice(0, 20)) console.error('  - ' + m);
  process.exit(1);
}
