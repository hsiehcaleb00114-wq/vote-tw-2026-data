"""OCR 讀不出號次的格子：換大小、留白重做。

python -I retry.py make <cells 資料夾>    產生 *_v0.png… 與清單 list_retry.txt
python -I retry.py merge <cells 資料夾>   把變體結果併回：原本讀不出、變體讀得出且各變體一致者，寫回主 json
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, 'C:/VoteTW/.pylib')
from PIL import Image  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
CELL = re.compile(r'^[^\d\u3400-\u9fff]{0,2}(\d{1,2})(?!\d)')
VARIANTS = [(0.6, 30), (1.6, 40), (1.0, 80), (0.8, 120)]


def ok(path):
    if not os.path.exists(path):
        return None
    words = json.load(open(path, encoding='utf-8')).get('words', [])
    return ''.join(w[5] for w in words)


def main():
    step, d = sys.argv[1], sys.argv[2]
    mains = [p for p in glob.glob(os.path.join(d, '*.png')) if not re.search(r'_v\d\.png$', p)]
    if step == 'make':
        lines = []
        for png in mains:
            text = ok(png[:-4] + '.json')
            if text is None or CELL.match(text):
                continue
            img = Image.open(png).convert('L')
            for k, (scale, pad) in enumerate(VARIANTS):
                w, h = img.size
                v = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
                canvas = Image.new('L', (v.size[0] + 2 * pad, v.size[1] + 2 * pad), 255)
                canvas.paste(v, (pad, pad))
                out = png[:-4] + f'_v{k}.png'
                canvas.save(out)
                lines.append(f'{out.replace(os.sep, "/")}\t{out[:-4].replace(os.sep, "/")}.json')
        open(os.path.join(d, 'list_retry.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        print(len(lines), 'variants')
    else:
        fixed = conflict = 0
        for png in mains:
            base = png[:-4]
            text = ok(base + '.json')
            if text is None or CELL.match(text):
                continue
            reads = [ok(base + f'_v{k}.json') for k in range(len(VARIANTS))]
            good = [t for t in reads if t and CELL.match(t)]
            if not good:
                continue
            nums = {CELL.match(t).group(1) for t in good}
            if len(nums) > 1:
                conflict += 1
                continue
            # 取最長（姓名最完整）的一個
            best = max(good, key=len)
            j = json.load(open(base + '.json', encoding='utf-8'))
            j['words'] = [[0, 0, 0, 0, 0, best]]
            j['retry'] = True
            json.dump(j, open(base + '.json', 'w', encoding='utf-8'), ensure_ascii=False)
            fixed += 1
        print('fixed', fixed, 'conflict', conflict)


if __name__ == '__main__':
    main()
