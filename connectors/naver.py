import hashlib
import hmac as _hmac
import base64
import time
import json
import urllib.parse
import requests
import pandas as pd

BASE_URL = "https://api.naver.com"
EMPTY_COLS = ["date", "campaign", "impressions", "clicks", "ctr", "spend", "conversions", "revenue", "roas"]


def _sign(timestamp: str, method: str, path: str, secret_key: str) -> str:
    msg = f"{timestamp}.{method}.{path}"
    digest = _hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers(method: str, path: str, api_key: str, secret_key: str, customer_id: str) -> dict:
    ts = str(int(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": ts,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _sign(ts, method, path, secret_key),
    }


def get_naver_data(api_key: str, secret_key: str, customer_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = "/ncc/campaigns"
    resp = requests.get(
        BASE_URL + path,
        headers=_headers("GET", path, api_key, secret_key, customer_id),
    )

    if not resp.ok:
        raise RuntimeError(f"NAVER 캠페인 조회 실패 (HTTP {resp.status_code}): {resp.text}")

    campaigns = resp.json()

    if not campaigns:
        raise RuntimeError("NAVER 캠페인 목록이 비어있습니다. API 키와 Customer ID를 확인해주세요.")

    since = str(start_date).replace("-", "")
    until = str(end_date).replace("-", "")
    fields = json.dumps(["impCnt", "clkCnt", "ctr", "salesAmt", "rvsCnt"], separators=(',', ':'))
    time_range = json.dumps({"since": since, "until": until}, separators=(',', ':'))

    rows = []
    stat_errors = []

    for camp in campaigns:
        camp_id = camp.get("nccCampaignId", "")
        camp_name = camp.get("name", "")
        if not camp_id:
            continue

        stat_path = "/stats"
        full_url = f"{BASE_URL}{stat_path}?ids={camp_id}&fields={fields}&timeRange={time_range}&timeUnit=date"
        resp = requests.get(
            full_url,
            headers=_headers("GET", stat_path, api_key, secret_key, customer_id),
        )

        if not resp.ok:
            stat_errors.append(f"{camp_name}: HTTP {resp.status_code} - {resp.text[:300]} | URL: {full_url[:300]}")
            continue

        body = resp.json()
        data = body if isinstance(body, list) else body.get("data", [])

        for item in data:
            dt = item.get("dt", "")
            if len(dt) == 8:
                dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
            spend = float(item.get("salesAmt", 0))
            clicks = int(item.get("clkCnt", 0))
            impressions = int(item.get("impCnt", 0))
            ctr = float(item.get("ctr", 0)) * 100
            rows.append({
                "date": dt,
                "campaign": camp_name,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr if ctr > 0 else ((clicks / impressions * 100) if impressions > 0 else 0.0),
                "spend": spend,
                "conversions": int(item.get("rvsCnt", 0)),
                "revenue": 0.0,
                "roas": 0.0,
            })

    if not rows:
        err_detail = (" | ".join(stat_errors[:3])) if stat_errors else "해당 기간 데이터 없음"
        raise RuntimeError(f"NAVER 통계 데이터 없음: {err_detail}")

    return pd.DataFrame(rows)
