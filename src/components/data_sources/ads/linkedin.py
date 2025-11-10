from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger
from typing import Optional


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "linkedin"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "linkedin"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(
    access_token: Optional[str] = None,
    ad_account_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad creatives from LinkedIn Marketing API"""
    if not access_token or not ad_account_id:
        log.warning("LinkedIn API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # LinkedIn Marketing API - Creatives endpoint
        url = "https://api.linkedin.com/v2/adCreativesV2"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        params = {
            "q": "account",
            "account": f"urn:li:sponsoredAccount:{ad_account_id}",
            "count": 100,
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        elements = data.get("elements", [])
        if not elements:
            log.info("No LinkedIn creatives found for account %s", ad_account_id)
            return pd.DataFrame()

        rows = []
        for creative in elements:
            # Extract creative content
            content = creative.get("content", {})
            reference = content.get("reference", "")

            # Get different creative types
            title = ""
            text = ""
            image_url = ""

            if "adContent" in content:
                ad_content = content.get("adContent", {})
                title = ad_content.get("title", "")
                text = ad_content.get("description", "")

            # Handle different content types (sponsored content, etc.)
            if "sponsoredCreativeContent" in creative:
                scc = creative.get("sponsoredCreativeContent", {})
                share_content = scc.get("shareContent", {})
                media = share_content.get("media", [])
                if media:
                    image_url = media[0].get("landingPage", {}).get("thumbnailUrl", "")

            # Extract campaign ID from URN
            campaign_urn = creative.get("campaign", "")
            campaign_id = campaign_urn.split(":")[-1] if campaign_urn else ""

            rows.append({
                "creative_id": str(creative.get("id")),
                "platform": "linkedin",
                "title": title,
                "text": text,
                "hook": None,
                "overlay_text": None,
                "frame_desc": creative.get("type", ""),
                "asset_uri": image_url,
                "status": creative.get("status", "UNKNOWN"),
                "campaign_id": campaign_id,
                "campaign_name": None,  # Would require separate API call to fetch campaign details
                "adset_id": "",
            })

        log.info("Fetched %d LinkedIn ad creatives", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch LinkedIn creatives: %s", e)
        return pd.DataFrame()


def fetch_performance(
    start: datetime,
    end: datetime,
    access_token: Optional[str] = None,
    ad_account_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad performance metrics from LinkedIn Marketing API"""
    if not access_token or not ad_account_id:
        log.warning("LinkedIn API credentials missing")
        return pd.DataFrame()

    try:
        import requests

        # LinkedIn Analytics API
        url = "https://api.linkedin.com/v2/adAnalyticsV2"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        # Convert to LinkedIn's date format (milliseconds since epoch)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        params = {
            "q": "analytics",
            "pivot": "CREATIVE",
            "timeGranularity": "DAILY",
            "dateRange.start.day": start.day,
            "dateRange.start.month": start.month,
            "dateRange.start.year": start.year,
            "dateRange.end.day": end.day,
            "dateRange.end.month": end.month,
            "dateRange.end.year": end.year,
            "accounts[0]": f"urn:li:sponsoredAccount:{ad_account_id}",
            "fields": "impressions,clicks,costInLocalCurrency,externalWebsiteConversions,conversionValueInLocalCurrency",
            "count": 1000,
        }

        response = requests.get(url, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        elements = data.get("elements", [])
        if not elements:
            log.info("No LinkedIn performance data found for account %s", ad_account_id)
            return pd.DataFrame()

        rows = []
        for element in elements:
            # Extract creative ID from pivot value
            pivot_value = element.get("pivotValue", "")
            creative_id = pivot_value.split(":")[-1] if ":" in pivot_value else pivot_value

            # Extract date
            date_range = element.get("dateRange", {})
            start_date = date_range.get("start", {})
            date_obj = datetime(
                year=start_date.get("year", start.year),
                month=start_date.get("month", start.month),
                day=start_date.get("day", start.day)
            )

            rows.append({
                "creative_id": str(creative_id),
                "dt": pd.to_datetime(date_obj),
                "impressions": int(element.get("impressions", 0)),
                "clicks": int(element.get("clicks", 0)),
                "spend": float(element.get("costInLocalCurrency", 0)),
                "conversions": int(element.get("externalWebsiteConversions", 0)),
                "revenue": float(element.get("conversionValueInLocalCurrency", 0)),
                "platform": "linkedin",
            })

        log.info("Fetched %d LinkedIn performance records", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch LinkedIn performance: %s", e)
        return pd.DataFrame()
