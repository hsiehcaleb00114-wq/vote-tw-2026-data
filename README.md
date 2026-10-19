# 九合一投票通：線上資料

「九合一投票通」App 的參選人資料。App 每次開啟都會讀取這裡的 `election.json`，所以更新這個檔案就能更新所有使用者看到的名單、照片和政見，**不必重新送審 App**。

- 線上網址：`https://raw.githubusercontent.com/hsiehcaleb00114-wq/vote-tw-2026-data/main/election.json`
- GitHub 有約 5 分鐘的快取，推上去後最多等 5 分鐘才會生效
- App 只會採用 `updated` 日期**比手上更新**的資料，所以每次更新都要把 `updated` 改成當天日期

## 更新步驟

1. 編輯 `election.json`
2. 把 `updated` 改成今天（`YYYY-MM-DD`）
3. 檢查格式：`node check.mjs`
4. 看到 ✓ 才 commit 並 push

## 從中選會名冊重新匯入

目前資料來自中選會〈[115年地方公職人員選舉候選人登記名冊](https://web.cec.gov.tw/central/article/64709)〉，共 9 類、19,695 人。11/12、11/17 正式候選人名單公告後，若格式相同可直接重跑：

1. 下載各類的「x-1 候選人登記彙總表」PDF（只要 1-1、2-1、3-1、4-1、5、6、7、8、9），檔名保留開頭編號，放進同一個資料夾
2. `pip install pdfplumber`
3. `python tools/import_cec.py <PDF資料夾> --updated YYYY-MM-DD`
4. 比對輸出的人數與 PDF，`node check.mjs` 通過後再推上來

匯入時會保留既有的人工欄位（現任、號次、照片、政見、學經歷、來源網址）。

**罕用字姓名**：名冊中有 21 位參選人的姓名含罕用字，PDF 以圖片呈現且部分字無法顯示，已依圖片人工轉錄在 `tools/manual_names.json`（○ 為無法顯示的字），並在 App 中標示「待中選會公告確認」。正式名單公告後請逐筆核對修正。

## 格式

```jsonc
{
  "version": 1,
  "updated": "2026-11-17",
  "source": "中選會「115年地方公職人員選舉候選人登記名冊」", // 選填：顯示在 App 參選人頁底部
  "races": [
    {
      "office": "council",          // mayor 縣市長｜council 縣市議員｜township 鄉鎮市長｜township_rep 鄉鎮市民代表｜village 村里長
      "county": "臺北市",            // 用「臺」不是「台」
      "district": "第 1 選舉區",     // 縣市長不用填，其他職位必填
      "area": "北投區、士林區",       // 選填：選區範圍
      "seats": 12,                   // 選填：應選名額
      "candidates": [
        {
          "name": "王小明",
          "party": "無黨籍",
          "number": 3,               // 選填：號次
          "incumbent": true,         // 選填：現任
          "photo": "https://...",    // 選填：大頭貼，必須是 https
          "photoCredit": "中選會選舉公報", // 有照片時必填
          "education": ["..."],      // 選填：學歷
          "experience": ["..."],     // 選填：經歷
          "platform": ["..."],       // 選填：政見，依選舉公報原文逐條
          "sourceUrl": "https://..." // 選填：原始資料（選舉公報）
        }
      ]
    }
  ]
}
```

## 資料來源與原則

- 正式候選人與號次：中選會公告（直轄市長 11/12、其餘 11/17）
- 政見、學經歷、照片：中選會選舉公報，原文照錄、不改寫不評論
- 照片一律註明來源；沒有可用的照片就不放，App 會顯示姓名首字
- 本資料為民間整理，非中選會官方資料
