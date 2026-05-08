import hashlib
import hmac as _hmac
import base64
import time
import json
import urllib.parse
import requests
import pandas as pd
from datetime import datetime, timedelta

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
    fields = json.dumps(["impCnt", "clkCnt", "salesAmt"], separators=(',', ':'))
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
            raw_dt = item.get("dt", "")
            spend_total = float(item.get("salesAmt", 0))
            clicks_total = int(item.get("clkCnt", 0))
            imps_total = int(item.get("impCnt", 0))

            if len(raw_dt) == 8:
                # 일별 데이터: 그대로 사용
                dt = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}"
                rows.append({
                    "date": dt, "campaign": camp_name,
                    "impressions": imps_total, "clicks": clicks_total,
                    "ctr": (clicks_total / imps_total * 100) if imps_total > 0 else 0.0,
                    "spend": spend_total, "conversions": 0, "revenue": 0.0, "roas": 0.0,
                })
            else:
                # 집계 행: 일수로 균등 분배해 차트 스파이크 방지
                d0 = datetime.strptime(str(start_date), "%Y-%m-%d")
                d1 = datetime.strptime(str(end_date), "%Y-%m-%d")
                num_days = max((d1 - d0).days + 1, 1)
                daily_spend = spend_total / num_days
                daily_clicks = clicks_total / num_days
                daily_imps = imps_total / num_days
                for i in range(num_days):
                    day = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
                    rows.append({
                        "date": day, "campaign": camp_name,
                        "impressions": daily_imps, "clicks": daily_clicks,
                        "ctr": (daily_clicks / daily_imps * 100) if daily_imps > 0 else 0.0,
                        "spend": daily_spend, "conversions": 0, "revenue": 0.0, "roas": 0.0,
                    })

    if stat_errors and not rows:
        raise RuntimeError("NAVER API 오류: " + " | ".join(stat_errors[:2]))

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=EMPTY_COLS)
