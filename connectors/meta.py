import json
import requests
import pandas as pd

GRAPH_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
EMPTY_COLS = ["date", "campaign", "impressions", "clicks", "ctr", "spend", "conversions", "revenue", "roas"]

PURCHASE_TYPES = {
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
}


def get_meta_data(app_id, app_secret, access_token, ad_account_id, start_date, end_date):
    url = f"{BASE_URL}/{ad_account_id}/insights"
    params = {
        "access_token": access_token,
        "fields": "campaign_name,impressions,clicks,ctr,spend,actions,action_values,date_start",
        "level": "campaign",
        "time_range": json.dumps({"since": str(start_date), "until": str(end_date)}),
        "time_increment": "1",
        "limit": "500",
    }

    rows = []
    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()

        for insight in body.get("data", []):
            spend = float(insight.get("spend", 0))
            actions = insight.get("actions", [])
            action_values = insight.get("action_values", [])

            conversions = sum(
                int(float(a["value"])) for a in actions if a["action_type"] in PURCHASE_TYPES
            )
            if not conversions:
                conversions = sum(
                    int(float(a["value"])) for a in actions if "purchase" in a["action_type"]
                )

            revenue = sum(
                float(a["value"]) for a in action_values if a["action_type"] in PURCHASE_TYPES
            )

            rows.append({
                "date": insight.get("date_start", ""),
                "campaign": insight.get("campaign_name", ""),
                "impressions": int(insight.get("impressions", 0)),
                "clicks": int(insight.get("clicks", 0)),
                "ctr": float(insight.get("ctr", 0)),
                "spend": spend,
                "conversions": conversions,
                "revenue": revenue,
                "roas": revenue / spend if spend > 0 else 0.0,
            })

        url = body.get("paging", {}).get("next")
        params = {}

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=EMPTY_COLS)
