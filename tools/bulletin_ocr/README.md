# 掃描版選舉公報 OCR

部分公報是掃描圖片，或文字層是亂碼（`bulletin_match.py` 會列在 `garbled.tsv`），這些工具用 Windows 內建 OCR（zh-Hant-TW）讀號次。
工作資料夾寫死在 `C:/VoteTW/.ocr`（`OCR_WORK` 可改），PyMuPDF／Pillow／numpy 在 `C:/VoteTW/.pylib`。

1. `python -I stage.py fetch <清單.tsv>`、`stage.py pages`：下載、轉圖、整頁 OCR
2. 直排姓名版型（「號次」「姓名」表頭）：`stage.py cells`，再 `retry.py make/merge` 重試讀不出的格子，`stage.py collect`
3. 橫排姓名版型：`anchor.py build`，`ocr.ps1 list_b.txt`，`anchor.py collect`
4. `python ocr_match.py villages.txt out.csv results.json results_b.json …`

整頁 OCR 讀不到單獨的大號次與直排姓名，所以把號次字與姓名逐字切下、橫排成一行再辨識。
只輸出「選區每人都讀到、號次恰為 1..n」的選區；姓名容許差一字只限同檔已有他人完全對中的同一選區、且格子文字乾淨。
