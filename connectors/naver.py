import hashlib
import hmac as _hmac
import base64
import time
import json
import requests
import pandas as pd

BASE_URL = "https://api.naver.com"
EMPTY_COLS = ["date", "campaign", "impressions", "clicks", "ctr", "spend", "conversions", "roas"]


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
    resp.raise_for_status()
    campaigns = resp.json()

    if not campaigns:
        return pd.DataFrame(columns=EMPTY_COLS)

    rows = []
    for camp in campaigns:
        camp_id = camp.get("nccCampaignId", "")
        camp_name = camp.get("name", "")
        if not camp_id:
            continue

        path = "/stats"
        params = {
            "ids": camp_id,
            "fields": "impCnt,clkCnt,ctr,salesAmt,rvsCnt,convAmt",
            "timeRange": json.dumps({"since": str(start_date), "until": str(end_date)}),
            "timeUnit": "day",
        }
        resp = requests.get(
            BASE_URL + path,
            headers=_headers("GET", path, api_key, secret_key, customer_id),
            params=params,
        )
        if not resp.ok:
            continue

        for item in resp.json().get("data", []):
            dt = item.get("dt", "")
            if len(dt) == 8:
                dt = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
            spend = float(item.get("salesAmt", 0))
            conv_amt = float(item.get("convAmt", 0))
            rows.append({
                "date": dt,
                "campaign": camp_name,
                "impressions": int(item.get("impCnt", 0)),
                "clicks": int(item.get("clkCnt", 0)),
                "ctr": float(item.get("ctr", 0)) * 100,
                "spend": spend,
                "conversions": int(item.get("rvsCnt", 0)),
                "roas": conv_amt / spend if spend > 0 else 0.0,
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=EMPTY_COLS)
