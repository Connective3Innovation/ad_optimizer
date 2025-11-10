from __future__ import annotations

from datetime import datetime
import pandas as pd
from ...utils.logging import get_logger
from typing import Optional, Dict, Any


log = get_logger(__name__)


def fetch_creatives_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path)
        df["platform"] = "google"
        return df
    except Exception as e:
        log.error("Failed to read mock creatives: %s", e)
        return pd.DataFrame()


def fetch_performance_mock(sample_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(sample_path, parse_dates=["dt"])  # yyyy-mm-dd
        df["platform"] = "google"
        return df
    except Exception as e:
        log.error("Failed to read mock performance: %s", e)
        return pd.DataFrame()


def fetch_creatives(
    developer_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
    customer_id: Optional[str] = None,
    mcc_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad creatives from Google Ads API

    Args:
        developer_token: Google Ads developer token
        client_id: OAuth client ID
        client_secret: OAuth client secret
        refresh_token: OAuth refresh token
        customer_id: Customer account ID (the account with campaigns)
        mcc_id: MCC account ID (for authentication). If not provided, uses customer_id
    """
    if not all([developer_token, client_id, client_secret, refresh_token, customer_id]):
        log.warning("Google Ads credentials missing")
        return pd.DataFrame()

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException

        # Use MCC ID for authentication if provided, otherwise use customer_id
        login_id = mcc_id if mcc_id else customer_id

        # Initialize client with credentials
        credentials = {
            "developer_token": developer_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "login_customer_id": login_id.replace("-", ""),  # MCC or direct account
            "use_proto_plus": True,
        }

        client = GoogleAdsClient.load_from_dict(credentials)
        ga_service = client.get_service("GoogleAdsService")

        # Query for ads with all possible text fields
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.name,
                ad_group_ad.ad.type,
                ad_group_ad.ad.final_urls,
                ad_group_ad.ad.expanded_text_ad.headline_part1,
                ad_group_ad.ad.expanded_text_ad.headline_part2,
                ad_group_ad.ad.expanded_text_ad.description,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group_ad.ad.text_ad.headline,
                ad_group_ad.ad.text_ad.description1,
                ad_group_ad.status,
                campaign.id,
                campaign.name,
                ad_group.id,
                ad_group.name
            FROM ad_group_ad
            WHERE ad_group_ad.status != 'REMOVED'
            LIMIT 1000
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        try:
            response = ga_service.search(request=search_request)
        except GoogleAdsException as ex:
            log.error(f"Google Ads query failed: {ex.failure.errors[0].message}")
            return pd.DataFrame()

        rows = []
        for row in response:
            try:
                ad = row.ad_group_ad.ad
                ad_type = ad.type_.name if hasattr(ad, 'type_') else "UNKNOWN"

                # Extract text based on ad type
                title = ""
                text = ""

                # Responsive Search Ad
                if hasattr(ad, 'responsive_search_ad') and ad.responsive_search_ad.headlines:
                    headlines = [h.text for h in ad.responsive_search_ad.headlines if h.text]
                    descriptions = [d.text for d in ad.responsive_search_ad.descriptions if d.text]
                    title = headlines[0] if headlines else ""
                    text = descriptions[0] if descriptions else ""

                # Expanded Text Ad
                elif hasattr(ad, 'expanded_text_ad') and ad.expanded_text_ad.headline_part1:
                    h1 = ad.expanded_text_ad.headline_part1
                    h2 = ad.expanded_text_ad.headline_part2 if hasattr(ad.expanded_text_ad, 'headline_part2') else ""
                    title = f"{h1} {h2}".strip()
                    text = ad.expanded_text_ad.description if hasattr(ad.expanded_text_ad, 'description') else ""

                # Text Ad (legacy)
                elif hasattr(ad, 'text_ad') and ad.text_ad.headline:
                    title = ad.text_ad.headline
                    text = ad.text_ad.description1 if hasattr(ad.text_ad, 'description1') else ""

                # Fallback to ad name
                if not title:
                    title = ad.name if hasattr(ad, 'name') and ad.name else f"Ad {ad.id}"
                if not text:
                    text = f"Type: {ad_type}"

                rows.append({
                    "creative_id": str(ad.id),
                    "platform": "google",
                    "title": title,
                    "text": text,
                    "hook": None,
                    "overlay_text": None,
                    "frame_desc": None,
                    "asset_uri": "",
                    "status": row.ad_group_ad.status.name,
                    "campaign_id": str(row.campaign.id),
                    "adset_id": str(row.ad_group.id),
                })
            except Exception as e:
                log.warning(f"Failed to process ad {ad.id}: {e}")
                continue

        df = pd.DataFrame(rows)

        # Log status distribution for debugging
        if not df.empty and "status" in df.columns:
            status_counts = df["status"].value_counts().to_dict()
            log.info("Fetched %d Google Ads creatives - Status distribution: %s", len(rows), status_counts)
        else:
            log.info("Fetched %d Google Ads creatives", len(rows))

        return df

    except Exception as e:
        log.error("Failed to fetch Google Ads creatives: %s", e)
        return pd.DataFrame()


def fetch_performance(
    start: datetime,
    end: datetime,
    developer_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
    customer_id: Optional[str] = None,
    mcc_id: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch ad performance metrics from Google Ads API

    Args:
        start: Start date for performance data
        end: End date for performance data
        developer_token: Google Ads developer token
        client_id: OAuth client ID
        client_secret: OAuth client secret
        refresh_token: OAuth refresh token
        customer_id: Customer account ID (the account with campaigns)
        mcc_id: MCC account ID (for authentication). If not provided, uses customer_id
    """
    if not all([developer_token, client_id, client_secret, refresh_token, customer_id]):
        log.warning("Google Ads credentials missing")
        return pd.DataFrame()

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException

        # Use MCC ID for authentication if provided, otherwise use customer_id
        login_id = mcc_id if mcc_id else customer_id

        # Initialize client
        credentials = {
            "developer_token": developer_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "login_customer_id": login_id.replace("-", ""),  # MCC or direct account
            "use_proto_plus": True,
        }

        client = GoogleAdsClient.load_from_dict(credentials)
        ga_service = client.get_service("GoogleAdsService")

        # Query for performance metrics
        query = f"""
            SELECT
                ad_group_ad.ad.id,
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value
            FROM ad_group_ad
            WHERE segments.date BETWEEN '{start.strftime("%Y-%m-%d")}' AND '{end.strftime("%Y-%m-%d")}'
                AND ad_group_ad.status != 'REMOVED'
        """

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id.replace("-", "")
        search_request.query = query

        response = ga_service.search(request=search_request)

        rows = []
        for row in response:
            rows.append({
                "creative_id": str(row.ad_group_ad.ad.id),
                "dt": pd.to_datetime(row.segments.date),
                "impressions": int(row.metrics.impressions),
                "clicks": int(row.metrics.clicks),
                "spend": float(row.metrics.cost_micros) / 1_000_000,  # Convert micros to currency
                "conversions": int(row.metrics.conversions),
                "revenue": float(row.metrics.conversions_value),
                "platform": "google",
            })

        log.info("Fetched %d Google Ads performance records", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch Google Ads performance: %s", e)
        return pd.DataFrame()

