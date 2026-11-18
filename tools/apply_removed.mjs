// 依 tools/removed.json 移除未列入候選人公告的參選人（死亡、資格不合）。
//   node tools/apply_removed.mjs
// 執行後請跑 node check.mjs，通過再 commit、push。
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');
const data = JSON.parse(readFileSync(DATA, 'utf8'));
const { removed } = JSON.parse(readFileSync(join(ROOT, 'tools', 'removed.json'), 'utf8'));

let count = 0;
for (const x of removed) {
  const race = data.races.find(
    (r) => r.office === x.office && r.county === x.county && (r.district ?? '') === (x.district ?? ''),
  );
  if (!race) {
    console.error(`找不到選區：${x.office} ${x.county} ${x.district ?? ''}`);
    process.exit(1);
  }
  const before = race.candidates.length;
  race.candidates = race.candidates.filter((c) => c.name !== x.name);
  if (race.candidates.length < before) count++;
}
data.updated = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
writeElection(DATA, data);
console.log(`移除 ${count} 人（清單 ${removed.length} 人），updated = ${data.updated}`);
