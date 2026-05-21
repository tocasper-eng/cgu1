# CGU1 - 台積電 vs 廣達 股價相關性分析

## 程式來源

Claude Chat 產生的 Python 程式

## 程式功能

分析台積電 (2330) 與廣達 (2382) 的股價關聯性，存入 SQL Server 資料庫，並以 Plotly 互動式圖表呈現。

## 專案結構

```
files/
  app.py                  # Flask web app 入口
  stock_correlation.py    # 分析核心邏輯（FinMind API + SQL Server + Plotly）
  requirements.txt        # Python 依賴
  Procfile                # Zeabur/Gunicorn 啟動指令
```

## 資料庫連線

- **Server**: 43.153.159.36,30147
- **User**: sa
- **Password**: 7TH5AIxg3N9jBcXsdJqZ4o6V82t10mpv
- **Database**: gemio
- **Tables**: `stock_prices`, `correlation_results`（程式自動建立）

使用 `pymssql`（非 pyodbc），Linux 容器免裝 ODBC Driver。

## GitHub

- **Repo**: [tocasper-eng/cgu1](https://github.com/tocasper-eng/cgu1)
- **Branch**: main

## Zeabur 部署

- **Project**: cgu1 (ID: `6a0f9052d09eb4a2f5c999d2`)
- **Service ID**: `6a0f905ff3f352d1e8d648f3`
- **Environment ID**: `6a0f9052f3b70f2a79fbdd2a`
- **URL**: https://cgu1-xk9m2p.zeabur.app
- **環境變數**: DB_SERVER, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME（已設定）

## 部署方式

```bash
# 推送程式碼後重新部署
cd files
git add -A && git commit -m "update" && git push

# 或用 Zeabur CLI 直接部署
npx zeabur deploy --project-id 6a0f9052d09eb4a2f5c999d2 --service-id 6a0f905ff3f352d1e8d648f3 -i=false
```

## 開發注意事項

- DB 連線參數透過環境變數讀取，本地開發時可設 `.env` 或直接用預設值
- `app.py` 首次訪問時自動執行分析，結果快取於記憶體
- 點「重新抓取資料」可手動更新
- FinMind API 無 token 有 rate limit，可設定 `FINMIND_TOKEN` 環境變數
