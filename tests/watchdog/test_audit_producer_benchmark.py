import json
from pathlib import Path

from cascade.watchdog.audit_projection import MAX_SOURCE_BYTES
from tests.watchdog.benchmark_audit_producer import run


def test_representative_large_ledger_records_bounded_producer_work(
    tmp_path: Path,
) -> None:
    evidence = run(tmp_path)

    assert evidence["fixture"] == {
        "attempts": 10_000,
        "incident_rows": 100,
        "owners": 17,
        "generations": 100,
        "malformed_rows": 20,
        "source_bytes": evidence["fixture"]["source_bytes"],
    }
    assert evidence["fixture"]["source_bytes"] <= MAX_SOURCE_BYTES
    assert evidence["enforced_ceilings"] == {
        "candidates_per_pass": 100,
        "pass_seconds": 60,
        "candidate_seconds": 2,
    }
    assert evidence["producer"]["pages"] == 3
    assert evidence["producer"]["serialized_page_bytes"] > 0


def test_recorded_large_ledger_evidence_discloses_environment_and_limitations(
) -> None:
    baseline = (
        Path(__file__).parent
        / "baselines"
        / "task_044_001_004_audit_producer.json"
    )
    evidence = json.loads(baseline.read_text(encoding="utf-8"))

    assert evidence["fixture"]["attempts"] == 10_000
    assert evidence["environment"]["python"]
    assert evidence["environment"]["platform"]
    assert evidence["producer"]["elapsed_seconds"] > 0
    assert evidence["limitations"]
