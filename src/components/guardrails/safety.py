from __future__ import annotations

from typing import List, Optional
from ..config import Settings
from ..models import VariantProposal
from ..utils.logging import get_logger


log = get_logger(__name__)


BLOCKLIST = [
    "cure", "guarantee", "clickbait", "shockingly", "you won't believe",
]


def _use_openai_moderation(settings: Settings) -> bool:
    try:
        import openai  # noqa: F401
        return bool(settings.openai_api_key)
    except Exception:
        return False


def check_compliance(settings: Settings, text: str, platform: str) -> List[str]:
    flags: List[str] = []
    lower = (text or "").lower()
    for bad in BLOCKLIST:
        if bad in lower:
            flags.append(f"blocklist:{bad}")

    # Optionally use OpenAI moderations for extra signals
    if _use_openai_moderation(settings):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            # Use text-moderation-latest endpoint via responses or moderation API
            result = client.moderations.create(
                model="omni-moderation-latest",
                input=text,
            )
            categories = result.results[0].categories
            for k, v in categories.items():
                if v:
                    flags.append(f"moderation:{k}")
        except Exception as e:
            log.warning("Moderation call failed: %s", e)

    return flags


def approve_variant(settings: Settings, proposal: VariantProposal, platform: str, guidelines: Optional[str]) -> VariantProposal:
    combined_text = " ".join(
        filter(None, [proposal.new_hook, proposal.new_overlay_text, proposal.new_body_text])
    )
    flags = check_compliance(settings, combined_text, platform)
    if guidelines:
        # Very simple guideline checks (brand terms, tone, etc.) can be added here
        pass
    proposal.compliance_flags = flags
    return proposal

