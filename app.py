"""
Flask Web App - 台積電 vs 廣達 股價相關性分析
"""

import os

from flask import Flask, render_template_string

import stock_correlation as sc

app = Flask(__name__)

# 快取分析結果
_cache = {"html": None, "result": None}

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>股價相關性分析</title>
    <style>
        body { font-family: 'Microsoft JhengHei', sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { margin: 0; font-size: 1.4em; }
        .header a { color: white; background: #3498db; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-size: 0.9em; }
        .header a:hover { background: #2980b9; }
        .info { padding: 15px 40px; background: #ecf0f1; font-size: 0.9em; color: #555; }
        .chart-container { padding: 20px; }
        .error { padding: 40px; text-align: center; color: #e74c3c; font-size: 1.2em; }
    </style>
</head>
<body>
    <div class="header">
        <h1>台積電 (2330) vs 廣達 (2382) 股價相關性分析</h1>
        <a href="/refresh">重新抓取資料</a>
    </div>
    {% if result %}
    <div class="info">
        期間: {{ result.period_start }} ~ {{ result.period_end }} |
        樣本數: {{ result.sample_size }} 個交易日 |
        日報酬率相關係數: {{ "%.4f"|format(result.corr_return) }}
    </div>
    {% endif %}
    <div class="chart-container">
        {{ chart_html | safe }}
    </div>
</body>
</html>"""

ERROR_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>錯誤</title>
    <style>
        body { font-family: 'Microsoft JhengHei', sans-serif; text-align: center; padding-top: 80px; background: #f5f5f5; }
        .error { color: #e74c3c; font-size: 1.3em; margin-bottom: 20px; }
        .detail { color: #666; font-size: 0.95em; max-width: 600px; margin: 0 auto; word-break: break-all; }
        a { display: inline-block; margin-top: 30px; color: #3498db; }
    </style>
</head>
<body>
    <div class="error">分析執行失敗</div>
    <div class="detail">{{ error }}</div>
    <a href="/refresh">重試</a>
</body>
</html>"""


def _run_analysis():
    """執行分析流程並更新快取"""
    result, html = sc.run_pipeline()
    _cache["result"] = result
    _cache["html"] = html


@app.route("/")
def index():
    """首頁：顯示分析結果 (首次自動執行)"""
    if _cache["html"] is None:
        try:
            _run_analysis()
        except Exception as e:
            return render_template_string(ERROR_TEMPLATE, error=str(e)), 500

    return render_template_string(
        PAGE_TEMPLATE,
        result=_cache["result"],
        chart_html=_cache["html"],
    )


@app.route("/refresh")
def refresh():
    """重新抓取資料並分析"""
    try:
        _run_analysis()
    except Exception as e:
        return render_template_string(ERROR_TEMPLATE, error=str(e)), 500

    return render_template_string(
        PAGE_TEMPLATE,
        result=_cache["result"],
        chart_html=_cache["html"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
