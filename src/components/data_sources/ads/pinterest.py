from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger
from typing import Optional


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "pinterest"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "pinterest"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(
    access_token: Optional[str] = None,
    ad_account_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad creatives from Pinterest Ads API"""
    if not access_token or not ad_account_id:
        log.warning("Pinterest API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # Pinterest Ads API v5
        url = f"https://api.pinterest.com/v5/ad_accounts/{ad_account_id}/ads"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        params = {
            "page_size": 100,
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        ads = data.get("items", [])
        if not ads:
            log.info("No Pinterest ads found for account %s", ad_account_id)
            return pd.DataFrame()

        rows = []
        for ad in ads:
            # Get Pin ID to fetch creative details
            pin_id = ad.get("pin_id")
            creative_type = ad.get("creative_type", "REGULAR")

            # Fetch pin details for creative info
            pin_url = f"https://api.pinterest.com/v5/pins/{pin_id}" if pin_id else None
            pin_data = {}

            if pin_url:
                try:
                    pin_response = requests.get(pin_url, headers=headers, timeout=10)
                    pin_response.raise_for_status()
                    pin_data = pin_response.json()
                except Exception as e:
                    log.warning("Failed to fetch pin details for %s: %s", pin_id, e)

            rows.append({
                "creative_id": str(ad.get("id")),
                "platform": "pinterest",
                "title": pin_data.get("title", ad.get("name", "")),
                "text": pin_data.get("description", ""),
                "hook": None,
                "overlay_text": None,
                "frame_desc": creative_type,
                "asset_uri": pin_data.get("media", {}).get("images", {}).get("originals", {}).get("url", ""),
                "status": ad.get("status", "UNKNOWN"),
                "campaign_id": str(ad.get("campaign_id", "")),
                "adset_id": str(ad.get("ad_group_id", "")),
            })

        log.info("Fetched %d Pinterest ad creatives", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch Pinterest creatives: %s", e)
        return pd.DataFrame()


def fetch_performance(
    start: datetime,
    end: datetime,
    access_token: Optional[str] = None,
    ad_account_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad performance metrics from Pinterest Ads API"""
    if not access_token or not ad_account_id:
        log.warning("Pinterest API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # Pinterest Analytics API
        url = f"https://api.pinterest.com/v5/ad_accounts/{ad_account_id}/ads/analytics"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        params = {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "granularity": "DAY",
            "columns": "IMPRESSION,CLICKTHROUGH,SPEND_IN_DOLLAR,TOTAL_CONVERSIONS,TOTAL_CONVERSIONS_VALUE",
            "page_size": 1000,
        }

        response = requests.get(url, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            log.info("No Pinterest performance data found for account %s", ad_account_id)
            return pd.DataFrame()

        rows = []
        for item in items:
            # Pinterest returns metrics per ad per day
            ad_id = item.get("AD_ID")
            date_str = item.get("DATE")

            rows.append({
                "creative_id": str(ad_id),
                "dt": pd.to_datetime(date_str),
                "impressions": int(item.get("IMPRESSION", 0)),
                "clicks": int(item.get("CLICKTHROUGH", 0)),
                "spend": float(item.get("SPEND_IN_DOLLAR", 0)),
                "conversions": int(item.get("TOTAL_CONVERSIONS", 0)),
                "revenue": float(item.get("TOTAL_CONVERSIONS_VALUE", 0)),
                "platform": "pinterest",
            })

        log.info("Fetched %d Pinterest performance records", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch Pinterest performance: %s", e)
        return pd.DataFrame()
