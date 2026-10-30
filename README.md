# 選舉通：線上資料

「選舉通」App 的參選人資料。App 每次開啟都會讀取這裡的 `election.json`，所以更新這個檔案就能更新所有使用者看到的名單、照片和政見，**不必重新送審 App**。

- 線上網址：`https://raw.githubusercontent.com/hsiehcaleb00114-wq/vote-tw-2026-data/main/election.json`
- GitHub 有約 5 分鐘的快取，推上去後最多等 5 分鐘才會生效
- App 只會採用 `updated` 日期**比手上更新**的資料，所以每次更新都要把 `updated` 改成當天日期

## 更新步驟

1. 編輯 `election.json`
2. 把 `updated` 改成今天（`YYYY-MM-DD`）
3. 檢查格式：`node check.mjs`
4. 看到 ✓ 才 commit 並 push

## 從中選會名冊重新匯入

目前資料（19,685 人）由三份中選會文件組成：

| 內容 | 來源 | 工具 |
|---|---|---|
| 9 類參選人姓名、選區、政黨 | 〈[115年地方公職人員選舉候選人登記名冊](https://web.cec.gov.tw/central/article/64709)〉 | `tools/import_cec.py` |
| 排除審定不合格的 10 位議員參選人 | 〈[115/10/16 審定候選人資格新聞稿](https://web.cec.gov.tw/central/article/65213)〉 | `tools/disqualified.json` |
| 議員選舉區範圍、應選名額、婦女保障名額、原住民選區 | 〈[115/8/20 選舉公告](https://web.cec.gov.tw/api/file/45d8e965-f63a-46d5-b636-7d81e47cf4d1.pdf)〉 | `tools/import_districts.py` |

11/12、11/17 正式候選人名單公告後，若格式相同可直接重跑：

1. 下載各類的「x-1 候選人登記彙總表」PDF（只要 1-1、2-1、3-1、4-1、5、6、7、8、9），檔名保留開頭編號，放進同一個資料夾
2. `pip install pdfplumber`
3. `python tools/import_cec.py <PDF資料夾> --updated YYYY-MM-DD --source "資料來源說明"`
4. 選舉區劃分有變動時才需要：`python tools/import_districts.py <選舉公告.pdf>`
5. 比對輸出的人數與 PDF，`node check.mjs` 通過後再推上來

匯入時會保留既有的人工欄位（現任、號次、照片、政見、學經歷、來源網址）與選區欄位（範圍、名額、原住民選區）。

**罕用字**：名冊中以圖片呈現、部分字無法顯示的資料，記在 `tools/manual_names.json`：

- 21 位參選人姓名，依圖片人工轉錄（○ 為無法顯示的字），App 中標示「待中選會公告確認」。正式名單公告後請逐筆核對修正。
- 3 個村里名稱（臺中市大安區龜壳里、臺南市西港區檨林里、臺南市安南區塭南里、公塭里），依現行行政區名稱補正。

## 開票結果

在 `election.json` 根層加上 `results`，並在參選人加上 `votes`（得票數）與 `elected`（是否當選）：

```jsonc
"results": { "updatedAt": "2026-11-28T18:30:00+08:00", "final": false, "source": "中選會開票資料" }
```

App 用「`updated`＋`results.updatedAt`」判斷資料新舊，開票夜每次更新都要把 `results.updatedAt` 改成當下時間（含 `+08:00`），否則 App 不會採用。中選會公告當選人名單（12/4）後把 `final` 改成 `true`。

### 號次

1. 整理成 CSV 放在 `tools/ballot_numbers/`：`office,county,district,name,number`（縣市長的 district 留空）
2. `node tools/apply_numbers.mjs tools/ballot_numbers/<檔名>.csv --source "來源"`
   - 任何一人對不到或號次重複就整批不寫入；整個選區都有號次後會依號次排序
   - 重新執行 `import_cec.py` 後號次會保留，但順序會回到登記順序，要再跑一次這個指令
3. `node check.mjs` 通過後 commit、push

目前已匯入：縣市長 81 人（`mayor.csv`，中央社 10/27 整理各縣市選委會抽籤結果，並與 TVBS 報導逐筆核對一致）。議員、鄉鎮市長、代表、村里長待各選委會公告。

### 開票夜流程

1. 取得票數，整理成 CSV：`office,county,district,name,votes,elected,reported,total`（縣市長的 district 留空；當選填 `Y`）
2. `node tools/apply_results.mjs 票數.csv --reported 已回報投開票所數 --total 總投開票所數`（最終結果加 `--final`）
   - 會自動把 `results.updatedAt` 設成現在時間；對不到參選人的列會列出來並以錯誤結束
3. `node check.mjs` 通過後 commit、push，App 約 5 分鐘內更新（GitHub 快取）

中選會即時開票的資料格式要等 2026 開票網站上線才能確認，屆時再寫轉換程式產生上面的 CSV。

### 測試用模擬資料

`node tools/simulate_results.mjs 0.35`（開票 35%，加 `--final` 為最終結果）會產生**假的**票數到 `tools/sim/`（不納入版本控制），只用來測試 App 畫面。`check.mjs` 會擋下來源標示為模擬的資料，避免誤推。

## 歷屆選舉（history/）

App「歷屆選舉」「我的地區」使用的資料，由中選會選舉資料庫（[db.cec.gov.tw](https://db.cec.gov.tw/)）的批次下載檔轉換：

1. 下載 `https://data.cec.gov.tw/選舉資料庫/votedata.zip`（約 110 MB，政府資料開放授權條款第 1 版）
2. `python tools/import_history.py votedata.zip`

| 檔案 | 內容 |
|---|---|
| `history/index.json` | 歷屆選舉清單 |
| `history/<年>.json` | 總統（全國與各縣市）、縣市長、立委與議員政黨席次 |
| `history/trends.json` | 歷屆政黨席次、得票率、投票率走勢 |
| `history/villages/<縣市>.json` | 各村里在 6 次選舉的得票率（跨村里投開票所各村里都計入） |
| `history/referendums.json` | 2018、2021 全國性公投 14 案，主文見 `tools/referendum_titles.json` |

目前涵蓋 1996–2024 總統、2008–2024 立委（單一選區兩票制後）、1997–2022 縣市長與議員（2014 年前縣市與直轄市不同年，合併為一個週期）；我的地區涵蓋 2014–2024 共 9 場。要加年份時，在 `tools/import_history.py` 的 `ELECTIONS` 加上該屆資料夾即可。2026 選後中選會更新批次檔，再重跑一次就會多一屆。

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
