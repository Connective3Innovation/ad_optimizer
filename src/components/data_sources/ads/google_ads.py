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
                AND campaign.status = 'ENABLED'
            LIMIT 5000
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
                    "campaign_name": row.campaign.name if hasattr(row.campaign, 'name') else None,
                    "adset_id": str(row.ad_group.id),
                    "adset_name": row.ad_group.name if hasattr(row.ad_group, 'name') else None,
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
    view: str = "ad",
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
        view: 'ad' for creative-level data (default) or 'asset' for asset-level metrics
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

        customer_rn = customer_id.replace("-", "")

        def _run_query(query: str):
            search_request = client.get_type("SearchGoogleAdsRequest")
            search_request.customer_id = customer_rn
            search_request.query = query
            return ga_service.search(request=search_request)

        view_mode = (view or "ad").lower()

        if view_mode == "asset":
            query = f"""
                SELECT
                    ad_group_ad.ad.id,
                    ad_group.id,
                    ad_group.name,
                    campaign.id,
                    campaign.name,
                    ad_group_ad_asset_view.field_type,
                    ad_group_ad_asset_view.performance_label,
                    asset.resource_name,
                    asset.name,
                    asset.type,
                    asset.text_asset.text,
                    asset.image_asset.full_size_image_url,
                    asset.youtube_video_asset.youtube_video_id,
                    segments.date,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.conversions_value
                FROM ad_group_ad_asset_view
                WHERE segments.date BETWEEN '{start.strftime("%Y-%m-%d")}' AND '{end.strftime("%Y-%m-%d")}'
                    AND ad_group_ad.status != 'REMOVED'
                    AND campaign.status = 'ENABLED'
            """
            response = _run_query(query)

            def _extract_asset_fields(asset_obj):
                asset_text = None
                asset_url = None
                youtube_id = None

                if hasattr(asset_obj, "text_asset") and asset_obj.text_asset and getattr(asset_obj.text_asset, "text", None):
                    asset_text = asset_obj.text_asset.text

                if hasattr(asset_obj, "image_asset") and asset_obj.image_asset and getattr(asset_obj.image_asset, "full_size_image_url", None):
                    asset_url = asset_obj.image_asset.full_size_image_url

                if hasattr(asset_obj, "youtube_video_asset") and asset_obj.youtube_video_asset and getattr(asset_obj.youtube_video_asset, "youtube_video_id", None):
                    youtube_id = asset_obj.youtube_video_asset.youtube_video_id
                    asset_url = f"https://www.youtube.com/watch?v={youtube_id}"

                return asset_text, asset_url, youtube_id

            rows = []
            for row in response:
                try:
                    asset_obj = getattr(row, "asset", None)
                    asset_text, asset_url, youtube_id = _extract_asset_fields(asset_obj) if asset_obj else (None, None, None)
                    asset_text_value = asset_text
                    if not asset_text_value and asset_obj and hasattr(asset_obj, "text_asset"):
                        asset_text_value = getattr(asset_obj.text_asset, "text", None)
                    asset_type = None
                    if asset_obj:
                        if hasattr(asset_obj, "type_") and asset_obj.type_:
                            asset_type = asset_obj.type_.name
                        elif hasattr(asset_obj, "asset_type") and asset_obj.asset_type:
                            asset_type = asset_obj.asset_type.name

                    rows.append({
                        "creative_id": str(row.ad_group_ad.ad.id),
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name if hasattr(row.campaign, 'name') else None,
                        "ad_group_id": str(row.ad_group.id),
                        "ad_group_name": row.ad_group.name if hasattr(row.ad_group, 'name') else None,
                        "asset_resource_name": row.ad_group_ad_asset_view.asset,
                        "asset_name": asset_obj.name if asset_obj and hasattr(asset_obj, "name") else None,
                        "asset_type": asset_type,
                        "field_type": row.ad_group_ad_asset_view.field_type.name if row.ad_group_ad_asset_view.field_type else None,
                        "asset_performance_label": row.ad_group_ad_asset_view.performance_label.name if row.ad_group_ad_asset_view.performance_label else None,
                        "asset_text": asset_text_value,
                        "asset_url": asset_url,
                        "asset_youtube_id": youtube_id,
                        "dt": pd.to_datetime(row.segments.date),
                        "impressions": int(row.metrics.impressions),
                        "clicks": int(row.metrics.clicks),
                        "spend": float(row.metrics.cost_micros) / 1_000_000,
                        "conversions": float(row.metrics.conversions),
                        "revenue": float(row.metrics.conversions_value),
                        "platform": "google",
                    })
                except Exception as asset_err:
                    log.warning("Failed to process asset row: %s", asset_err)
                    continue

            log.info("Fetched %d Google Ads asset performance records", len(rows))
            return pd.DataFrame(rows)

        # Default creative-level performance query
        # Note: Not filtering by campaign.status to match Google Ads UI behavior
        # which shows enabled ads regardless of campaign/ad group status
        query = f"""
            SELECT
                ad_group_ad.ad.id,
                ad_group.id,
                ad_group.name,
                campaign.id,
                campaign.name,
                campaign.status,
                ad_group.status,
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.average_cpc,
                metrics.conversions_from_interactions_rate
            FROM ad_group_ad
            WHERE segments.date BETWEEN '{start.strftime("%Y-%m-%d")}' AND '{end.strftime("%Y-%m-%d")}'
                AND ad_group_ad.status != 'REMOVED'
        """

        response = _run_query(query)

        rows = []
        for row in response:
            rows.append({
                "creative_id": str(row.ad_group_ad.ad.id),
                "ad_group_id": str(row.ad_group.id),
                "ad_group_name": row.ad_group.name if hasattr(row.ad_group, 'name') else None,
                "ad_group_status": row.ad_group.status.name if hasattr(row.ad_group, 'status') else None,
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name if hasattr(row.campaign, 'name') else None,
                "campaign_status": row.campaign.status.name if hasattr(row.campaign, 'status') else None,
                "dt": pd.to_datetime(row.segments.date),
                "impressions": int(row.metrics.impressions),
                "clicks": int(row.metrics.clicks),
                "spend": float(row.metrics.cost_micros) / 1_000_000,  # Convert micros to currency
                "conversions": int(row.metrics.conversions),
                "revenue": float(row.metrics.conversions_value),
                "cpc": float(row.metrics.average_cpc) / 1_000_000 if hasattr(row.metrics, 'average_cpc') else 0.0,  # Convert micros to currency
                "cvr": float(row.metrics.conversions_from_interactions_rate) if hasattr(row.metrics, 'conversions_from_interactions_rate') else 0.0,
                "platform": "google",
            })

        log.info("Fetched %d Google Ads performance records", len(rows))
        return pd.DataFrame(rows)

    except Exception as e:
        log.error("Failed to fetch Google Ads performance: %s", e)
        return pd.DataFrame()

