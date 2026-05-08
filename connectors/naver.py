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

    fields = json.dumps(["impCnt", "clkCnt", "salesAmt"], separators=(',', ':'))
    camp_map = {c["nccCampaignId"]: c["name"] for c in campaigns if c.get("nccCampaignId")}
    all_ids = ",".join(camp_map.keys())

    d0 = datetime.strptime(str(start_date), "%Y-%m-%d")
    d1 = datetime.strptime(str(end_date), "%Y-%m-%d")
    num_days = (d1 - d0).days + 1

    rows = []
    stat_errors = []

    # 하루씩 조회해 실제 일별 데이터 수집
    for i in range(num_days):
        day = d0 + timedelta(days=i)
        day_str = day.strftime("%Y%m%d")
        date_str = day.strftime("%Y-%m-%d")

        time_range = json.dumps({"since": day_str, "until": day_str}, separators=(',', ':'))
        stat_path = "/stats"
        full_url = f"{BASE_URL}{stat_path}?ids={all_ids}&fields={fields}&timeRange={time_range}&timeUnit=date"
        resp = requests.get(
            full_url,
            headers=_headers("GET", stat_path, api_key, secret_key, customer_id),
        )

        if not resp.ok:
            stat_errors.append(f"{date_str}: HTTP {resp.status_code} - {resp.text[:200]}")
            continue

        body = resp.json()
        data = body if isinstance(body, list) else body.get("data", [])

        for item in data:
            camp_id = item.get("id", "")
            camp_name = camp_map.get(camp_id, camp_id)
            spend = float(item.get("salesAmt", 0))
            clicks = int(item.get("clkCnt", 0))
            impressions = int(item.get("impCnt", 0))
            rows.append({
                "date": date_str,
                "campaign": camp_name,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": (clicks / impressions * 100) if impressions > 0 else 0.0,
                "spend": spend,
                "conversions": 0,
                "revenue": 0.0,
                "roas": 0.0,
            })

    if stat_errors and not rows:
        raise RuntimeError("NAVER API 오류: " + " | ".join(stat_errors[:3]))

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=EMPTY_COLS)
