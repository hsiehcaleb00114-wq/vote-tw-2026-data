// 把 tools/extras.json 的公投與無人登記村里寫進 election.json（保留開票結果等其他欄位）。
//   node tools/apply_extras.mjs
// 執行後請跑 node check.mjs，通過再 commit、push。
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeElection } from './write_election.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = join(ROOT, 'election.json');
const data = JSON.parse(readFileSync(DATA, 'utf8'));
const extras = JSON.parse(readFileSync(join(ROOT, 'tools', 'extras.json'), 'utf8'));

// 開票結果（result）由開票工具寫入，重新套用時保留
const oldResults = new Map((data.referendums ?? []).map((r) => [r.no, r.result]));
const { races, ...head } = data;
const merged = { ...head, referendums: extras.referendums.map((r) => ({ ...r, ...(oldResults.get(r.no) ? { result: oldResults.get(r.no) } : {}) })), vacantVillages: extras.vacantVillages, races };
merged.updated = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
writeElection(DATA, merged);
console.log(`公投 ${merged.referendums.length} 案、無人登記村里 ${merged.vacantVillages.length} 個，updated = ${merged.updated}`);
