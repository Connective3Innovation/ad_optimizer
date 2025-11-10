from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ..config import Settings
from ..db.bq_client import BigQueryClient
from ..models import AgentAction
from ..utils.logging import get_logger


log = get_logger(__name__)


class ApprovalQueue:
    def __init__(self, settings: Settings):
        """
        Initialize the approval queue.

        :param settings: The application settings.
        """
        self.settings = settings
        self.cache_path = settings.repo_root / ".cache"
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.cache_path / "approval_queue.json"
        if not self.queue_file.exists():
            self.queue_file.write_text("[]", encoding="utf-8")

    def _load(self) -> List[AgentAction]:
        raw = json.loads(self.queue_file.read_text(encoding="utf-8"))
        return [AgentAction(**item) for item in raw]

    def _save(self, items: List[AgentAction]) -> None:
        self.queue_file.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2))

    def list(self) -> List[AgentAction]:
        return self._load()

    def add(self, action: AgentAction) -> None:
        items = self._load()
        items.append(action)
        self._save(items)

    def approve(self, idx: int, approved: bool = True) -> Optional[AgentAction]:
        items = self._load()
        if 0 <= idx < len(items):
            items[idx].approved = approved
            self._save(items)
            return items[idx]
        return None

    def execute(self, idx: int) -> Optional[AgentAction]:
        items = self._load()
        if 0 <= idx < len(items):
            action = items[idx]
            if not action.approved:
                action.result_message = "Not approved"
                self._save(items)
                return action
            # Simulate execution (dry-run or no-op)
            action.executed = True
            action.result_message = f"Executed {action.action_type} on {action.target_platform}:{action.target_id}"
            items[idx] = action
            self._save(items)
            return action
        return None

    def clear(self) -> None:
        """Clear all actions from the queue"""
        self._save([])


def actions_from_fatigue(perf_with_flags: pd.DataFrame, platform: str) -> List[AgentAction]:
    actions: List[AgentAction] = []
    for _, r in perf_with_flags.iterrows():
        cid = str(r["creative_id"]) if "creative_id" in r else None
        if not cid:
            continue
        status = r.get("status", "fresh")
        if status == "fatigued":
            actions.append(AgentAction(
                action_type="pause_ad",
                target_platform=platform,
                target_id=cid,
                params={"reason": "fatigued"},
            ))
        elif status == "fatigue-risk":
            actions.append(AgentAction(
                action_type="update_copy",
                target_platform=platform,
                target_id=cid,
                params={"reason": "fatigue-risk"},
            ))
    return actions


def persist_actions_bq(bq: BigQueryClient, actions: List[AgentAction]) -> None:
    if not actions:
        return
    if not bq.enabled:
        return
    try:
        df = pd.DataFrame([
            {
                "action_type": a.action_type,
                "target_platform": a.target_platform,
                "target_id": a.target_id,
                "params": json.dumps(a.params, ensure_ascii=False),
                "approved": a.approved,
                "executed": a.executed,
                "result_message": a.result_message,
                "created_at": datetime.utcnow().isoformat(),
            }
            for a in actions
        ])
        bq.ensure_dataset_and_tables()
        bq._client.load_table_from_dataframe(df, bq._table_ref("actions")).result()
    except Exception as e:
        log.warning("Failed to persist actions to BQ: %s", e)

