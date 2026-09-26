"""
UrbanSense AI — Traffic Intelligence Package (Milestone 5)
===========================================================
SOURCE OF TRUTH: URBANSENSE_FINAL_MASTER_IMPLEMENTATION_PLAN.md (R4 Phase 19)

Modules:
- aggregator: Aggregates tracked vehicle observations into windowed traffic metrics.
- bottleneck: Evaluates the rolling 3-window bottleneck condition.
"""
from backend.app.traffic.aggregator import TrafficAggregator
from backend.app.traffic.bottleneck import BottleneckEngine

__all__ = ["TrafficAggregator", "BottleneckEngine"]
