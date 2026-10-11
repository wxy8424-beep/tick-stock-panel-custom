"""行情状态 / SSE 推送 API。

盘中选股相关端点已迁移至策略页面，此处仅保留全局行情基础设施。
SSE 推送四种事件 (使用标准 SSE event 字段):
  - quotes_updated: 行情数据刷新，前端 invalidate 对应 query
  - strategy_results_updated: 策略监控已写入最新结果，前端刷新策略个股列表
  - strategy_alert: 策略监控/告警触发，前端弹通知
  - depth_updated: 五档盘口修正完成，前端刷新连板梯队/看板封单数据
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/intraday", tags=["quotes"])


def _get_quote_service(request: Request):
    """获取全局 QuoteService。"""
    return getattr(request.app.state, "quote_service", None)


def _fallback_index_quotes_from_daily(request: Request, symbols: list[str] | None = None) -> list[dict]:
    """实时指数缓存为空时，从本地指数日 K 取最近收盘价作为兜底。"""
    repo = getattr(request.app.state, "repo", None)
    if not repo:
        return []

    params: list[str] = []
    symbol_filter = ""
    if symbols:
        placeholders = ", ".join("?" for _ in symbols)
        symbol_filter = f"WHERE symbol IN ({placeholders})"
        params.extend(symbols)

    try:
        rows = repo.execute_all(
            f"""
            WITH ranked AS (
                SELECT symbol, date, close,
                       row_number() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                FROM kline_index_daily
                {symbol_filter}
            ), latest AS (
                SELECT symbol,
                       max(CASE WHEN rn = 1 THEN date END) AS date,
                       max(CASE WHEN rn = 1 THEN close END) AS last_price,
                       max(CASE WHEN rn = 2 THEN close END) AS prev_close
                FROM ranked
                WHERE rn <= 2
                GROUP BY symbol
            )
            SELECT latest.symbol, latest.date, latest.last_price, latest.prev_close
            FROM latest
            ORDER BY latest.symbol
            """,
            params,
        )
    except Exception:  # noqa: BLE001
        return []

    out: list[dict] = []
    for symbol, dt, last_price, prev_close in rows:
        change_amount = None
        change_pct = None
        if last_price is not None and prev_close not in (None, 0):
            change_amount = float(last_price) - float(prev_close)
            change_pct = change_amount / float(prev_close) * 100
        out.append({
            "symbol": symbol,
            "name": None,
            "date": str(dt) if dt else None,
            "last_price": float(last_price) if last_price is not None else None,
            "close": float(last_price) if last_price is not None else None,
            "prev_close": float(prev_close) if prev_close is not None else None,
            "change_amount": change_amount,
            "change_pct": change_pct,
            "source": "index_daily",
        })
    return out


@router.get("/status")
def status(request: Request):
    """行情状态 (来自全局 QuoteService)。"""
    qs = _get_quote_service(request)
    if qs:
        return qs.status()
    return {"enabled": False, "running": False, "symbol_count": 0, "index_symbol_count": 0,
            "quote_age_ms": None, "is_trading_hours": False, "last_fetch_ms": None}


@router.get("/indices")
def index_quotes(
    request: Request,
    symbols: str | None = Query(None, description="逗号分隔的指数 symbol 列表"),
):
    """返回实时指数行情缓存，不触发 TickFlow 请求。"""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    qs = _get_quote_service(request)
    if not qs:
        rows = _fallback_index_quotes_from_daily(request, symbol_list)
        return {"rows": rows, "count": len(rows), "source": "index_daily"}
    df = qs.get_index_quotes(symbol_list)
    rows = df.to_dicts() if not df.is_empty() else []
    if not rows:
        rows = _fallback_index_quotes_from_daily(request, symbol_list)
        return {"rows": rows, "count": len(rows), "source": "index_daily"}
    return {"rows": rows, "count": len(rows), "source": "realtime"}


@router.get("/quotes")
def quote_snapshots(
    request: Request,
    symbols: str | None = Query(None, description="逗号分隔的完整 symbol; 只读缓存, 不请求数据源"),
):
    """基础行情读取: CN 保持兼容报价字段, HK/US 不依赖 enriched。

    港美无指标、量单位未支持; age_ms 来自行情戳, 不代表市场是否开市。
    """
    qs = _get_quote_service(request)
    rows = []
    if qs:
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
        if symbol_list is None or any(s.endswith((".SH", ".SZ", ".BJ")) for s in symbol_list):
            df = qs.get_quotes_compat()
            rows = df.to_dicts() if not df.is_empty() else []
            if symbol_list is not None:
                wanted = set(symbol_list)
                rows = [row for row in rows if row["symbol"] in wanted]
        rows.extend(qs.get_non_cn_quotes(symbol_list))
    return {"rows": rows, "count": len(rows)}


def _read_snapshot_archive(request: Request, **filters) -> list[dict]:
    from app.services.snapshot_archive import SnapshotArchive

    repo = getattr(request.app.state, "repo", None)
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:
        return []
    try:
        return SnapshotArchive(data_dir).query(**filters)
    except Exception:
        raise HTTPException(503, "快照归档暂不可读") from None


@router.get("/snapshots/recent")
def archived_snapshots(
    request: Request,
    symbol: str | None = Query(None, max_length=128),
    market: Literal["CN", "HK", "US"] | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """最近收到的逐证券快照; 只读 SQLite, 不请求 Provider。"""
    rows = _read_snapshot_archive(request, symbol=symbol, market=market, limit=limit, latest=True)
    return {"rows": rows, "count": len(rows)}


@router.get("/snapshots/quality")
def archived_quality(
    request: Request,
    symbol: str | None = Query(None, max_length=128),
    market: Literal["CN", "HK", "US"] | None = None,
    limit: int = Query(100, ge=1, le=1000),
    before_id: int | None = Query(None, ge=1),
):
    """逐条历史质量记录, 按入库ID倒序分页; 含原快照与两个时钟。"""
    rows = _read_snapshot_archive(request, symbol=symbol, market=market, limit=limit, before_id=before_id)
    return {"rows": rows, "count": len(rows)}


@router.get("/stream")
async def quote_stream(request: Request):
    """SSE 端点: 行情更新 + 告警推送 + 五档修正 + 复盘进度。

    使用 sse-starlette EventSourceResponse:
    - 标准 SSE event 字段，前端按 event name 监听
    - 内置断线检测，客户端断开立即终止 generator
    - 内置 ping 心跳，保持连接活跃

    每个连接注册一个独立订阅者 (QuoteSubscriber: 独立事件 + 独立队列),
    事件由 QuoteService 广播 — 多客户端 (多标签页/设备) 各自收到全量事件。
    此前四通道共用服务级 Event + pop 取走语义, 告警只会被先醒的连接消费。
    """
    qs = _get_quote_service(request)

    async def event_generator():
        if qs is None:
            # 无行情服务: 保持连接 (EventSourceResponse 自带 ping), 不推事件
            while True:
                await asyncio.sleep(30)

        sub = qs.subscribe()
        try:
            while True:
                # 等待任一通道有新信号 (5s 超时保持循环, 便于断线时尽快退出)
                await asyncio.to_thread(sub.wait, 5.0)
                data = sub.pop()

                # 告警 (分片推送, 避免单条 SSE 过大)
                alerts = data["alerts"]
                for chunk_start in range(0, len(alerts), 20):
                    chunk = alerts[chunk_start:chunk_start + 20]
                    yield {
                        "event": "strategy_alert",
                        "data": json.dumps({
                            "ts": int(time.time() * 1000),
                            "alerts": chunk,
                        }, ensure_ascii=False),
                    }

                # 复盘进度 (定时复盘流式生成时) — 前端 reviewStore 直接消费
                # 事件已是 recap_market_stream 产出的 JSON 字符串, 逐条转发
                for evt_json in data["reviews"]:
                    yield {
                        "event": "review_progress",
                        "data": evt_json,
                    }

                # 行情更新
                if data["quote_updated"]:
                    yield {
                        "event": "quotes_updated",
                        "data": json.dumps({
                            "ts": int(time.time() * 1000),
                            "symbol_count": qs._symbol_count,
                        }),
                    }

                # 策略监控完成后, 结果已写入内存缓存; 独立通知只刷新策略个股列表。
                if data["strategy_results_updated"]:
                    yield {
                        "event": "strategy_results_updated",
                        "data": json.dumps({"ts": int(time.time() * 1000)}),
                    }

                # 五档修正完成 — 前端刷新连板梯队封单数据
                if data["depth_updated"]:
                    yield {
                        "event": "depth_updated",
                        "data": json.dumps({
                            "ts": int(time.time() * 1000),
                        }),
                    }
        finally:
            qs.unsubscribe(sub)

    return EventSourceResponse(event_generator())


@router.post("/refresh")
def refresh_quotes(request: Request):
    """手动刷新一次行情数据。"""
    qs = _get_quote_service(request)
    if qs:
        return qs.refresh()
    return {"error": "QuoteService not available"}
