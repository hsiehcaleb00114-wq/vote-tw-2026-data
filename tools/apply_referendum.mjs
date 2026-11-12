// 開票夜寫入公投票數，每次更新都執行一次。
//
// 用法：
//   node tools/apply_referendum.mjs --no 22 --agree 3210000 --disagree 2980000 --invalid 120000 \
//     --electorate 19800000 --reported 9500 --total 18000 [--final]
//
// - electorate：投票權人總額（中選會公告；門檻是同意票達其四分之一）
// - reported、total：已回報／總投開票所數，可省略
// - --final：最終結果，會依門檻寫入 passed（通過與否）
//
// 會同時把 results.updatedAt 設成現在時間，App 才會把同一天的多次更新視為新資料。
// 執行後請跑 node check.mjs，通過再 commit、push。

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');

const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? undefined : Number(args[i + 1]);
};
const no = opt('no');
const data = JSON.parse(readFileSync(DATA, 'utf8'));
const q = data.referendums?.find((r) => r.no === no);
if (!q) {
  console.error(`找不到第 ${no} 案，請先執行 node tools/apply_extras.mjs`);
  process.exit(1);
}
const result = { agree: opt('agree'), disagree: opt('disagree'), electorate: opt('electorate') };
for (const [k, v] of Object.entries(result)) {
  if (!Number.isInteger(v) || v < 0) {
    console.error(`--${k} 必須是非負整數`);
    process.exit(1);
  }
}
for (const k of ['invalid', 'reported', 'total']) if (opt(k) !== undefined) result[k] = opt(k);
if (args.includes('--final')) result.passed = result.agree > result.disagree && result.agree * 4 >= result.electorate;
q.result = result;

const taipei = new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 19) + '+08:00';
data.results = { ...(data.results ?? { source: '中選會開票資料' }), updatedAt: taipei };
if (data.updated < taipei.slice(0, 10)) data.updated = taipei.slice(0, 10);
writeElection(DATA, data);
console.log(`✓ 第 ${no} 案：同意 ${result.agree}、不同意 ${result.disagree}${'passed' in result ? (result.passed ? '，通過' : '，不通過') : ''}；updatedAt = ${taipei}`);
