"""
台積電 (2330) 與廣達 (2382) 股價相關性分析
---------------------------------------------
- 資料來源: FinMind
- 資料庫: SQL Server
- 分析: 近一年皮爾森相關係數 (基於日報酬率)
- 圖表: Plotly 互動式 HTML
"""

import os
from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
# 設定區
# ============================================================
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")
STOCKS = {
    "2330": "台積電",
    "2382": "廣達",
}

# SQL Server 連線 (從環境變數讀取)
DB_SERVER = os.getenv("DB_SERVER", "43.153.159.36")
DB_PORT = os.getenv("DB_PORT", "30147")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "7TH5AIxg3N9jBcXsdJqZ4o6V82t10mpv")
DB_NAME = os.getenv("DB_NAME", "gemio")


def get_engine() -> Engine:
    """建立 SQLAlchemy Engine (pymssql)"""
    conn_str = (
        f"mssql+pymssql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_SERVER}:{DB_PORT}/{DB_NAME}"
    )
    return create_engine(conn_str)


# ============================================================
# 1. 資料抓取
# ============================================================
def fetch_finmind(stock_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """從 FinMind 抓單一檔股票的日線資料"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if FINMIND_TOKEN:
        params["token"] = FINMIND_TOKEN

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != 200:
        raise RuntimeError(f"FinMind API 錯誤: {data}")

    df = pd.DataFrame(data["data"])
    if df.empty:
        raise RuntimeError(f"{stock_id} 沒有資料")

    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "stock_id", "open", "max", "min", "close", "Trading_Volume"]]
    df.columns = ["trade_date", "stock_id", "open_price", "high_price",
                  "low_price", "close_price", "volume"]
    return df


def fetch_all_stocks() -> pd.DataFrame:
    """抓所有股票並合併"""
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=400)).strftime("%Y-%m-%d")

    dfs: List[pd.DataFrame] = []
    for stock_id in STOCKS:
        print(f"抓取 {stock_id} {STOCKS[stock_id]} ...")
        df = fetch_finmind(stock_id, start_date, end_date)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


# ============================================================
# 2. 資料庫層
# ============================================================
DDL_PRICES = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'stock_prices')
BEGIN
    CREATE TABLE stock_prices (
        stock_id      VARCHAR(10)   NOT NULL,
        trade_date    DATE          NOT NULL,
        open_price    DECIMAL(12,2),
        high_price    DECIMAL(12,2),
        low_price     DECIMAL(12,2),
        close_price   DECIMAL(12,2),
        volume        BIGINT,
        updated_at    DATETIME      DEFAULT GETDATE(),
        CONSTRAINT PK_stock_prices PRIMARY KEY (stock_id, trade_date)
    );
END
"""

DDL_CORRELATION = """
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'correlation_results')
BEGIN
    CREATE TABLE correlation_results (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        run_time        DATETIME      NOT NULL DEFAULT GETDATE(),
        stock_a         VARCHAR(10)   NOT NULL,
        stock_b         VARCHAR(10)   NOT NULL,
        period_start    DATE          NOT NULL,
        period_end      DATE          NOT NULL,
        corr_price      DECIMAL(8,5),
        corr_return     DECIMAL(8,5),
        sample_size     INT,
        note            NVARCHAR(200)
    );
END
"""


def init_db(engine: Engine) -> None:
    """建立資料表"""
    with engine.begin() as conn:
        conn.execute(text(DDL_PRICES))
        conn.execute(text(DDL_CORRELATION))
    print("資料表已就緒")


def upsert_prices(engine: Engine, df: pd.DataFrame) -> None:
    """UPSERT 股價資料 (使用 MERGE)"""
    with engine.begin() as conn:
        conn.execute(text("""
            IF OBJECT_ID('tempdb..#stock_prices_staging') IS NOT NULL
                DROP TABLE #stock_prices_staging
        """))
        conn.execute(text("""
            CREATE TABLE #stock_prices_staging (
                stock_id    VARCHAR(10),
                trade_date  DATE,
                open_price  DECIMAL(12,2),
                high_price  DECIMAL(12,2),
                low_price   DECIMAL(12,2),
                close_price DECIMAL(12,2),
                volume      BIGINT
            )
        """))

        df.to_sql("#stock_prices_staging", conn, if_exists="append", index=False)

        conn.execute(text("""
            MERGE stock_prices AS tgt
            USING #stock_prices_staging AS src
            ON tgt.stock_id = src.stock_id AND tgt.trade_date = src.trade_date
            WHEN MATCHED THEN UPDATE SET
                open_price  = src.open_price,
                high_price  = src.high_price,
                low_price   = src.low_price,
                close_price = src.close_price,
                volume      = src.volume,
                updated_at  = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (stock_id, trade_date, open_price, high_price,
                        low_price, close_price, volume)
                VALUES (src.stock_id, src.trade_date, src.open_price,
                        src.high_price, src.low_price, src.close_price, src.volume);
        """))
    print(f"已 UPSERT {len(df)} 筆股價資料")


def save_correlation(engine: Engine, result: dict) -> None:
    """寫入相關性分析結果"""
    sql = text("""
        INSERT INTO correlation_results
            (stock_a, stock_b, period_start, period_end,
             corr_price, corr_return, sample_size, note)
        VALUES
            (:stock_a, :stock_b, :period_start, :period_end,
             :corr_price, :corr_return, :sample_size, :note)
    """)
    with engine.begin() as conn:
        conn.execute(sql, result)
    print("已寫入分析結果")


# ============================================================
# 3. 分析層
# ============================================================
def analyze_correlation(df: pd.DataFrame) -> tuple:
    """計算兩檔股票的相關性"""
    pivot = df.pivot(index="trade_date", columns="stock_id", values="close_price").sort_index()

    one_year_ago = pivot.index.max() - pd.Timedelta(days=365)
    pivot = pivot.loc[pivot.index >= one_year_ago]
    pivot = pivot.dropna()

    returns = pivot.pct_change().dropna()

    stock_a, stock_b = list(STOCKS.keys())

    corr_price = pivot[stock_a].corr(pivot[stock_b])
    corr_return = returns[stock_a].corr(returns[stock_b])

    result = {
        "stock_a": stock_a,
        "stock_b": stock_b,
        "period_start": pivot.index.min().date(),
        "period_end": pivot.index.max().date(),
        "corr_price": round(float(corr_price), 5),
        "corr_return": round(float(corr_return), 5),
        "sample_size": len(returns),
        "note": f"{STOCKS[stock_a]} vs {STOCKS[stock_b]} 近一年",
    }

    print("\n=== 分析結果 ===")
    print(f"期間: {result['period_start']} ~ {result['period_end']}")
    print(f"樣本數: {result['sample_size']} 個交易日")
    print(f"收盤價相關係數: {result['corr_price']:.4f}  (僅供參考)")
    print(f"日報酬率相關係數: {result['corr_return']:.4f}  ← 主要指標")
    print("================\n")

    return result, pivot, returns


# ============================================================
# 4. 視覺化層
# ============================================================
def make_chart(pivot: pd.DataFrame, returns: pd.DataFrame, result: dict) -> str:
    """產生互動式 HTML 圖表，回傳 HTML 字串"""
    stock_a, stock_b = result["stock_a"], result["stock_b"]
    name_a, name_b = STOCKS[stock_a], STOCKS[stock_b]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            f"收盤價走勢 (雙軸)",
            f"日報酬率散佈圖 (相關係數 = {result['corr_return']:.4f})",
            f"日報酬率時間序列",
            "標準化股價走勢 (起始=100)",
        ),
        specs=[
            [{"secondary_y": True}, {}],
            [{}, {}],
        ],
        vertical_spacing=0.13,
        horizontal_spacing=0.10,
    )

    # 左上: 雙軸收盤價
    fig.add_trace(
        go.Scatter(x=pivot.index, y=pivot[stock_a], name=f"{name_a} ({stock_a})",
                   line=dict(color="#E74C3C")),
        row=1, col=1, secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=pivot.index, y=pivot[stock_b], name=f"{name_b} ({stock_b})",
                   line=dict(color="#3498DB")),
        row=1, col=1, secondary_y=True,
    )

    # 右上: 散佈圖 + 迴歸線
    fig.add_trace(
        go.Scatter(x=returns[stock_a], y=returns[stock_b],
                   mode="markers", name="日報酬率",
                   marker=dict(color="#9B59B6", size=6, opacity=0.6),
                   showlegend=False),
        row=1, col=2,
    )
    x = returns[stock_a].values
    y = returns[stock_b].values
    slope, intercept = np.polyfit(x, y, 1)
    x_line = np.array([x.min(), x.max()])
    fig.add_trace(
        go.Scatter(x=x_line, y=slope * x_line + intercept,
                   mode="lines", line=dict(color="black", dash="dash"),
                   name=f"迴歸線 (β={slope:.2f})", showlegend=False),
        row=1, col=2,
    )

    # 左下: 日報酬率時間序列
    fig.add_trace(
        go.Scatter(x=returns.index, y=returns[stock_a] * 100,
                   name=f"{name_a} 報酬%", line=dict(color="#E74C3C", width=1)),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(x=returns.index, y=returns[stock_b] * 100,
                   name=f"{name_b} 報酬%", line=dict(color="#3498DB", width=1)),
        row=2, col=1,
    )

    # 右下: 標準化股價
    normalized = pivot / pivot.iloc[0] * 100
    fig.add_trace(
        go.Scatter(x=normalized.index, y=normalized[stock_a],
                   name=f"{name_a} 標準化", line=dict(color="#E74C3C"),
                   showlegend=False),
        row=2, col=2,
    )
    fig.add_trace(
        go.Scatter(x=normalized.index, y=normalized[stock_b],
                   name=f"{name_b} 標準化", line=dict(color="#3498DB"),
                   showlegend=False),
        row=2, col=2,
    )

    # 軸標籤
    fig.update_yaxes(title_text=f"{name_a} 收盤價 (元)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text=f"{name_b} 收盤價 (元)", row=1, col=1, secondary_y=True)
    fig.update_xaxes(title_text=f"{name_a} 日報酬率", row=1, col=2)
    fig.update_yaxes(title_text=f"{name_b} 日報酬率", row=1, col=2)
    fig.update_yaxes(title_text="報酬率 (%)", row=2, col=1)
    fig.update_yaxes(title_text="標準化價格", row=2, col=2)

    fig.update_layout(
        title=dict(
            text=f"<b>{name_a} ({stock_a}) vs {name_b} ({stock_b}) 股價相關性分析</b><br>"
                 f"<sub>期間: {result['period_start']} ~ {result['period_end']}  |  "
                 f"樣本數: {result['sample_size']} 個交易日  |  "
                 f"日報酬率相關係數: {result['corr_return']:.4f}</sub>",
            x=0.5, xanchor="center",
        ),
        height=850,
        hovermode="x unified",
        template="plotly_white",
    )

    return fig.to_html(include_plotlyjs="cdn")


# ============================================================
# 主流程 (供直接執行)
# ============================================================
def run_pipeline():
    """執行完整流程，回傳 (result, html)"""
    df = fetch_all_stocks()
    print(f"共抓取 {len(df)} 筆資料\n")

    engine = get_engine()
    init_db(engine)
    upsert_prices(engine, df)

    result, pivot, returns = analyze_correlation(df)
    save_correlation(engine, result)

    html = make_chart(pivot, returns, result)
    return result, html


if __name__ == "__main__":
    result, html = run_pipeline()
    with open("stock_correlation_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("圖表已輸出: stock_correlation_report.html")
    print("\n完成！")
