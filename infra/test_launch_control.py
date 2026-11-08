import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from launch_control import bundle, checkpoint_cursor, forecast, json_file, observe, unwrap


class LaunchControlTests(unittest.TestCase):
    def setUp(self):
        self.record = dict(job_id="main_pinned", source_commit="a" * 40,
                           planned_tasks=3, launcher_sha256="b" * 64,
                           lower_seconds=600, expected_seconds=750, upper_seconds=900)
        self.job = dict(job_id="main_pinned", source_sha256="b" * 64, state="running")

    def test_active_job_never_resubmitted(self):
        for state in ("queued", "running", "pending"):
            self.job["state"] = state
            result = observe(self.record, self.job, {"cursor": 1})
            self.assertFalse(result["automatic_resubmit"])
            self.assertEqual(result["next_action"], "OBSERVE_EXISTING_JOB")
            self.assertEqual(result["execution_observed"], state == "running")

    def test_identity_mismatch_is_not_another_run(self):
        for field in ("job_id", "source_sha256"):
            job = dict(self.job, **{field: "other"})
            with self.assertRaises(ValueError):
                observe(self.record, job)

    def test_disconnect_does_not_mean_stopped(self):
        self.job["state"] = "unknown"
        result = observe(self.record, self.job)
        self.assertFalse(result["automatic_resubmit"])
        self.assertEqual(result["next_action"], "RESTORE_STATUS_ACCESS_WITHOUT_RESUBMIT")

    def test_cursor_from_partial_checkpoint_not_nested_state(self):
        self.assertEqual(checkpoint_cursor({"text": '{"active":null,"cursor":2,"row_hashes":[', "offset": 0}), 2)
        self.assertIsNone(checkpoint_cursor({"text": '{"active":{"cursor":100,"x":', "offset": 0}))
        self.assertIsNone(checkpoint_cursor({"text": '{"cursor":2}', "offset": 50}))
        with self.assertRaises(ValueError):
            observe(self.record, self.job, {"cursor": 4})

    def test_no_process_file_while_running_is_normal(self):
        self.assertEqual(observe(self.record, self.job)["next_action"], "OBSERVE_EXISTING_JOB")

    def test_reprocessing_old_input_does_not_invent_fresh_observation(self):
        self.assertIsNone(observe(self.record, self.job)["observed_at_utc"])
        self.assertEqual(observe(self.record, self.job, observed_at="2026-11-08T14:00:00Z")["observed_at_utc"], "2026-11-08T14:00:00Z")

    def test_exit_zero_is_not_scientific_validation(self):
        self.job.update(state="completed", exit_code=0)
        proc = dict(source_commit="a" * 40, exit_code=0, process_wall_seconds=750,
                    run=dict(source_commit="a" * 40, complete=True, technical_pass=True, task_count=3))
        result = observe(self.record, self.job, process=proc)
        self.assertEqual(result["time_and_workload_check"], "WITHIN_RANGE")
        self.assertFalse(result["scientific_confirmation"])
        proc["run"]["task_count"] = 2
        result = observe(self.record, self.job, process=proc)
        self.assertEqual(result["time_and_workload_check"], "REVIEW_REQUIRED")
        proc["run"]["task_count"] = 3
        proc["process_wall_seconds"] = 50
        self.assertEqual(observe(self.record, self.job, process=proc)["time_and_workload_check"], "REVIEW_REQUIRED")

    def test_missing_final_report_requests_reading_not_relaunch(self):
        self.job["state"] = "completed"
        result = observe(self.record, self.job)
        self.assertEqual(result["next_action"], "READ_PROCESS_AND_LOGS")
        self.assertFalse(result["automatic_resubmit"])

    def test_tool_errors_and_partial_files_are_not_json_success(self):
        raw = {"content": [{"type": "text", "text": json.dumps(self.job)}], "structuredContent": None}
        self.assertEqual(unwrap(raw), self.job)
        with self.assertRaises(ValueError):
            unwrap(dict(raw, isError=True))
        with self.assertRaises(ValueError):
            unwrap({"content": [{"type": "text", "text": "Operation failed"}]})
        with self.assertRaises(ValueError):
            json_file({"path": "result", "text": '{"ok":true}', "next_offset": 20})

    def test_bundle_roundtrip_and_refuse_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "code.py"
            p.write_bytes(b"print('pinned')\n")
            raw = p.read_bytes()
            sha1 = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            receipt = dict(source_commit="a" * 40, github_tree_sha="tree", files={"code.py": hashlib.sha256(raw).hexdigest()}, git_blobs={"code.py": sha1})
            tree = dict(sha="tree", truncated=False, tree=[dict(path="code.py", type="blob", sha=sha1)])
            packed = bundle(tmp, receipt, tree)
            self.assertEqual(json.loads(zlib.decompress(base64.b64decode(packed["zlib_base64"]))), {"code.py": raw.decode()})
            self.assertEqual(packed, bundle(tmp, receipt, tree))
            with self.assertRaises(ValueError):
                bundle(tmp, receipt, dict(tree, truncated=True))
            p.write_text("modified")
            with self.assertRaises(ValueError):
                bundle(tmp, receipt, tree)

    def calibration(self):
        return dict(source_commit="a" * 40, exit_code=0, process_wall_seconds=5,
                    run=dict(complete=True, technical_pass=True, phase="calibrate", task_count=2,
                             source_digest="s", config_digest="c", environment_fingerprint="e"),
                    rows=[dict(stratum="slow", task_compute_seconds=3), dict(stratum=None, task_compute_seconds=1)])

    def test_stratified_forecast_keeps_measured_slow_work(self):
        tasks = [dict(case_id="base")] + [dict(case_id="slow_case") for _ in range(10)]
        result = forecast(tasks, {"slow_case": "slow"}, self.calibration(), dict(tasks=1, seconds=2, reference="pinned base"))
        self.assertEqual(result["expected_seconds"], 37.5)
        self.assertFalse(result["admission_granted"])

    def test_missing_stratum_and_changed_base_do_not_invent_runtime(self):
        for strata, count in [({"x": "unmeasured"}, 0), ({}, 0)]:
            with self.assertRaises(ValueError):
                forecast([dict(case_id="x")], strata, self.calibration(), dict(tasks=count, seconds=2, reference="pinned base"))

    def test_failed_or_impossible_calibration_is_rejected(self):
        for change in ("failed", "parallel", "missing"):
            cal = deepcopy(self.calibration())
            if change == "failed": cal["exit_code"] = 1
            if change == "parallel": cal["process_wall_seconds"] = 1
            if change == "missing": cal["rows"].pop()
            with self.assertRaises(ValueError):
                forecast([dict(case_id="base")], {}, cal, dict(tasks=1, seconds=2, reference="pinned base"))


if __name__ == "__main__":
    unittest.main()
