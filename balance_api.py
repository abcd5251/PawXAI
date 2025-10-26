import json
from decimal import Decimal, getcontext
from datetime import datetime
from typing import List, Dict, Any, Optional


import httpx
from fastapi import FastAPI, HTTPException
from models.model import OpenAIModel
from prompts.readable import READABLE_PROMPT
from prompts.readable_transactions import readable_transac_prompt
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# High precision for ETH/wei conversions
getcontext().prec = 50

app = FastAPI(title="Balance History Formatter API")

class BalanceHistoryRequest(BaseModel):
    chain_id: str = Field(..., description="Chain ID, e.g., 8453 for Base")
    address: str = Field(..., description="Account address, e.g., 0x...")

def wei_to_eth(wei_int: int) -> Decimal:
    return Decimal(wei_int) / Decimal(10**18)

def fmt_eth(d: Decimal) -> str:
    return f"{d:.8f}".rstrip("0").rstrip(".")

def fmt_wei(n: int) -> str:
    return f"{n:,}"

def short_hash(tx_hash: str) -> str:
    if not tx_hash or len(tx_hash) < 10:
        return tx_hash or ""
    return f"{tx_hash[:10]}…{tx_hash[-8:]}"

def short_addr(addr: str) -> str:
    if not addr or len(addr) < 10:
        return addr or ""
    return f"{addr[:6]}…{addr[-4:]}"

def parse_iso_utc(ts: str) -> str:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

def _add_if(params: Dict[str, str], key: str, value: Optional[str]) -> None:
    if value is not None:
        v = str(value).strip()
        if v:
            params[key] = v

