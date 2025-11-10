"""A/B Testing Module - Manages experiments and statistical analysis"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import asdict
import pandas as pd
import numpy as np

from ..models import ABTest
from ..db.bq_client import BigQueryClient
from ..utils.logging import get_logger

log = get_logger(__name__)


class ABTestManager:
    """Manages A/B testing experiments"""

    def __init__(self, bq_client: BigQueryClient):
        self.bq = bq_client
        self._cache: Dict[str, ABTest] = {}

    def create_test(
        self,
        client_id: str,
        platform: str,
        test_name: str,
        test_type: str,
        variant_a_id: str,
        variant_b_id: str,
        variant_c_id: Optional[str] = None,
        variant_d_id: Optional[str] = None,
        traffic_split: Optional[Dict[str, float]] = None,
    ) -> ABTest:
        """Create a new A/B test"""
        test_id = str(uuid.uuid4())

        # Default 50/50 split or evenly distribute
        if not traffic_split:
            num_variants = 2 + (1 if variant_c_id else 0) + (1 if variant_d_id else 0)
            split_pct = 1.0 / num_variants
            traffic_split = {"a": split_pct, "b": split_pct}
            if variant_c_id:
                traffic_split["c"] = split_pct
            if variant_d_id:
                traffic_split["d"] = split_pct

        test = ABTest(
            test_id=test_id,
            client_id=client_id,
            platform=platform,
            test_name=test_name,
            test_type=test_type,
            status="draft",
            variant_a_id=variant_a_id,
            variant_b_id=variant_b_id,
            variant_c_id=variant_c_id,
            variant_d_id=variant_d_id,
            traffic_split=traffic_split,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self._cache[test_id] = test
        log.info("Created A/B test: %s", test_id)
        return test

    def start_test(self, test_id: str) -> bool:
        """Start an A/B test"""
        test = self._cache.get(test_id)
        if not test:
            log.error("Test not found: %s", test_id)
            return False

        test.status = "running"
        test.start_date = datetime.now()
        test.updated_at = datetime.now()

        log.info("Started A/B test: %s", test_id)
        return True

    def pause_test(self, test_id: str) -> bool:
        """Pause an A/B test"""
        test = self._cache.get(test_id)
        if not test:
            log.error("Test not found: %s", test_id)
            return False

        test.status = "paused"
        test.updated_at = datetime.now()

        log.info("Paused A/B test: %s", test_id)
        return True

    def complete_test(self, test_id: str, winner: Optional[str] = None) -> bool:
        """Complete an A/B test"""
        test = self._cache.get(test_id)
        if not test:
            log.error("Test not found: %s", test_id)
            return False

        test.status = "completed"
        test.end_date = datetime.now()
        test.winner = winner
        test.updated_at = datetime.now()

        log.info("Completed A/B test: %s (winner: %s)", test_id, winner)
        return True

    def analyze_test(
        self,
        test_id: str,
        performance_data: pd.DataFrame,
        metric: str = "ctr",
        confidence_level: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Analyze A/B test results with statistical significance

        Args:
            test_id: Test ID
            performance_data: DataFrame with performance metrics
            metric: Metric to analyze (ctr, cvr, roas, cpa)
            confidence_level: Confidence level for statistical test (default 0.95)

        Returns:
            Analysis results with winner, p-value, confidence intervals
        """
        test = self._cache.get(test_id)
        if not test:
            log.error("Test not found: %s", test_id)
            return {}

        try:
            # Get variant IDs
            variants = {
                "a": test.variant_a_id,
                "b": test.variant_b_id,
            }
            if test.variant_c_id:
                variants["c"] = test.variant_c_id
            if test.variant_d_id:
                variants["d"] = test.variant_d_id

            # Calculate metrics for each variant
            results = {}
            for variant_name, creative_id in variants.items():
                variant_data = performance_data[performance_data["creative_id"] == creative_id]

                if variant_data.empty:
                    results[variant_name] = {
                        "creative_id": creative_id,
                        "metric_value": 0,
                        "sample_size": 0,
                        "std_error": 0,
                    }
                    continue

                # Calculate metric
                total_impressions = variant_data["impressions"].sum()
                total_clicks = variant_data["clicks"].sum()
                total_conversions = variant_data["conversions"].sum()
                total_spend = variant_data["spend"].sum()
                total_revenue = variant_data.get("revenue", pd.Series([0])).sum()

                if metric == "ctr":
                    metric_value = (total_clicks / total_impressions) if total_impressions > 0 else 0
                    sample_size = total_impressions
                elif metric == "cvr":
                    metric_value = (total_conversions / total_clicks) if total_clicks > 0 else 0
                    sample_size = total_clicks
                elif metric == "cpa":
                    metric_value = (total_spend / total_conversions) if total_conversions > 0 else 0
                    sample_size = total_conversions
                elif metric == "roas":
                    metric_value = (total_revenue / total_spend) if total_spend > 0 else 0
                    sample_size = int(total_spend)  # Using spend as proxy for sample
                else:
                    metric_value = 0
                    sample_size = 0

                # Calculate standard error
                if metric in ["ctr", "cvr"] and sample_size > 0:
                    std_error = np.sqrt((metric_value * (1 - metric_value)) / sample_size)
                else:
                    std_error = 0

                results[variant_name] = {
                    "creative_id": creative_id,
                    "metric_value": metric_value,
                    "sample_size": sample_size,
                    "std_error": std_error,
                    "impressions": int(total_impressions),
                    "clicks": int(total_clicks),
                    "conversions": int(total_conversions),
                    "spend": float(total_spend),
                    "revenue": float(total_revenue),
                }

            # Perform statistical test (Z-test for proportions)
            winner = None
            p_value = 1.0

            if len(results) >= 2:
                # Compare variant A with B (simplest case)
                a_data = results.get("a")
                b_data = results.get("b")

                if a_data and b_data and a_data["sample_size"] > 0 and b_data["sample_size"] > 0:
                    p1 = a_data["metric_value"]
                    p2 = b_data["metric_value"]
                    n1 = a_data["sample_size"]
                    n2 = b_data["sample_size"]

                    # Pooled proportion
                    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)

                    # Z-score
                    if p_pool > 0 and p_pool < 1:
                        se_pool = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
                        if se_pool > 0:
                            z_score = (p1 - p2) / se_pool

                            # P-value (two-tailed test)
                            from scipy import stats
                            p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))

                            # Determine winner
                            if p_value < (1 - confidence_level):
                                winner = "a" if p1 > p2 else "b"

            # Update test with results
            test.metrics = results
            test.confidence_level = 1 - p_value if p_value < 1 else 0
            test.winner = winner
            test.updated_at = datetime.now()

            analysis = {
                "test_id": test_id,
                "metric": metric,
                "variants": results,
                "winner": winner,
                "p_value": p_value,
                "confidence_level": test.confidence_level,
                "is_significant": p_value < (1 - confidence_level),
            }

            log.info("Analyzed A/B test %s: winner=%s, p_value=%.4f", test_id, winner, p_value)
            return analysis

        except Exception as e:
            log.error("Failed to analyze A/B test %s: %s", test_id, e)
            return {}

    def get_test(self, test_id: str) -> Optional[ABTest]:
        """Get a test by ID"""
        return self._cache.get(test_id)

    def list_tests(self, client_id: Optional[str] = None, status: Optional[str] = None) -> List[ABTest]:
        """List all tests, optionally filtered"""
        tests = list(self._cache.values())

        if client_id:
            tests = [t for t in tests if t.client_id == client_id]

        if status:
            tests = [t for t in tests if t.status == status]

        return tests

    def get_test_summary(self, test_id: str) -> Dict[str, Any]:
        """Get a summary of test results"""
        test = self._cache.get(test_id)
        if not test:
            return {}

        return {
            "test_id": test.test_id,
            "test_name": test.test_name,
            "platform": test.platform,
            "status": test.status,
            "winner": test.winner,
            "confidence_level": test.confidence_level,
            "metrics": test.metrics,
            "start_date": test.start_date.isoformat() if test.start_date else None,
            "end_date": test.end_date.isoformat() if test.end_date else None,
        }
