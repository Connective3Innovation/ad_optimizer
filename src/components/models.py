from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List, Dict, Any


@dataclass
class Client:
    """Multi-client configuration"""
    client_id: str
    client_name: str
    is_active: bool = True
    # Platform credentials stored as JSON
    meta_access_token: Optional[str] = None
    meta_ad_account_id: Optional[str] = None
    meta_api_version: str = "v19.0"
    google_ads_developer_token: Optional[str] = None
    google_ads_client_id: Optional[str] = None
    google_ads_client_secret: Optional[str] = None
    google_ads_refresh_token: Optional[str] = None
    google_ads_customer_id: Optional[str] = None
    google_ads_mcc_id: Optional[str] = None  # MCC account for authentication (if applicable)
    tiktok_access_token: Optional[str] = None
    tiktok_app_id: Optional[str] = None
    tiktok_secret: Optional[str] = None
    tiktok_advertiser_id: Optional[str] = None
    pinterest_access_token: Optional[str] = None
    pinterest_ad_account_id: Optional[str] = None
    linkedin_access_token: Optional[str] = None
    linkedin_ad_account_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass
class Creative:
    creative_id: str
    platform: str  # meta|tiktok|google|pinterest|linkedin
    client_id: Optional[str] = None  # Multi-client support
    account_id: Optional[str] = None
    campaign_id: Optional[str] = None
    adset_id: Optional[str] = None
    ad_id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    hook: Optional[str] = None
    overlay_text: Optional[str] = None
    frame_desc: Optional[str] = None
    asset_uri: Optional[str] = None  # image/video URL or gs://
    status: Optional[str] = None     # active|paused|deleted


@dataclass
class Performance:
    creative_id: str
    dt: date
    impressions: int
    clicks: int
    spend: float
    conversions: int = 0
    revenue: float = 0.0
    client_id: Optional[str] = None  # Multi-client support
    platform: Optional[str] = None

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions) if self.impressions else 0.0

    @property
    def cvr(self) -> float:
        return (self.conversions / self.clicks) if self.clicks else 0.0

    @property
    def cpa(self) -> float:
        return (self.spend / self.conversions) if self.conversions else 0.0

    @property
    def roas(self) -> float:
        return (self.revenue / self.spend) if self.spend else 0.0


@dataclass
class FatigueReport:
    creative_id: str
    status: str  # fresh|fatigue-risk|fatigued
    drop_from_peak_ctr: float
    drop_from_peak_roas: float
    exposure_index: float
    notes: Optional[str] = None


@dataclass
class VariantProposal:
    creative_id: str
    idea_title: str
    new_hook: Optional[str] = None
    new_overlay_text: Optional[str] = None
    new_body_text: Optional[str] = None
    rationale: Optional[str] = None
    compliance_flags: List[str] = field(default_factory=list)
    estimated_uplift: Optional[float] = None


@dataclass
class AgentAction:
    action_type: str  # rotate_asset|update_copy|pause_ad
    target_platform: str
    target_id: str  # ad_id or creative_id
    params: Dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    executed: bool = False
    result_message: Optional[str] = None


@dataclass
class EmbeddingVector:
    creative_id: str
    vector: List[float]
    model: str = "text-embedding-3-small"


@dataclass
class VisualFeaturesModel:
    creative_id: str
    width: int
    height: int
    ahash: str
    dhash: str
    dominant_colors: List[str]
    avg_brightness: float
    entropy: float
    overlay_text: str
    overlay_density: float


@dataclass
class ABTest:
    """A/B Testing experiment"""
    test_id: str
    client_id: str
    platform: str
    test_name: str
    test_type: str  # creative|copy|audience|budget
    status: str  # draft|running|paused|completed
    variant_a_id: str  # creative_id or ad_id
    variant_b_id: str
    variant_c_id: Optional[str] = None
    variant_d_id: Optional[str] = None
    traffic_split: Dict[str, float] = field(default_factory=lambda: {"a": 0.5, "b": 0.5})  # percentage per variant
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    winner: Optional[str] = None  # a|b|c|d
    confidence_level: Optional[float] = None  # statistical significance
    metrics: Dict[str, Any] = field(default_factory=dict)  # results per variant
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