def format_balance_history_items(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No balance change data found."

    # Sort chronologically (oldest → newest)
    items = sorted(items, key=lambda x: x.get("block_timestamp", ""))

    start_ts = parse_iso_utc(items[0]["block_timestamp"])
    end_ts = parse_iso_utc(items[-1]["block_timestamp"])

    total_income_wei = 0
    total_spend_wei = 0

    lines = []
    header = [
        f"Count: {len(items)}",
        f"Period: {start_ts} → {end_ts}",
        "Notes: Positive delta = income, negative delta = expense; balance unit is ETH (Base/Ethereum native coin).",
        ""
    ]
    lines.extend(header)

    for it in items:
        block = it.get("block_number")
        ts = parse_iso_utc(it.get("block_timestamp", ""))
        txh = it.get("transaction_hash", "")
        delta_wei = int(it.get("delta", "0"))
        value_wei = int(it.get("value", "0"))

        delta_eth = wei_to_eth(delta_wei)
        value_eth = wei_to_eth(value_wei)

        direction = "Income" if delta_wei > 0 else ("Expense" if delta_wei < 0 else "No change")
        if delta_wei > 0:
            total_income_wei += delta_wei
        elif delta_wei < 0:
            total_spend_wei += -delta_wei

        line = (
            f"{ts} | Block {block} | Tx {short_hash(txh)} | "
            f"{direction} {fmt_eth(abs(delta_eth))} ETH "
            f"({fmt_wei(abs(delta_wei))} wei) | New balance {fmt_eth(value_eth)} ETH"
        )
        lines.append(line)

    net_wei = total_income_wei - total_spend_wei
    net_eth = wei_to_eth(net_wei)

    summary = [
        "",
        f"Total income: {fmt_eth(wei_to_eth(total_income_wei))} ETH ({fmt_wei(total_income_wei)} wei)",
        f"Total expense: {fmt_eth(wei_to_eth(total_spend_wei))} ETH ({fmt_wei(total_spend_wei)} wei)",
        f"Net change: {fmt_eth(net_eth)} ETH ({fmt_wei(net_wei)} wei)"
    ]
    lines.extend(summary)

    return "\n".join(lines)

@app.post("/format-balance-history", response_class=PlainTextResponse)
async def format_balance_history(req: BalanceHistoryRequest) -> PlainTextResponse:
    """
    POST JSON body: {"chain_id": "<CHAIN_ID>", "address": "<ADDR>"}
    Calls local /v1/direct_api_call with coin-balance-history and returns human-readable text.
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "endpoint_path": f"/api/v2/addresses/{req.address.strip()}/coin-balance-history",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "http://127.0.0.1:8000/v1/direct_api_call",
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse upstream response: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    items = (payload.get("data") or {}).get("items", []) or []
    human_text = format_balance_history_items(items)
    return PlainTextResponse(content=human_text, status_code=200)

@app.post("/address-info")
async def address_info(req: BalanceHistoryRequest):
    """
    POST JSON: {"chain_id": "<CHAIN_ID>", "address": "<ADDR>"}
    Proxy to /v1/get_address_info
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "address": req.address.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/get_address_info", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)

class TransactionsRequest(BaseModel):
    chain_id: str
    address: str

@app.post("/transactions", response_class=PlainTextResponse)
async def transactions(req: TransactionsRequest):
    """
    POST JSON: {"chain_id": "...", "address": "..."}
    Proxy to /v1/get_transactions_by_address and return human-readable text.
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "address": req.address.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/get_transactions_by_address", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse upstream response: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    # Extract a list of items robustly
    data_obj = payload.get("data", payload)
    if isinstance(data_obj, dict):
        items = data_obj.get("items") or data_obj.get("data") or data_obj.get("transactions") or []
    elif isinstance(data_obj, list):
        items = data_obj
    else:
        items = []

    # Prefer LLM-rendered text; fall back to rule-based summary
    try:
        llm = OpenAIModel(system_prompt=readable_transac_prompt, temperature=0)
        content = json.dumps({"address": req.address, "data": items}, ensure_ascii=False)
        prompt = f"transfers_snapshot:{content}\nOUTPUT:"
        text, _, _ = llm.generate_string_text(prompt)
        return PlainTextResponse(text)
    except Exception:
        return PlainTextResponse(_render_transactions_fallback_text(items))

class TokenTransfersRequest(BaseModel):
    chain_id: str
    address: str

@app.post("/token-transfers")
async def token_transfers(req: TokenTransfersRequest):
    """
    POST JSON: {"chain_id": "...", "address": "...", "age_from": "...", "age_to": "...", "token": "0x..."}
    Proxy to /v1/get_token_transfers_by_address
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "address": req.address.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/get_token_transfers_by_address", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)

class TokensByAddressRequest(BaseModel):
    chain_id: str
    address: str

@app.post("/tokens", response_class=PlainTextResponse)
async def tokens(req: TokensByAddressRequest) -> PlainTextResponse:
    """
    POST JSON: {"chain_id": "...", "address": "..."}
    Proxy to /v1/get_tokens_by_address
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "address": req.address.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/get_tokens_by_address", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    data_obj = payload.get("data", payload)
    if isinstance(data_obj, dict):
        tokens_raw = data_obj.get("items") or data_obj.get("data") or []
    elif isinstance(data_obj, list):
        tokens_raw = data_obj
    else:
        tokens_raw = []

    doc = _compute_doc(tokens_raw)

    # Prefer LLM-rendered text; fall back to rule-based summary
    try:
        llm = OpenAIModel(system_prompt=READABLE_PROMPT, temperature=0)
        content = json.dumps(doc, ensure_ascii=False)
        prompt = f"tokens_snapshot:{content}\nOUTPUT:"
        text, _, _ = llm.generate_string_text(prompt)
        return PlainTextResponse(text)
    except Exception:
        return PlainTextResponse(_render_fallback_text(doc))

class TransactionSummaryRequest(BaseModel):
    chain_id: str
    transaction_hash: str

@app.post("/transaction-summary")
async def transaction_summary(req: TransactionSummaryRequest):
    """
    POST JSON: {"chain_id": "...", "transaction_hash": "0x..."}
    Proxy to /v1/transaction_summary
    """
    params = {
        "chain_id": req.chain_id.strip(),
        "transaction_hash": req.transaction_hash.strip(),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/transaction_summary", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)

class LatestBlockRequest(BaseModel):
    chain_id: str

@app.post("/latest-block")
async def latest_block(req: LatestBlockRequest):
    """
    POST JSON: {"chain_id": "..."}
    Proxy to /v1/get_latest_block
    """
    params = {"chain_id": req.chain_id.strip()}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("http://127.0.0.1:8000/v1/get_latest_block", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"Upstream error: {e.response.status_code}: {e.response.text}"
        raise HTTPException(status_code=502, detail=detail)

class TokensReadableRequest(BaseModel):
    chain_id: Optional[str] = None
    address: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    use_llm: Optional[bool] = True  


def _to_decimal(x: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(x))
    except Exception:
        return None

def _has_non_ascii(s: Optional[str]) -> bool:
    if not s:
        return False
    return any(ord(ch) > 127 for ch in s)

def _fmt_amount(d: Decimal) -> str:
    s = f"{d:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"

def _fmt_usd(d: Decimal) -> str:
    return f"{d:.2f}"

def _compute_doc(tokens_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    total_usd = Decimal("0")
    priced_count = 0
    no_price_symbols: List[str] = []
    suspicious_symbols: List[str] = []
    stable_symbols = {"USDC", "USDT", "DAI", "LUSD", "FRAX", "USD+"}

    for tk in tokens_raw:
        symbol = tk.get("symbol") or ""
        name = tk.get("name") or ""
        decimals_str = tk.get("decimals")
        balance_str = tk.get("balance")
        price_str = tk.get("exchange_rate")

        try:
            decimals = int(decimals_str) if decimals_str is not None else 18
        except Exception:
            decimals = 18
        try:
            balance_int = int(str(balance_str)) if balance_str is not None else 0
        except Exception:
            balance_int = 0

        amount = Decimal(balance_int) / Decimal(10 ** decimals)

        price = _to_decimal(price_str)
        usd_value = None
        if price is not None:
            usd_value = amount * price
            priced_count += 1
            total_usd += usd_value
        else:
            no_price_symbols.append(symbol or name or "(unknown)")

        if _has_non_ascii(symbol) or _has_non_ascii(name):
            suspicious_symbols.append(symbol or name or "(unknown)")

        items.append({
            "symbol": symbol,
            "name": name,
            "amount": str(amount),         
            "amount_fmt": _fmt_amount(amount),
            "usd_value": str(usd_value) if usd_value is not None else None,
            "usd_value_fmt": _fmt_usd(usd_value) if usd_value is not None else None,
            "is_stable": (symbol.upper() in stable_symbols),
            "decimals": decimals,
            "price": str(price) if price is not None else None,
        })

    priced_items = [it for it in items if it["usd_value"] is not None]
    priced_items_sorted = sorted(priced_items, key=lambda x: Decimal(x["usd_value"]), reverse=True)

    top1 = priced_items_sorted[0] if priced_items_sorted else None
    top3 = priced_items_sorted[:3]
    top1_usd = Decimal(top1["usd_value"]) if top1 else Decimal("0")
    top3_usd = sum(Decimal(it["usd_value"]) for it in top3) if top3 else Decimal("0")
    top1_pct = (top1_usd / total_usd * Decimal("100")) if total_usd > 0 else Decimal("0")
    top3_pct = (top3_usd / total_usd * Decimal("100")) if total_usd > 0 else Decimal("0")

    doc = {
        "stats": {
            "tokens_count": len(items),
            "priced_count": priced_count,
            "total_usd": str(total_usd),
            "total_usd_fmt": _fmt_usd(total_usd),
            "top1_pct": f"{top1_pct:.1f}",
            "top3_pct": f"{top3_pct:.1f}",
        },
        "top5": [
            {
                "symbol": it["symbol"],
                "amount_fmt": it["amount_fmt"],
                "usd_value_fmt": it["usd_value_fmt"],
            }
            for it in priced_items_sorted[:5]
        ],
        "stable_holdings": [
            {"symbol": it["symbol"], "amount_fmt": it["amount_fmt"], "usd_value_fmt": it["usd_value_fmt"]}
            for it in items if it["is_stable"]
        ],
        "no_price": list(set(no_price_symbols)),
        "suspicious": list(set(suspicious_symbols)),
        "items": items,
    }
    return doc

def _render_fallback_text(doc: Dict[str, Any]) -> str:
    s = doc["stats"]
    lines = []
    lines.append(f"Tokens held: {s['tokens_count']}, priced tokens: {s['priced_count']}, total estimated value ≈${s['total_usd_fmt']}")
    lines.append(f"Concentration: Top1 {s['top1_pct']}%, Top3 combined {s['top3_pct']}%")
    lines.append("")
    lines.append("Top 5 (by estimated value):")
    if doc["top5"]:
        for i, it in enumerate(doc["top5"], start=1):
            lines.append(f"{i}. {it['symbol']}: amount {it['amount_fmt']}, ≈${it['usd_value_fmt']}")
    else:
        lines.append("No priced holdings available")
    lines.append("")
    if doc["stable_holdings"]:
        lines.append("Stablecoin holdings:")
        for it in doc["stable_holdings"]:
            v = f", ≈${it['usd_value_fmt']}" if it["usd_value_fmt"] else ""
            lines.append(f"- {it['symbol']}: amount {it['amount_fmt']}{v}")
    else:
        lines.append("Stablecoin holdings: None or not detected")
    lines.append("")
    if doc["no_price"]:
        lines.append(f"No price / cannot be valued: {', '.join(doc['no_price'])}")
    if doc["suspicious"]:
        lines.append(f"Suspicious or look-alike tokens: {', '.join(doc['suspicious'])}")
    lines.append("")
    lines.append("Note: Crypto assets are volatile. This is a snapshot and rough estimation; do your own research before making decisions.")
    return "\n".join(lines)

def _render_transactions_fallback_text(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No transactions found."

    def _pick_ts(it: Dict[str, Any]) -> str:
        return it.get("timestamp") or it.get("block_timestamp") or ""

    # Sort chronologically
    try:
        items_sorted = sorted(items, key=lambda x: _pick_ts(x))
    except Exception:
        items_sorted = items

    start_ts_raw = _pick_ts(items_sorted[0]) if items_sorted else ""
    end_ts_raw = _pick_ts(items_sorted[-1]) if items_sorted else ""
    start_ts = parse_iso_utc(start_ts_raw) if start_ts_raw else "(unknown)"
    end_ts = parse_iso_utc(end_ts_raw) if end_ts_raw else "(unknown)"

    lines = []
    lines.append(f"Count: {len(items_sorted)}")
    lines.append(f"Period: {start_ts} → {end_ts}")
    lines.append("Notes: Amounts shown when available; gas fee is native ≈ fee/1e18.")
    lines.append("")

    counterparties: Dict[str, int] = {}
    token_volume_usd: Dict[str, Decimal] = {}

    for it in items_sorted:
        ts_raw = _pick_ts(it)
        ts = parse_iso_utc(ts_raw) if ts_raw else "(unknown time)"

        txh = it.get("hash") or it.get("transaction_hash") or ""
        fee_str = it.get("fee") or "0"
        try:
            fee_eth = wei_to_eth(int(str(fee_str)))
            fee_fmt = fmt_eth(fee_eth)
        except Exception:
            fee_fmt = "unknown"

        frm = it.get("from_address") or ""
        to = it.get("to_address") or ""
        if frm:
            counterparties[frm] = counterparties.get(frm, 0) + 1
        if to:
            counterparties[to] = counterparties.get(to, 0) + 1

        method = str(it.get("method") or "").lower()
        action = "Transfer"
        if "swap" in method:
            action = "Swap/Trade"
        elif method == "claim":
            action = "Claim"

        token = it.get("token") or {}
        symbol = token.get("symbol") or token.get("name") or "(unknown)"
        price = _to_decimal(token.get("exchange_rate"))

        total = it.get("total") or {}
        value_str = total.get("value")
        decimals_raw = total.get("decimals") or token.get("decimals")
        amount_fmt = "unknown"
        usd_str = "no available price"
        try:
            decimals = int(str(decimals_raw)) if decimals_raw is not None else 18
            value_int = int(str(value_str)) if value_str is not None else None
            if value_int is not None:
                amount = Decimal(value_int) / Decimal(10 ** decimals)
                amount_fmt = _fmt_amount(amount)
                if price is not None:
                    usd_val = amount * price
                    usd_str = f"≈ ${_fmt_usd(usd_val)}"
                    if symbol:
                        token_volume_usd[symbol] = token_volume_usd.get(symbol, Decimal("0")) + usd_val
        except Exception:
            pass

        line = (
            f"- {ts} — {action} — {short_addr(frm)} → {short_addr(to)} — "
            f"{amount_fmt} {symbol} ({usd_str}); gas ≈ {fee_fmt} — {short_hash(txh)}"
        )
        lines.append(line)

    # Summary
    lines.append("")
    if counterparties:
        top_ctps = sorted(counterparties.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines.append("Top counterparties:")
        for addr, cnt in top_ctps:
            lines.append(f"- {short_addr(addr)}: {cnt} interactions")
    if token_volume_usd:
        top_tokens = sorted(token_volume_usd.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines.append("Top tokens by estimated USD volume:")
        for sym, usd in top_tokens:
            lines.append(f"- {sym}: ≈ ${_fmt_usd(usd)}")

    return "\n".join(lines)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("balance_api:app", host="127.0.0.1", port=5050, reload=True)