from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "meta"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "meta"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(api_token: str | None = None, ad_account_id: str | None = None, api_version: str = "v24.0") -> pd.DataFrame:
    """Fetch ad creatives from Meta Marketing API"""
    if not api_token or not ad_account_id:
        log.warning("Meta API token or ad_account_id missing")
        return pd.DataFrame()

    try:
        import requests

        # Ensure ad_account_id has act_ prefix
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"

        url = f"https://graph.facebook.com/{api_version}/{ad_account_id}/ads"
        params = {
            "access_token": api_token,
            "fields": "id,name,status,creative{id,name,title,body,image_url,video_id,object_story_spec}",
            "limit": 100
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "data" not in data or not data["data"]:
            log.info("No ads found in account %s", ad_account_id)
            return pd.DataFrame()

        # Parse ad data into creatives dataframe
        rows = []
        for ad in data["data"]:
            creative = ad.get("creative", {})
            rows.append({
                "creative_id": creative.get("id", ad["id"]),
                "platform": "meta",
                "title": creative.get("title", creative.get("name", "")),
                "text": creative.get("body", ""),
                "hook": None,
                "overlay_text": None,
                "frame_desc": None,
                "asset_uri": creative.get("image_url", ""),
                "status": ad.get("status", "UNKNOWN")
            })

        log.info("Fetched %d Meta ad creatives", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch Meta creatives: %s", e)
        return pd.DataFrame()


def fetch_performance(start: datetime, end: datetime, api_token: str | None = None, ad_account_id: str | None = None, api_version: str = "v24.0") -> pd.DataFrame:
    """Fetch ad performance metrics from Meta Marketing API"""
    if not api_token or not ad_account_id:
        log.warning("Meta API token or ad_account_id missing")
        return pd.DataFrame()

    try:
        import requests

        # Ensure ad_account_id has act_ prefix
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"

        url = f"https://graph.facebook.com/{api_version}/{ad_account_id}/insights"
        params = {
            "access_token": api_token,
            "time_range": f'{{"since":"{start.strftime("%Y-%m-%d")}","until":"{end.strftime("%Y-%m-%d")}"}}',
            "time_increment": 1,  # Daily breakdown
            "level": "ad",
            "fields": "ad_id,ad_name,date_start,impressions,clicks,spend,actions",
            "limit": 1000
        }

        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        # Check for API errors
        if "error" in data:
            log.error("Meta API error: %s", data["error"])
            return pd.DataFrame()

        if "data" not in data or not data["data"]:
            log.info("No performance data found for account %s", ad_account_id)
            return pd.DataFrame()

        # Parse performance data
        rows = []
        for item in data["data"]:
            # Extract conversions from actions array
            conversions = 0
            actions = item.get("actions", [])
            for action in actions:
                if action.get("action_type") in ["purchase", "lead", "complete_registration", "offsite_conversion"]:
                    conversions += int(action.get("value", 0))

            rows.append({
                "creative_id": item.get("ad_id"),
                "dt": pd.to_datetime(item.get("date_start")),
                "impressions": int(item.get("impressions", 0)),
                "clicks": int(item.get("clicks", 0)),
                "spend": float(item.get("spend", 0)),
                "conversions": conversions,
                "platform": "meta"
            })

        log.info("Fetched %d Meta performance records", len(rows))
        return pd.DataFrame(rows)

    except requests.exceptions.HTTPError as e:
        # Try to get more details from the response
        try:
            error_data = e.response.json()
            log.error("Meta API HTTP error: %s - %s", e, error_data)
        except:
            log.error("Meta API HTTP error: %s", e)
        return pd.DataFrame()
    except Exception as e:
        log.error("Failed to fetch Meta performance: %s", e)
        return pd.DataFrame()

