// 依 import_cec.py 的排版寫回 election.json：每位參選人一行，分隔符號與 Python json.dumps 相同（", "、": "），
// 這樣 git diff 只會出現真正有變動的那幾行。
import { writeFileSync } from 'node:fs';

const dump = (v) => {
  if (Array.isArray(v)) return '[' + v.map(dump).join(', ') + ']';
  if (v && typeof v === 'object') {
    return '{' + Object.entries(v).map(([k, x]) => JSON.stringify(k) + ': ' + dump(x)).join(', ') + '}';
  }
  return JSON.stringify(v);
};

export function writeElection(path, data) {
  const out = ['{', `  "version": ${dump(data.version)},`, `  "updated": ${dump(data.updated)},`];
  if (data.source) out.push(`  "source": ${dump(data.source)},`);
  if (data.results) out.push(`  "results": ${dump(data.results)},`);
  out.push('  "races": [');
  data.races.forEach((r, i) => {
    const { candidates, ...head } = r;
    out.push('    ' + dump(head).slice(0, -1) + ', "candidates": [');
    candidates.forEach((c, j) => out.push('      ' + dump(c) + (j < candidates.length - 1 ? ',' : '')));
    out.push('    ]}' + (i < data.races.length - 1 ? ',' : ''));
  });
  out.push('  ]', '}');
  writeFileSync(path, out.join('\n') + '\n');
}
