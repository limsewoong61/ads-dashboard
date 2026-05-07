import pandas as pd
from google.ads.googleads.client import GoogleAdsClient

EMPTY_COLS = ["date", "campaign", "impressions", "clicks", "ctr", "spend", "conversions", "roas"]


def get_google_ads_data(customer_id, start_date, end_date, credentials):
    client = GoogleAdsClient.load_from_dict(credentials)
    ga_service = client.get_service("GoogleAdsService")
    clean_id = customer_id.replace("-", "")

    query = f"""
        SELECT
            campaign.name,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            AND campaign.status != 'REMOVED'
        ORDER BY segments.date DESC
    """

    response = ga_service.search(customer_id=clean_id, query=query)

    rows = []
    for row in response:
        spend = row.metrics.cost_micros / 1_000_000
        revenue = row.metrics.conversions_value
        rows.append({
            "date": row.segments.date,
            "campaign": row.campaign.name,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "ctr": row.metrics.ctr * 100,
            "spend": spend,
            "conversions": row.metrics.conversions,
            "roas": revenue / spend if spend > 0 else 0.0,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=EMPTY_COLS)
