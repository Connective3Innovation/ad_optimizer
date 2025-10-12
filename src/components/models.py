from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Dict, Any


@dataclass
class Creative:
    creative_id: str
    platform: str  # meta|tiktok|google
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
