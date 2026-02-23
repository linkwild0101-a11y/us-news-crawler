#!/usr/bin/env python3
"""Feature flag helpers shared by stock pipelines."""

from __future__ import annotations

import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes", "on"}


def read_bool_env(name: str, default: bool = False) -> bool:
    """Read boolean flag from env with safe defaults."""
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in TRUE_VALUES


@dataclass(frozen=True)
class FeatureFlags:
    """Runtime feature flags for incremental V3 rollout."""

    enable_stock_v3_run_log: bool = False
    enable_stock_v3_eval: bool = False
    enable_stock_v3_paper: bool = False
    enable_stock_v3_challenger: bool = False
    enable_stock_v3_drift: bool = False
    enable_stock_v3_lifecycle: bool = False
    enable_stock_v3_subscription_alert: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        """Build feature flag config from process environment."""
        return cls(
            enable_stock_v3_run_log=read_bool_env("ENABLE_STOCK_V3_RUN_LOG", default=False),
            enable_stock_v3_eval=read_bool_env("ENABLE_STOCK_V3_EVAL", default=False),
            enable_stock_v3_paper=read_bool_env("ENABLE_STOCK_V3_PAPER", default=False),
            enable_stock_v3_challenger=read_bool_env(
                "ENABLE_STOCK_V3_CHALLENGER",
                default=False,
            ),
            enable_stock_v3_drift=read_bool_env("ENABLE_STOCK_V3_DRIFT", default=False),
            enable_stock_v3_lifecycle=read_bool_env("ENABLE_STOCK_V3_LIFECYCLE", default=False),
            enable_stock_v3_subscription_alert=read_bool_env(
                "ENABLE_STOCK_V3_SUBSCRIPTION_ALERT",
                default=False,
            ),
        )
