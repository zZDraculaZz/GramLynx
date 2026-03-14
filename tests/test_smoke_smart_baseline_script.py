from __future__ import annotations

import scripts.smoke_smart_baseline as smoke


def test_smoke_script_targets_recommended_baseline_profile() -> None:
    assert smoke.HOST == "127.0.0.1"
    assert smoke.PORT == 8010
    assert smoke.HEALTH_URL.endswith("/health")
    assert smoke.CLEAN_URL.endswith("/clean")
    assert len(smoke.SAMPLE_REQUESTS) == 3
    assert all(req["mode"] == "smart" for req in smoke.SAMPLE_REQUESTS)
