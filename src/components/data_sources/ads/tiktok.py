from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger
from typing import Optional


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "tiktok"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "tiktok"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(
    access_token: Optional[str] = None,
    advertiser_id: Optional[str] = None,
    app_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad creatives from TikTok Marketing API"""
    if not access_token or not advertiser_id:
        log.warning("TikTok API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # TikTok Marketing API v1.3 endpoint
        url = "https://business-api.tiktok.com/open_api/v1.3/ad/get/"

        headers = {
            "Access-Token": access_token,
            "Content-Type": "application/json",
        }

        params = {
            "advertiser_id": advertiser_id,
            "page_size": 100,
            "page": 1,
            "filtering": {
                "ad_ids": [],  # Empty to get all ads
            }
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            log.error("TikTok API error: %s", data.get("message"))
            return pd.DataFrame()

        ads = data.get("data", {}).get("list", [])
        if not ads:
            log.info("No TikTok ads found for advertiser %s", advertiser_id)
            return pd.DataFrame()

        rows = []
        for ad in ads:
            # Get ad creative details
            creative_id = ad.get("ad_id")
            ad_name = ad.get("ad_name", "")
            ad_text = ad.get("ad_text", "")

            # Extract image/video
            creative_type = ad.get("creative_type", "")
            video_id = ad.get("video_id")
            image_ids = ad.get("image_ids", [])

            asset_uri = ""
            if video_id:
                asset_uri = f"tiktok://video/{video_id}"
            elif image_ids:
                asset_uri = f"tiktok://image/{image_ids[0]}"

            rows.append({
                "creative_id": str(creative_id),
                "platform": "tiktok",
                "title": ad_name,
                "text": ad_text,
                "hook": None,
                "overlay_text": None,
                "frame_desc": creative_type,
                "asset_uri": asset_uri,
                "status": ad.get("status", "UNKNOWN"),
                "campaign_id": str(ad.get("campaign_id", "")),
                "campaign_name": ad.get("campaign_name", None),  # TikTok may provide this
                "adset_id": str(ad.get("adgroup_id", "")),
            })

        log.info("Fetched %d TikTok ad creatives", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch TikTok creatives: %s", e)
        return pd.DataFrame()


def fetch_performance(
    start: datetime,
    end: datetime,
    access_token: Optional[str] = None,
    advertiser_id: Optional[str] = None,
    app_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad performance metrics from TikTok Marketing API"""
    if not access_token or not advertiser_id:
        log.warning("TikTok API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # TikTok Reporting API
        url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"

        headers = {
            "Access-Token": access_token,
            "Content-Type": "application/json",
        }

        payload = {
            "advertiser_id": advertiser_id,
            "service_type": "AUCTION",
            "report_type": "BASIC",
            "data_level": "AUCTION_AD",
            "dimensions": ["ad_id", "stat_time_day"],
            "metrics": [
                "impressions",
                "clicks",
                "spend",
                "conversion",
                "cost_per_conversion",
            ],
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "page_size": 1000,
            "page": 1,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        if data.get("code") != 0:
            log.error("TikTok API error: %s", data.get("message"))
            return pd.DataFrame()

        records = data.get("data", {}).get("list", [])
        if not records:
            log.info("No TikTok performance data found for advertiser %s", advertiser_id)
            return pd.DataFrame()

        rows = []
        for record in records:
            dimensions = record.get("dimensions", {})
            metrics = record.get("metrics", {})

            rows.append({
                "creative_id": str(dimensions.get("ad_id")),
                "dt": pd.to_datetime(dimensions.get("stat_time_day")),
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": int(metrics.get("clicks", 0)),
                "spend": float(metrics.get("spend", 0)),
                "conversions": int(metrics.get("conversion", 0)),
                "revenue": 0.0,  # TikTok doesn't provide revenue in basic metrics
                "platform": "tiktok",
            })

        log.info("Fetched %d TikTok performance records", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch TikTok performance: %s", e)
        return pd.DataFrame()

