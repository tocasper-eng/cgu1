---
name: deploy-to-zeabur
description: Use when deploying a Python web app to Zeabur, converting a script to a Flask web service, or setting up Zeabur CLI deployment with environment variables and domain configuration
---

# Deploy Python App to Zeabur

## Overview

將 Python 程式（腳本或分析工具）轉換為 Flask web app，透過 Zeabur CLI 部署上線。涵蓋程式改造、Git 推送、Zeabur 建立專案/服務/環境變數/網域的完整流程。

## When to Use

- 需要將 Python 腳本部署為 web 服務
- 要把資料分析程式上線讓人透過瀏覽器查看
- 使用 Zeabur 平台部署 Python 專案

## Quick Reference

| 步驟 | 指令/工具 | 說明 |
|------|----------|------|
| 登入 | `npx zeabur auth login` | 瀏覽器授權登入 |
| 建專案 | `npx zeabur project create --name NAME --region REGION -i=false --json` | 非互動建立 |
| 部署 | `npx zeabur deploy --create --name NAME --project-id ID -i=false` | 上傳並建立服務 |
| 環境變數 | `npx zeabur variable create --id SVC_ID --env-id ENV_ID -k KEY=VAL -y -i=false` | 設定多個變數 |
| 網域 | `npx zeabur domain create --id SVC_ID --env-id ENV_ID -g --domain SUBDOMAIN -y -i=false` | 產生 .zeabur.app 網域 |
| 查狀態 | `npx zeabur deployment list --service-id SVC_ID --env-id ENV_ID -i=false --json` | 狀態: BUILDING → DEPLOYING → RUNNING |
| 查日誌 | `npx zeabur deployment log --service-id SVC_ID --env-id ENV_ID -i=false` | Runtime logs |

## Core Pattern: Script to Flask Web App

### 1. 程式改造

**DB 連線改用環境變數 + pymssql（取代 pyodbc，免裝 ODBC Driver）：**

```python
import os
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "mydb")

def get_engine():
    conn_str = f"mssql+pymssql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"
    return create_engine(conn_str)
```

**核心邏輯封裝為可呼叫函式，圖表回傳 HTML 字串：**

```python
def run_pipeline():
    # ... 業務邏輯 ...
    html = fig.to_html(include_plotlyjs="cdn")  # 不寫檔，回傳字串
    return result, html
```

### 2. Flask 入口 (app.py)

```python
import os
from flask import Flask, render_template_string
import my_module as m

app = Flask(__name__)
_cache = {"html": None, "result": None}

@app.route("/")
def index():
    if _cache["html"] is None:
        result, html = m.run_pipeline()
        _cache["result"], _cache["html"] = result, html
    return _cache["html"]

@app.route("/refresh")
def refresh():
    result, html = m.run_pipeline()
    _cache["result"], _cache["html"] = result, html
    return _cache["html"]

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
```

### 3. 部署檔案

**requirements.txt** — 加入 `flask`, `gunicorn`, `pymssql`（移除 `pyodbc`）

**Procfile:**
```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

**.gitignore:**
```
__pycache__/
*.pyc
.env
venv/
```

### 4. Zeabur CLI 部署流程

```bash
# 登入
npx zeabur auth login

# 建立專案（取得 project ID）
npx zeabur project create --name myapp --region SERVER_REGION -i=false --json

# 部署（取得 service ID 和 environment ID）
cd /project/dir
npx zeabur deploy --create --name myapp --project-id PROJECT_ID -i=false

# 設環境變數
npx zeabur variable create \
  --id SERVICE_ID --env-id ENV_ID \
  -k DB_SERVER=x.x.x.x -k DB_PORT=1433 \
  -k DB_USER=sa -k "DB_PASSWORD=xxx" \
  -k DB_NAME=mydb -y -i=false

# 產生網域（-g 為 generated，需搭配 --domain 指定子網域名）
npx zeabur domain create \
  --id SERVICE_ID --env-id ENV_ID \
  -g --domain my-unique-name -y -i=false
# 結果: my-unique-name.zeabur.app
```

## Common Mistakes

| 問題 | 解法 |
|------|------|
| 互動模式在 CLI 環境失敗 | 所有指令加 `-i=false`，用 `--json` 取 ID |
| Linux 容器缺 ODBC Driver | 用 `pymssql` 取代 `pyodbc`，不需額外安裝 |
| `zeabur domain create -g` 失敗 | 必須同時加 `--domain SUBDOMAIN`，不能只用 `-g` |
| `.zeabur.app` 網域被佔用 | 換更獨特的子網域名稱 |
| 部署後無法連 DB | 確認環境變數已設定，確認 DB 防火牆允許 Zeabur IP |
| Plotly 圖表寫檔而非回傳 | 改用 `fig.to_html()` 回傳字串，由 Flask 直接 return |

## ID 取得方式

部署完成後，Zeabur 回傳的 URL 包含所有 ID：
```
https://zeabur.com/projects/PROJECT_ID/services/SERVICE_ID?envID=ENV_ID
```

也可用 `--json` 取得：
```bash
npx zeabur project list --json    # 取 project ID
npx zeabur deployment list --service-id SVC --env-id ENV --json  # 查部署狀態
```
