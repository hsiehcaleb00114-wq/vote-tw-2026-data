"""掃描公報：依「號次」「姓名」表頭找出每個候選人格，把直排的號次與姓名字逐字切開、橫排拼成一行，再交給 OCR。

用法：python compose.py <整頁 OCR json> <整頁 png> <輸出資料夾> <前綴>
輸出：每格一張 <前綴>_<i>.png，以及 <前綴>_cells.json（每格的座標）
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')


def ink(img):
    a = np.asarray(img.convert('RGB')).astype(np.int16)
    return a.min(axis=2) < 150  # 黑色與洋紅等彩色字都算墨


def runs(mask1d, min_gap):
    """一維墨跡投影切段：回傳 (start, end)，間隔小於 min_gap 的段落合併"""
    idx = np.flatnonzero(mask1d)
    if not len(idx):
        return []
    out = [[idx[0], idx[0]]]
    for i in idx[1:]:
        if i - out[-1][1] <= min_gap:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [(a, b + 1) for a, b in out]


def strip_borders(m):
    """去掉格線：整列或整欄墨跡比例很高的視為框線"""
    m = m.copy()
    h, w = m.shape
    m[m.mean(axis=1) > 0.6, :] = False
    m[:, m.mean(axis=0) > 0.6] = False
    return m


def glyphs(m, vertical):
    """切出大字：直排依列投影、橫排依欄投影"""
    m = strip_borders(m)
    if not m.any():
        return []
    ys = runs(m.any(axis=1), 3)
    xs = runs(m.any(axis=0), 3)
    out = []
    if vertical:
        x0, x1 = min(a for a, _ in xs), max(b for _, b in xs)
        for a, b in ys:
            sub = m[a:b, x0:x1]
            cx = runs(sub.any(axis=0), 3)
            out.append((cx[0][0] + x0, a, cx[-1][1] + x0, b))
    else:
        for a, b in xs:
            yy = runs(m[:, a:b].any(axis=1), 3)
            if not yy:
                continue
            # 一段裡最高的一塊才是號次；細長的殘留框線（寬不到高的 1/8）不要
            y0, y1 = max(yy, key=lambda r: r[1] - r[0])
            if (b - a) * 8 < (y1 - y0) or (y1 - y0) < 12:
                continue
            out.append((a, y0, b, y1))
        if out:
            # 多位數：只留和最高那塊等高的
            hmax = max(g[3] - g[1] for g in out)
            out = [g for g in out if g[3] - g[1] > hmax * 0.6]
    return out


def compose(parts, height=60, gap=20):
    """把多張小圖等高橫排：每段之間空白"""
    imgs = []
    for p in parts:
        w, h = p.size
        s = height / max(h, 1)
        imgs.append(p.resize((max(1, int(w * s)), height), Image.LANCZOS))
    total = sum(i.size[0] for i in imgs) + gap * (len(imgs) + 1)
    canvas = Image.new('L', (total, height + 2 * gap), 255)
    x = gap
    for i in imgs:
        canvas.paste(i, (x, gap))
        x += i.size[0] + gap
    return canvas


def main():
    ocr_path, png_path, out_dir, prefix = sys.argv[1:5]
    page = json.load(open(ocr_path, encoding='utf-8'))
    img = Image.open(png_path).convert('RGB')
    m = ink(img)
    gray = Image.fromarray(np.where(m, 0, 255).astype(np.uint8))
    lines = {}
    for w in page['words']:
        lines.setdefault(w[4], []).append(w)
    heads = []  # (文字, x, y, w, h) 逐字
    for ws in lines.values():
        for w in ws:
            for i, ch in enumerate(w[5]):
                cw = w[2] / max(len(w[5]), 1)
                heads.append((ch, w[0] + i * cw, w[1], cw, w[3]))

    def find(word):
        out = []
        for i in range(len(heads) - 1):
            a, b = heads[i], heads[i + 1]
            if a[0] == word[0] and b[0] == word[1] and abs(a[2] - b[2]) < 8 and 0 < b[1] - a[1] < a[3] * 3:
                out.append((a[1], a[2], b[1] + b[3] - a[1], max(a[4], b[4])))
        return out

    nums, names = find('號次'), find('姓名')
    stops = find('基本') + find('出生') + find('學歷') + find('號次')
    cells = []
    for nx, ny, nw, nh in nums:
        # 同列、右側最近的「姓名」
        cand = [n for n in names if abs(n[1] - ny) < 15 and 0 < n[0] - nx < nw * 5]
        if not cand:
            continue
        sx, sy, sw, sh = min(cand, key=lambda n: n[0])
        top = int(ny + nh + 8)
        below = [s[1] for s in stops if s[1] > top + 40 and s[0] < sx + sw * 2 and s[0] + s[2] > nx - nw]
        bottom = int(min(below) - 8) if below else int(top + 12 * nh)
        # 號次欄：表頭左緣往左一點到姓名表頭左緣；姓名欄：姓名表頭左右各延伸半個表頭寬
        mid = (nx + nw + sx) / 2
        num_box = (int(nx - nw * 0.4), top, int(mid), bottom)
        name_box = (int(mid), top, int(sx + sw + sw * 0.6), bottom)
        cells.append({'num': num_box, 'name': name_box})

    for i, c in enumerate(cells):
        nb, mb = c['num'], c['name']
        ng = glyphs(m[nb[1]:nb[3], nb[0]:nb[2]], vertical=False)
        mg = glyphs(m[mb[1]:mb[3], mb[0]:mb[2]], vertical=True)
        c['n_num'], c['n_name'] = len(ng), len(mg)
        if not ng or not mg or len(mg) > 14:
            continue
        # 號次字可能有多位數（橫排），整塊當一張
        nx0, ny0 = min(g[0] for g in ng), min(g[1] for g in ng)
        nx1, ny1 = max(g[2] for g in ng), max(g[3] for g in ng)
        parts = [gray.crop((nb[0] + nx0, nb[1] + ny0, nb[0] + nx1, nb[1] + ny1))]
        parts += [gray.crop((mb[0] + g[0], mb[1] + g[1], mb[0] + g[2], mb[1] + g[3])) for g in mg]
        compose(parts).save(os.path.join(out_dir, f'{prefix}_{i}.png'))
    json.dump(cells, open(os.path.join(out_dir, f'{prefix}_cells.json'), 'w', encoding='utf-8'))
    print(len(cells), [(c['n_num'], c['n_name']) for c in cells])


if __name__ == '__main__':
    main()
