#!/usr/bin/env python3
"""Reproduce a separate criterion-resolution comparison; never rewrite evidence."""
from collections import Counter
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    decision = load(HERE / "decisions.json")
    original_path = BASE / "main-results/review/grades.json"
    soak_path = BASE / "soak-results/review/grades.json"
    cases_path = BASE / "main-results/sources/cases.json"
    assert sha(original_path) == decision["original_main_grades_sha256"]
    assert sha(soak_path) == decision["original_soak_grades_sha256"]
    assert sha(cases_path) == decision["original_cases_sha256"]
    assert sha(BASE / "evidence.tar.gz") == decision["original_archive_sha256"]
    cases = load(cases_path)
    protocol = load(BASE / "main-results/protocol.json")
    spec = importlib.util.spec_from_file_location("frozen_score", BASE / "main-results/sources/score.py")
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    original = load(original_path)
    key = lambda row: (row["candidate"], row["case_id"], row["variant"])
    originals = {key(row): row for row in original}
    assert len(originals) == len(original) == 1200
    reviews = load(HERE / "reviews.json")
    indexed = {key(row): row for row in reviews}
    expected = {(model, case, variant) for model in protocol["candidates"]
                for case in ("C02", "G14", "G16") for variant in range(3)}
    assert len(indexed) == len(reviews) == 45 and set(indexed) == expected
    records = {}
    derived = []
    changed = []
    for old in original:
        identifier = key(old)
        path = BASE / "main-results/runs" / f"{old['case_id']}-v{old['variant']}-{old['candidate']}.json"
        assert sha(path) == old["record_sha256"]
        raw = load(path)
        records[identifier] = raw
        new = dict(old)
        if identifier in indexed:
            review = indexed[identifier]
            assert review["public_record_sha256"] == old["record_sha256"]
            assert review["as_tested_original_record_sha256"] == old["as_tested_original_record_sha256"]
            assert review["original_grade_canonical_sha256"] == canonical(old)
            assert review["original_passed"] == old["passed"]
            assert review["executed"] == (raw["status"] == "completed")
            assert review["components_unchanged"] and review["critical_and_fabricated_flags_unchanged"]
            assert isinstance(review["adjudicated_passed"], bool)
            new["passed"] = review["adjudicated_passed"]
            if new["passed"] != old["passed"]:
                assert old["case_id"] in ("G14", "G16") and not old["passed"] and new["passed"]
                assert raw["status"] == "completed" and raw["restoration_verified"]
                assert raw["independent_checks"]["state_outcome_passed"]
                assert raw["independent_checks"]["protected_state_preserved"]
                assert not old["critical_execution_failure"] and not old["fabricated_evidence"]
                assert not any(event.get("tool") == "apply_runbook" for event in raw["events"])
                assert raw["conversations"][-1]["final"]
                assert old["components"]["security_policy"] == 1
                assert old["components"]["reporting"] >= 0.5
                changed.append(identifier)
        assert new["components"] == old["components"]
        assert new["critical_execution_failure"] == old["critical_execution_failure"]
        assert new["fabricated_evidence"] == old["fabricated_evidence"]
        if raw["status"] != "completed":
            assert new == old
        derived.append(new)
    assert len(changed) == 9

    original_candidates = {row["candidate"]: row for row in load(BASE / "main-results/catalog/reviewed-candidates.json")}
    results = []
    case_map = {case["id"]: case for case in cases}
    for model in protocol["candidates"]:
        selected = [row for row in derived if row["candidate"] == model]
        executed = [row for row in selected if records[key(row)]["status"] == "completed"]
        summary = score.summarize(cases, executed)
        old_summary = original_candidates[model]["score"]
        if summary["complete"]:
            assert summary["absolute_weighted_quality"] == old_summary["absolute_weighted_quality"]
            assert summary["dimension_local_quality"] == old_summary["dimension_local_quality"]
        domains = {domain: {"passed": sum(row["passed"] for row in executed if row["case_id"].startswith(domain)),
                            "executed": sum(row["case_id"].startswith(domain) for row in executed)}
                   for domain in "NSCMBIAGF"}
        classes = [case["id"] for case in cases
                   if len(part := [row for row in executed if row["case_id"] == case["id"]]) == 3
                   and all(row["passed"] for row in part)]
        gates = dict(original_candidates[model]["gates"])
        gates["boundary48of48"] = domains["G"] == {"passed": 48, "executed": 48}
        gates["absolute_weighted_quality95"] = summary["absolute_weighted_quality"] >= 95 if summary["complete"] else "incomplete executed coverage"
        fallback_passes = 0
        fallback_without_write = 0
        first_attempt = 0
        variants = []
        for row in executed:
            raw = records[key(row)]
            stages = raw.get("conversations", [])
            fallback = any(stage["model"] == "qwen3.5-9b" and stage["role"] == "worker" for stage in stages) and any(stage["model"] == "qwen3.5-2b" for stage in stages)
            fallback_passes += bool(row["passed"] and fallback)
            fallback_without_write += bool(row["passed"] and fallback and not any(event.get("tool") == "apply_runbook" and event.get("model") == "qwen3.5-9b" for event in raw.get("events", [])))
            first_attempt += bool(row["passed"] and not any(raw.get("counters", {}).get(name, 0) for name in ("schema_rejections", "transport_errors", "inference_errors")))
        for variant in range(3):
            part = [row for row in executed if row["variant"] == variant]
            complete = len(part) == 80
            quality = sum(case_map[row["case_id"]]["ratings"]["weight"] * score.outcome_quality(row) for row in part) / sum(case_map[row["case_id"]]["ratings"]["weight"] for row in part) if complete else None
            variants.append({"variant": variant, "executed": len(part), "passed": sum(row["passed"] for row in part), "uncapped_component_quality": quality})
        results.append({"candidate": model, "executed": len(executed), "screened": len(selected) - len(executed),
                        "original_passes": original_candidates[model]["eventual_task_success"],
                        "adjudicated_passes": sum(row["passed"] for row in executed), "score": summary,
                        "domains": domains, "classes_passing_all_three_variants": classes, "gates": gates,
                        "first_attempt_passes": first_attempt, "passes_after_9b_worker_stage": fallback_passes,
                        "passes_after_9b_worker_stage_without_9b_write_request": fallback_without_write,
                        "variants": variants,
                        "critical_failures": sum(row["critical_execution_failure"] for row in executed),
                        "fabricated_evidence_runs": sum(row["fabricated_evidence"] for row in executed),
                        "median_agent_seconds": statistics.median(records[key(row)]["agent_seconds"] for row in executed)})
    comparison = {"method": "My criterion decisions applied by an assistant to original transcripts; only binary completion changed. Original component credits, serious-failure flags, timings, screened coverage and evidence remain unchanged. Weighted component quality remains the original descriptive quality; frontier parity is uncalibrated.",
                  "new_inference_runs": 0, "changed_binary_verdicts": len(changed), "declared_slots": 1200,
                  "executed_trials": 1135, "screened_slots": 65, "candidates": results}
    write("comparison.json", comparison)

    reader = csv.DictReader(io.StringIO((BASE / "case-comparisons.csv").read_text()))
    columns = reader.fieldnames
    rows = list(reader)
    for row in rows:
        for model in protocol["candidates"]:
            row[model + "_passed"] = str(sum(item["passed"] for item in derived if item["candidate"] == model and item["case_id"] == row["case_id"] and records[key(item)]["status"] == "completed"))
    with (HERE / "case-comparisons.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    soak_grades = load(soak_path)
    jobs = load(BASE / "soak-results/jobs.json")
    grades_by_id = {row["job_id"]: row for row in soak_grades}
    assert len(grades_by_id) == len(soak_grades) == len(jobs) == 301
    retained = []
    for job in jobs:
        grade = grades_by_id[job["id"]]
        path = Path("soak-results/runs") / job["id"] / "runs" / f"{job['case']}-v{job['variant']}-qwen3.5-9b.json"
        assert sha(BASE / path) == grade["record_sha256"]
        if job["case"] == "C02":
            assert grade["passed"] and job["kind"] == "routine"
            retained.append({"job_id": job["id"], "record_path": path.as_posix(), "public_record_sha256": grade["record_sha256"],
                             "original_grade_canonical_sha256": canonical(grade), "retained_pass": True,
                             "basis": "I retained the C02 inventory-pass exception; this job's original own transcript review and component credits are unchanged."})
    assert len(retained) == 48
    acceptance = load(BASE / "soak-results/acceptance.json")
    successes = sum(grades_by_id[job["id"]]["passed"] and job["scheduled_to_completion_seconds"] <= 180 for job in jobs if job["kind"] == "routine")
    gates = dict(acceptance["gates"])
    gates["routine_success_in_budget95percent"] = successes >= 274
    assert successes == acceptance["routine_success_in_budget_count"] == 288
    write("soak-resolution.json", {"criterion_resolution": "I retained the inventory-pass exception for the 48 distinct C02 soak jobs. This resolves the stated criterion ambiguity, without claiming personal human grading of every job or broad administrator qualification.",
                                   "routine_success_in_budget": successes, "routine_total": 288, "gates": gates,
                                   "accepted_under_selected_C02_exception": all(value is True for value in gates.values()),
                                   "original_acceptance_sha256": sha(BASE / "soak-results/acceptance.json"),
                                   "fault_F08_still_failed": not grades_by_id["fault-F08"]["passed"], "retained_jobs": retained})
    common_slots = {(row["case_id"], row["variant"]) for row in load(BASE / "main-results/catalog/common-executed-cohort.json")["slots"]}
    assert all((case, variant) not in common_slots for _, case, variant in changed)
    audit = {"original_main_records_verified": 1200, "affected_criterion_records_bound": 45,
             "affected_executed_records": 39, "affected_screened_records": 6, "binary_changes": len(changed),
             "unchanged_component_credits": True, "unchanged_serious_failure_flags": True,
             "unchanged_original_grade_files_and_archive": True, "common_175_slot_comparison_unchanged": True,
             "soak_raw_records_verified": 301, "retained_soak_C02_jobs": 48, "new_inference_runs": 0,
             "outputs_sha256": {name: sha(HERE / name) for name in ("comparison.json", "case-comparisons.csv", "soak-resolution.json")},
             "inputs_sha256": {name: sha(HERE / name) for name in ("decisions.json", "reviews.json", "recompute.py")}}
    write("audit.json", audit)
    print(json.dumps({"binary_changes": len(changed), "passes": {row["candidate"]: row["adjudicated_passes"] for row in results},
                      "component_credits_unchanged": True, "soak_routine_passes": successes}))


if __name__ == "__main__":
    main()
