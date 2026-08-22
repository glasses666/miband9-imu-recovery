import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ota_preflight_guard import PreflightBlocked, build_summary, classify_ota_zip, enforce_actions


class OtaPreflightGuardTests(unittest.TestCase):
    def make_ota_zip(self) -> Path:
        tmpdir = Path(tempfile.mkdtemp(prefix="ota-preflight-test-"))
        zip_path = tmpdir / "test_ota.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(
                "ota.json",
                json.dumps(
                    {
                        "sw_version": "1.3.210",
                        "parts": [
                            {"file": "vela_ap.bin", "md5": "0123456789abcdef0123456789abcdef"}
                        ],
                    }
                ),
            )
            zf.writestr("vela_ap.bin", b"patched-copy-placeholder")
        return zip_path

    def test_classifies_vela_ota_zip_without_live_actions(self):
        result = classify_ota_zip(self.make_ota_zip())
        self.assertTrue(result["zip"])
        self.assertTrue(result["has_ota_json"])
        self.assertTrue(result["firmware5_zip_like"])
        self.assertEqual("1.3.210", result["sw_version"])
        self.assertEqual([], result["live_actions_performed"])
        self.assertTrue(result["visible_md5_mentions"])

    def test_local_actions_allowed(self):
        result = enforce_actions(
            [
                "read_local_zip",
                "classify_file",
                "host_admission_check",
                "map_app_session_states",
                "map_mi_fitness_status_path",
                "map_notify_owner_session",
            ]
        )
        self.assertTrue(result["allowed"])
        self.assertEqual([], result["dangerous"])

    def test_live_status_query_requires_explicit_authorization(self):
        with self.assertRaises(PreflightBlocked):
            enforce_actions(["live_dfu_status_query"])
        result = enforce_actions(["live_dfu_status_query"], allow_live_status=True)
        self.assertEqual(["live_dfu_status_query"], result["live_no_body"])

    def test_dangerous_update_actions_are_blocked(self):
        for action in [
            "prepare_transfer",
            "start_transfer",
            "firmware_body",
            "chunk_transfer",
            "validate",
            "upgrade",
            "recovery",
            "factory_mode",
            "app_launch",
            "band_connect_for_ota",
            "notify_firmware_selection",
            "notify_install_broadcast",
            "mi_fitness_prepare_ota",
            "mi_fitness_start_ota",
            "dfu_prepare_transfer",
            "dfu_start_transfer",
            "dfu_validate",
            "dfu_upgrade",
        ]:
            with self.subTest(action=action):
                with self.assertRaises(PreflightBlocked):
                    enforce_actions([action], allow_live_status=True)

    def test_summary_includes_source_gate_map_for_mi_fitness_and_notify(self):
        summary = build_summary(None, ["map_notify_owner_session", "map_mi_fitness_status_path"], False)
        source_gates = {(entry["source"], entry["gate"]): entry for entry in summary["source_gate_map"]}
        self.assertIn(("mi_fitness", "app_owned_connected_status_only"), source_gates)
        self.assertIn(("notify_nfx", "main_connected_owner_session"), source_gates)
        self.assertIn(("notify_nfx", "firmware5_zip_host_admission"), source_gates)
        self.assertEqual(
            "safe_next_gate_before_firmware_selection",
            source_gates[("notify_nfx", "main_connected_owner_session")]["status"],
        )
        self.assertIn(
            "notify_install_broadcast",
            source_gates[("notify_nfx", "firmware5_zip_host_admission")]["blocked_actions"],
        )


if __name__ == "__main__":
    unittest.main()
