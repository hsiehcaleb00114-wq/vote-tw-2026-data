// 產生「假的」開票票數，只用來測試 App 的開票畫面。
// 輸出到 tools/sim/（已加入 .gitignore），絕對不要把結果推上 GitHub。
//
// 用法：node tools/simulate_results.mjs <進度 0–1> [--final]
//   例：node tools/simulate_results.mjs 0.35  → tools/sim/election.sim.json（開票 35%）

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const progress = Math.max(0, Math.min(1, Number(process.argv[2] ?? 0.5)));
const final = process.argv.includes('--final');

const data = JSON.parse(readFileSync(join(ROOT, 'election.json'), 'utf8'));

// 固定亂數種子，讓同一個候選人在不同進度下的「實力」一致，票數只隨進度增加
const rand = (seed) => {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return ((h >>> 0) % 10000) / 10000;
};

const TOTAL_STATIONS = 18000;
for (const r of data.races) {
  if (!['mayor', 'council', 'township', 'village'].includes(r.office)) continue;
  const scale = r.office === 'mayor' ? 400000 : r.office === 'council' ? 30000 : 3000;
  // 每個選區的開票速度略有不同
  const p = Math.min(1, progress * (0.8 + rand(r.county + r.district) * 0.4));
  const strength = r.candidates.map((c) => rand(c.name) ** 2);
  r.candidates.forEach((c, i) => {
    c.votes = Math.round(scale * strength[i] * p);
    delete c.elected;
  });
  if (final) {
    const seats = r.seats ?? 1;
    [...r.candidates].sort((a, b) => b.votes - a.votes).slice(0, seats).forEach((c) => (c.elected = true));
  }
  const stations = Math.round(20 + rand(r.county) * 200);
  r.progress = { reported: Math.round(stations * p), total: stations };
}
data.results = {
  updatedAt: `2026-11-28T${String(16 + Math.floor(progress * 6)).padStart(2, '0')}:${String(Math.floor((progress * 360) % 60)).padStart(2, '0')}:00+08:00`,
  final,
  source: '模擬資料（非真實結果）',
  progress: { reported: Math.round(TOTAL_STATIONS * progress), total: TOTAL_STATIONS },
};

mkdirSync(join(ROOT, 'tools', 'sim'), { recursive: true });
const out = join(ROOT, 'tools', 'sim', 'election.sim.json');
writeFileSync(out, JSON.stringify(data));
console.log(`模擬開票 ${Math.round(progress * 100)}%${final ? '（最終）' : ''} → ${out}`);
