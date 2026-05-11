from __future__ import annotations

import json

from app.hil.dut_result_receiver import normalize_result_payload, write_result_payload


def test_normalize_result_payload_adds_received_timestamp() -> None:
    normalized = normalize_result_payload({"status": "COMPLETED", "output_fps": 14.8})

    assert normalized["status"] == "COMPLETED"
    assert normalized["output_fps"] == 14.8
    assert normalized["received_at_utc"].endswith("Z")


def test_write_result_payload_persists_json(tmp_path) -> None:
    result_path = tmp_path / "dut_result.json"

    payload = write_result_payload(
        result_path,
        {
            "run_id": "run_demo_001",
            "metrics": {"output_fps": 12.4, "detection_count": 42},
        },
    )

    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload == persisted
    assert persisted["run_id"] == "run_demo_001"
    assert persisted["metrics"]["output_fps"] == 12.4
    assert persisted["metrics"]["detection_count"] == 42
