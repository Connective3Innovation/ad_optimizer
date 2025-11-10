from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import json

import pandas as pd
import requests

from ...utils.logging import get_logger
from ...config import Settings


log = get_logger(__name__)


@dataclass
class RecommendedMedia:
    id: str
    caption: Optional[str]
    media_type: Optional[str]
    media_url: Optional[str]
    permalink: Optional[str]
    has_permission_for_partnership_ad: Optional[bool]
    eligibility_errors: Optional[List[str]]


def _graph_base(version: str) -> str:
    return f"https://graph.facebook.com/{version}"


def _headers() -> Dict[str, str]:
    return {"Content-Type": "application/json"}


def _graph_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(url, params=params, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def _graph_post(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(url, data=data, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def determine_permissioning(settings: Settings) -> str:
    hint = (settings.instagram_business_account_id or "").strip()
    if hint:
        return "account-level"
    return "post-level"


def _load_mock_recommended(sample_dir: Path) -> List[RecommendedMedia]:
    p = sample_dir / "meta_recommended_medias.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        out: List[RecommendedMedia] = []
        for item in raw.get("data", []):
            out.append(
                RecommendedMedia(
                    id=str(item.get("id")),
                    caption=item.get("caption"),
                    media_type=item.get("media_type"),
                    media_url=item.get("media_url"),
                    permalink=item.get("permalink"),
                    has_permission_for_partnership_ad=item.get("has_permission_for_partnership_ad"),
                    eligibility_errors=item.get("eligibility_errors"),
                )
            )
        return out
    except Exception as e:
        log.warning("Failed to load mock recommended: %s", e)
        return []


def fetch_recommended_creator_content(
    settings: Settings,
    instagram_id: Optional[str] = None,
    fields: Optional[List[str]] = None,
) -> List[RecommendedMedia]:
    if not fields:
        fields = [
            "id",
            "caption",
            "media_type",
            "media_url",
            "permalink",
            "has_permission_for_partnership_ad",
            "eligibility_errors",
        ]
    if settings.use_mock_data or not settings.meta_access_token:
        return _load_mock_recommended(settings.sample_data_dir)
    ig_id = instagram_id or settings.instagram_business_account_id
    if not ig_id:
        return []
    url = f"{_graph_base(settings.meta_api_version)}/{ig_id}/branded_content_advertisable_medias"
    params = {
        "only_fetch_recommended_content": "true",
        "fields": ",".join(fields),
        "access_token": settings.meta_access_token,
    }
    try:
        data = _graph_get(url, params)
        items = []
        for item in data.get("data", []):
            items.append(
                RecommendedMedia(
                    id=str(item.get("id")),
                    caption=item.get("caption"),
                    media_type=item.get("media_type"),
                    media_url=item.get("media_url"),
                    permalink=item.get("permalink"),
                    has_permission_for_partnership_ad=item.get("has_permission_for_partnership_ad"),
                    eligibility_errors=item.get("eligibility_errors"),
                )
            )
        return items
    except Exception as e:
        log.warning("fetch_recommended_creator_content failed: %s", e)
        return []


def create_creative_from_media(settings: Settings, media_id: str) -> Optional[str]:
    if settings.use_mock_data or settings.dry_run or not settings.meta_access_token:
        return f"mock_creative_{media_id}"
    ad_act = settings.meta_ad_account_id
    if not ad_act:
        return None
    url = f"{_graph_base(settings.meta_api_version)}/act_{ad_act}/adcreatives"
    data = {
        "source_instagram_media_id": media_id,
        "access_token": settings.meta_access_token,
    }
    try:
        res = _graph_post(url, data)
        return str(res.get("id")) if res.get("id") else None
    except Exception as e:
        log.warning("create_creative_from_media failed: %s", e)
        return None


def create_creative_from_ad_code(settings: Settings, ad_code: str) -> Optional[str]:
    if settings.use_mock_data or settings.dry_run or not settings.meta_access_token:
        return f"mock_creative_code_{ad_code[:6]}"
    ad_act = settings.meta_ad_account_id
    if not ad_act:
        return None
    url = f"{_graph_base(settings.meta_api_version)}/act_{ad_act}/adcreatives"
    data = {
        "instagram_boost_post_access_token": ad_code,
        "access_token": settings.meta_access_token,
    }
    try:
        res = _graph_post(url, data)
        return str(res.get("id")) if res.get("id") else None
    except Exception as e:
        log.warning("create_creative_from_ad_code failed: %s", e)
        return None


def create_ad(
    settings: Settings,
    creative_id: str,
    adset_id: Optional[str] = None,
    name: Optional[str] = None,
    status: str = "PAUSED",
) -> Optional[str]:
    if settings.use_mock_data or settings.dry_run or not settings.meta_access_token:
        return f"mock_ad_{creative_id}"
    ad_act = settings.meta_ad_account_id
    if not ad_act:
        return None
    url = f"{_graph_base(settings.meta_api_version)}/act_{ad_act}/ads"
    data = {
        "creative": json.dumps({"creative_id": creative_id}),
        "adset_id": adset_id or settings.meta_default_adset_id or "",
        "name": name or f"Partnership Ad {creative_id}",
        "status": status,
        "access_token": settings.meta_access_token,
    }
    try:
        res = _graph_post(url, data)
        return str(res.get("id")) if res.get("id") else None
    except Exception as e:
        log.warning("create_ad failed: %s", e)
        return None


def orchestrate_boost_from_media(
    settings: Settings,
    media_id: str,
    adset_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    cr_id = create_creative_from_media(settings, media_id)
    if not cr_id:
        return None, None
    ad_id = create_ad(settings, cr_id, adset_id=adset_id)
    return cr_id, ad_id


def orchestrate_boost_from_ad_code(
    settings: Settings,
    ad_code: str,
    adset_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    cr_id = create_creative_from_ad_code(settings, ad_code)
    if not cr_id:
        return None, None
    ad_id = create_ad(settings, cr_id, adset_id=adset_id)
    return cr_id, ad_id


def recommended_content_dataframe(items: List[RecommendedMedia]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([
        {
            "id": i.id,
            "caption": i.caption,
            "media_type": i.media_type,
            "media_url": i.media_url,
            "permalink": i.permalink,
            "has_permission_for_partnership_ad": i.has_permission_for_partnership_ad,
            "eligibility_errors": ", ".join(i.eligibility_errors or []),
        }
        for i in items
    ])

