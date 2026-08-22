import unittest

from miband9ctl.cli import (
    app_log_lines_for_nonce,
    app_log_reported_error,
    build_parser,
    normalize_global_args,
    parse_bluetooth_manager_dump,
    parse_connect_log,
    parse_find_band_log,
    parse_gamesir_probe_log,
    parse_gb_sport_xms_open_log,
    parse_gb_sport_xms_stop_log,
    parse_known_devices_log,
    parse_package_dump,
    parse_pair_log,
    parse_port_probe_log,
    parse_scan_log,
    parse_sport_xms_probe_log,
    redacted_extras,
)


class CliParsingTest(unittest.TestCase):
    def test_global_json_allowed_after_command(self):
        args = build_parser().parse_args(normalize_global_args(["doctor", "--json"]))
        self.assertEqual("doctor", args.cmd)
        self.assertTrue(args.json)

    def test_global_serial_allowed_after_nested_command(self):
        args = build_parser().parse_args(normalize_global_args(["app", "ping", "--serial", "c8f9a1da"]))
        self.assertEqual("app", args.cmd)
        self.assertEqual("ping", args.app_cmd)
        self.assertEqual("c8f9a1da", args.serial)

    def test_read_only_state_commands_parse(self):
        parser = build_parser()
        phone = parser.parse_args(normalize_global_args(["phone", "info", "--json"]))
        bluetooth = parser.parse_args(normalize_global_args(["bluetooth", "state", "--json"]))
        app = parser.parse_args(normalize_global_args(["app", "state", "--json"]))
        known = parser.parse_args(normalize_global_args(["app", "known-devices", "--json"]))
        enable_bt = parser.parse_args(normalize_global_args(["app", "enable-bluetooth", "--json"]))
        state_import = parser.parse_args(normalize_global_args(["state", "import", "--address", "AA:BB:CC:DD:EE:02", "--json"]))
        band_scan = parser.parse_args(normalize_global_args(["band", "scan", "--seconds", "3", "--name", "Xiaomi", "--json"]))
        band_pair = parser.parse_args(normalize_global_args(["band", "pair", "--address", "AA:BB:CC:DD:EE:02", "--json"]))
        band_connect = parser.parse_args(normalize_global_args(["band", "connect", "--address", "AA:BB:CC:DD:EE:02", "--json"]))
        band_port_probe = parser.parse_args(normalize_global_args(["band", "port-probe", "--address", "AA:BB:CC:DD:EE:02", "--ports", "1-5,7", "--hex", "A5A5", "--connect-timeout-ms", "1000", "--read-ms", "250", "--disconnect-first", "--json"]))
        band_find_band = parser.parse_args(normalize_global_args(["band", "find-band", "--address", "AA:BB:CC:DD:EE:02", "--duration-ms", "2500", "--json"]))
        band_mi_find_band = parser.parse_args(normalize_global_args(["band", "mi-find-band", "--did", "DID-REDACTED", "--duration-ms", "2000", "--json"]))
        band_gamesir_probe = parser.parse_args(normalize_global_args(["band", "gamesir-probe", "--seconds", "5", "--name", "GameSir,Nova", "--address", "AA:BB:CC:DD:EE:02", "--capture-ms", "4000", "--handshake", "--bond", "--historical-010103", "--json"]))
        band_sport_xms_probe = parser.parse_args(normalize_global_args(["band", "sport-xms-probe", "--capture-ms", "600000", "--start", "--sport-type", "812", "--did", "DID-REDACTED", "--json"]))
        band_gb_sport_xms_open = parser.parse_args(normalize_global_args(["band", "gb-sport-xms-open", "--capture-ms", "3000", "--sport-type", "812", "--out-dir", "artifacts/AUTO", "--json"]))
        band_gb_sport_xms_stop = parser.parse_args(normalize_global_args(["band", "gb-sport-xms-stop", "--capture-ms", "1000", "--sport-type", "812", "--out-dir", "artifacts/stop", "--json"]))
        band_gb_sport_xms_start_stop = parser.parse_args(normalize_global_args(["band", "gb-sport-xms-start-stop", "--capture-ms", "3000", "--stop-capture-ms", "1500", "--verify-capture-ms", "1000", "--sport-type", "812", "--out-dir", "artifacts/start_stop", "--json"]))
        band_bind = parser.parse_args(normalize_global_args(["band", "bind", "--address", "AA:BB:CC:DD:EE:02", "--reset-bond", "--json"]))
        self.assertEqual(("phone", "info"), (phone.cmd, phone.phone_cmd))
        self.assertEqual(("bluetooth", "state"), (bluetooth.cmd, bluetooth.bluetooth_cmd))
        self.assertEqual(("app", "state"), (app.cmd, app.app_cmd))
        self.assertEqual(("app", "known-devices"), (known.cmd, known.app_cmd))
        self.assertEqual(("app", "enable-bluetooth"), (enable_bt.cmd, enable_bt.app_cmd))
        self.assertEqual(("state", "import"), (state_import.cmd, state_import.state_cmd))
        self.assertEqual(("band", "scan"), (band_scan.cmd, band_scan.band_cmd))
        self.assertEqual(3, band_scan.seconds)
        self.assertEqual("Xiaomi", band_scan.name)
        self.assertEqual(("band", "pair"), (band_pair.cmd, band_pair.band_cmd))
        self.assertEqual("AA:BB:CC:DD:EE:02", band_pair.address)
        self.assertEqual(("band", "connect"), (band_connect.cmd, band_connect.band_cmd))
        self.assertEqual(("band", "port-probe"), (band_port_probe.cmd, band_port_probe.band_cmd))
        self.assertEqual("1-5,7", band_port_probe.ports)
        self.assertEqual("A5A5", band_port_probe.hex)
        self.assertEqual(1000, band_port_probe.connect_timeout_ms)
        self.assertEqual(250, band_port_probe.read_ms)
        self.assertTrue(band_port_probe.disconnect_first)
        self.assertEqual(("band", "find-band"), (band_find_band.cmd, band_find_band.band_cmd))
        self.assertEqual("AA:BB:CC:DD:EE:02", band_find_band.address)
        self.assertEqual(2500, band_find_band.duration_ms)
        self.assertEqual(("band", "mi-find-band"), (band_mi_find_band.cmd, band_mi_find_band.band_cmd))
        self.assertEqual("DID-REDACTED", band_mi_find_band.did)
        self.assertEqual(2000, band_mi_find_band.duration_ms)
        self.assertEqual(("band", "gamesir-probe"), (band_gamesir_probe.cmd, band_gamesir_probe.band_cmd))
        self.assertEqual(5, band_gamesir_probe.seconds)
        self.assertEqual("GameSir,Nova", band_gamesir_probe.name)
        self.assertEqual("AA:BB:CC:DD:EE:02", band_gamesir_probe.address)
        self.assertEqual(4000, band_gamesir_probe.capture_ms)
        self.assertTrue(band_gamesir_probe.handshake)
        self.assertTrue(band_gamesir_probe.bond)
        self.assertTrue(band_gamesir_probe.historical_010103)
        self.assertEqual(("band", "sport-xms-probe"), (band_sport_xms_probe.cmd, band_sport_xms_probe.band_cmd))
        self.assertEqual(600000, band_sport_xms_probe.capture_ms)
        self.assertTrue(band_sport_xms_probe.start)
        self.assertEqual(812, band_sport_xms_probe.sport_type)
        self.assertEqual("DID-REDACTED", band_sport_xms_probe.did)
        self.assertEqual(("band", "gb-sport-xms-open"), (band_gb_sport_xms_open.cmd, band_gb_sport_xms_open.band_cmd))
        self.assertEqual("artifacts/AUTO", band_gb_sport_xms_open.out_dir)
        self.assertEqual(("band", "gb-sport-xms-stop"), (band_gb_sport_xms_stop.cmd, band_gb_sport_xms_stop.band_cmd))
        self.assertEqual("artifacts/stop", band_gb_sport_xms_stop.out_dir)
        self.assertEqual(("band", "gb-sport-xms-start-stop"), (band_gb_sport_xms_start_stop.cmd, band_gb_sport_xms_start_stop.band_cmd))
        self.assertEqual("artifacts/start_stop", band_gb_sport_xms_start_stop.out_dir)
        self.assertEqual(1500, band_gb_sport_xms_start_stop.stop_capture_ms)
        self.assertEqual(1000, band_gb_sport_xms_start_stop.verify_capture_ms)
        self.assertEqual(("band", "bind"), (band_bind.cmd, band_bind.band_cmd))
        self.assertTrue(band_bind.reset_bond)

    def test_app_log_error_is_scoped_to_nonce(self):
        log = '\n'.join([
            'I/MI_HFIMU_ERROR: {"status":"error","nonce":"old"}',
            'I/MI_HFIMU_RESULT: {"status":"ok","nonce":"current"}',
        ])
        current = app_log_lines_for_nonce(log, "current")
        self.assertFalse(app_log_reported_error(current))
        old = app_log_lines_for_nonce(log, "old")
        self.assertTrue(app_log_reported_error(old))
    def test_redacted_extras_hides_did_override(self):
        self.assertEqual(
            {"xms_did": "[REDACTED]", "xms_sport_type": "812"},
            redacted_extras({"xms_did": "869875003", "xms_sport_type": "812"}),
        )


class ReadOnlyStateParsingTest(unittest.TestCase):
    def test_parse_bluetooth_manager_dump_keeps_bonded_devices_without_keys(self):
        dump = """Bluetooth Status
  enabled: true
  state: ON
  address: 00:00:00:00:00:01
  name: LTPTV

AdapterProperties
  Name: LTPTV
  Address: AA:BB:CC:DD:EE:00
  Discovering: false
  Bonded devices:
    AA:BB:CC:DD:EE:01 [BR/EDR] 联想thinkplus-LP40
    AA:BB:CC:DD:EE:02 [ DUAL ] Xiaomi Smart Band 9 test-device
mSnoopLogSettingAtEnable = false
"""
        parsed = parse_bluetooth_manager_dump(dump)
        self.assertTrue(parsed["enabled"])
        self.assertEqual("ON", parsed["state"])
        self.assertEqual("LTPTV", parsed["adapter_name"])
        self.assertFalse(parsed["discovering"])
        self.assertEqual(
            [
                {"address": "AA:BB:CC:DD:EE:01", "transport": "BR/EDR", "name": "联想thinkplus-LP40"},
                {"address": "AA:BB:CC:DD:EE:02", "transport": "DUAL", "name": "Xiaomi Smart Band 9 test-device"},
            ],
            parsed["bonded_devices"],
        )
        self.assertNotIn("auth", str(parsed).lower())
        self.assertNotIn("key", str(parsed).lower())

    def test_parse_package_dump_extracts_install_state(self):
        dump = """Packages:
  Package [nodomain.freeyourgadget.gadgetbridge.hfimucli] (8cda341):
    versionCode=235 minSdk=23 targetSdk=34
    versionName=0.83.0-hfimucli
    firstInstallTime=2026-05-29 12:00:00
    lastUpdateTime=2026-05-29 12:20:00
"""
        parsed = parse_package_dump(dump)
        self.assertTrue(parsed["installed"])
        self.assertEqual("235", parsed["version_code"])
        self.assertEqual("0.83.0-hfimucli", parsed["version_name"])
        self.assertEqual("2026-05-29 12:00:00", parsed["first_install_time"])
        self.assertEqual("2026-05-29 12:20:00", parsed["last_update_time"])

    def test_parse_known_devices_log_extracts_presence_without_values(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"known-devices","device_count":"2",'
            '"device_0_address":"AA:BB:CC:DD:EE:02","device_0_name":"Xiaomi Smart Band 9 test-device",'
            '"device_0_type_name":"XIAOMI_SMART_BAND_9","device_0_model":"M2345B1",'
            '"device_0_credential_present":"true",'
            '"device_1_address":"AA:BB:CC:DD:EE:01","device_1_name":"Other",'
            '"device_1_type_name":"OTHER","device_1_model":"",'
            '"device_1_credential_present":"false"}'
        )
        self.assertEqual(
            [
                {
                    "address": "AA:BB:CC:DD:EE:02",
                    "name": "Xiaomi Smart Band 9 test-device",
                    "type_name": "XIAOMI_SMART_BAND_9",
                    "model": "M2345B1",
                    "credential_present": True,
                },
                {
                    "address": "AA:BB:CC:DD:EE:01",
                    "name": "Other",
                    "type_name": "OTHER",
                    "model": "",
                    "credential_present": False,
                },
            ],
            parse_known_devices_log(log),
        )

    def test_parse_scan_log_extracts_discovered_target_devices(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"scan","message":"scan_complete","device_count":"2",'
            '"device_0_address":"AA:BB:CC:DD:EE:02","device_0_name":"Xiaomi Smart Band 9 test-device",'
            '"device_0_bond_state":"NONE",'
            '"device_1_address":"AA:BB:CC:DD:EE:03","device_1_name":"Xiaomi Band",'
            '"device_1_bond_state":"BONDED"}'
        )
        self.assertEqual(
            [
                {"address": "AA:BB:CC:DD:EE:02", "name": "Xiaomi Smart Band 9 test-device", "bond_state": "NONE"},
                {"address": "AA:BB:CC:DD:EE:03", "name": "Xiaomi Band", "bond_state": "BONDED"},
            ],
            parse_scan_log(log),
        )

    def test_parse_pair_log_extracts_pair_result(self):
        log = (
            'I/MI_HFIMU_RESULT(123): {"status":"ok","command":"pair","message":"service_start_requested"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"pair","message":"pair_complete",'
            '"address":"AA:BB:CC:DD:EE:02","name":"Xiaomi Smart Band 9 test-device",'
            '"bond_state":"BONDED","reset_requested":"true"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "pair_complete",
                "address": "AA:BB:CC:DD:EE:02",
                "name": "Xiaomi Smart Band 9 test-device",
                "bond_state": "BONDED",
                "reset_requested": True,
            },
            parse_pair_log(log),
        )

    def test_parse_connect_log_extracts_initialized_gate(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"connect","message":"device_state",'
            '"address":"AA:BB:CC:DD:EE:02","name":"Xiaomi Smart Band 9 test-device",'
            '"device_state":"AUTHENTICATING","state_ordinal":"8","initialized":"false"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"connect","message":"initialized",'
            '"address":"AA:BB:CC:DD:EE:02","name":"Xiaomi Smart Band 9 test-device",'
            '"device_state":"INITIALIZED","state_ordinal":"9","initialized":"true"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "initialized",
                "address": "AA:BB:CC:DD:EE:02",
                "name": "Xiaomi Smart Band 9 test-device",
                "device_state": "INITIALIZED",
                "state_ordinal": "9",
                "initialized": True,
                "reason": "",
            },
            parse_connect_log(log),
        )

    def test_parse_port_probe_log_extracts_results_without_secrets(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"port-probe","message":"port_result",'
            '"address":"AA:BB:CC:DD:EE:02","port":"5","connected":"true",'
            '"reason":"connected","connect_ms":"321","bytes_written":"30",'
            '"bytes_read":"30","response_hex":"A5A5"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"port-probe","message":"probe_complete",'
            '"address":"AA:BB:CC:DD:EE:02","tested_ports":"2",'
            '"open_ports":"5","open_port_count":"1"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "probe_complete",
                "address": "AA:BB:CC:DD:EE:02",
                "tested_ports": 2,
                "open_ports": [5],
                "open_port_count": 1,
                "reason": "",
                "results": [
                    {
                        "port": 5,
                        "connected": True,
                        "reason": "connected",
                        "connect_ms": 321,
                        "bytes_written": 30,
                        "bytes_read": 30,
                        "response_hex": "A5A5",
                    }
                ],
            },
            parse_port_probe_log(log),
        )

    def test_parse_find_band_log_extracts_start_stop_gate_marker(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"find-band","message":"find_started",'
            '"requested_address":"AA:BB:CC:DD:EE:02","address":"AA:BB:CC:DD:EE:02",'
            '"name":"Xiaomi Smart Band 9 test-device","duration_ms":"2500",'
            '"device_state":"INITIALIZED","state_ordinal":"9","initialized":"true"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"find-band","message":"find_stopped",'
            '"requested_address":"AA:BB:CC:DD:EE:02","address":"AA:BB:CC:DD:EE:02",'
            '"name":"Xiaomi Smart Band 9 test-device","duration_ms":"2500",'
            '"device_state":"INITIALIZED","state_ordinal":"9","initialized":"true"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"find-band","message":"find_complete",'
            '"requested_address":"AA:BB:CC:DD:EE:02","address":"AA:BB:CC:DD:EE:02",'
            '"name":"Xiaomi Smart Band 9 test-device","duration_ms":"2500",'
            '"device_state":"INITIALIZED","state_ordinal":"9","initialized":"true"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "find_complete",
                "requested_address": "AA:BB:CC:DD:EE:02",
                "address": "AA:BB:CC:DD:EE:02",
                "name": "Xiaomi Smart Band 9 test-device",
                "duration_ms": 2500,
                "device_state": "INITIALIZED",
                "state_ordinal": "9",
                "initialized": True,
                "reason": "",
                "started": True,
                "stopped": True,
            },
            parse_find_band_log(log),
        )

    def test_parse_gamesir_probe_log_extracts_state_matrix(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gamesir-probe","message":"scan_candidate",'
            '"address":"AA:BB:CC:DD:EE:02","name":"GameSir-Nova",'
            '"rssi":"-48","bond_state":"BONDED","service_uuids":"8650,1812"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gamesir-probe","message":"gatt_service",'
            '"service_uuid":"00008650-0000-1000-8000-00805f9b34fb",'
            '"char_uuids":"0000865f-0000-1000-8000-00805f9b34fb"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gamesir-probe","message":"write_result",'
            '"char_uuid":"0000865f-0000-1000-8000-00805f9b34fb",'
            '"label":"865F_PRIME","hex":"07","gatt_status":"0"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gamesir-probe","message":"notification",'
            '"char_uuid":"00002a4d-0000-1000-8000-00805f9b34fb",'
            '"elapsed_ms":"321","bytes_read":"8","hex":"0102030405060708"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gamesir-probe","message":"probe_complete",'
            '"target_name":"GameSir,Nova","target_address":"AA:BB:CC:DD:EE:02",'
            '"candidate_count":"1","service_count":"2","write_count":"1",'
            '"notification_count":"1","duration_ms":"4020"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "probe_complete",
                "target_name": "GameSir,Nova",
                "target_address": "AA:BB:CC:DD:EE:02",
                "candidate_count": 1,
                "service_count": 2,
                "write_count": 1,
                "notification_count": 1,
                "duration_ms": 4020,
                "reason": "",
                "candidates": [
                    {
                        "address": "AA:BB:CC:DD:EE:02",
                        "name": "GameSir-Nova",
                        "rssi": -48,
                        "bond_state": "BONDED",
                        "service_uuids": ["8650", "1812"],
                    }
                ],
                "services": [
                    {
                        "service_uuid": "00008650-0000-1000-8000-00805f9b34fb",
                        "char_uuids": ["0000865f-0000-1000-8000-00805f9b34fb"],
                    }
                ],
                "writes": [
                    {
                        "char_uuid": "0000865f-0000-1000-8000-00805f9b34fb",
                        "label": "865F_PRIME",
                        "hex": "07",
                        "gatt_status": 0,
                    }
                ],
                "notifications": [
                    {
                        "char_uuid": "00002a4d-0000-1000-8000-00805f9b34fb",
                        "elapsed_ms": 321,
                        "bytes_read": 8,
                        "hex": "0102030405060708",
                    }
                ],
            },
            parse_gamesir_probe_log(log),
        )
    def test_parse_sport_xms_probe_log_extracts_binder_sensor_stream(self):
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"sport-xms-probe","message":"binder_connected",'
            '"service_package":"com.mi.health","interface":"com.xiaomi.fitness.sport_xms.launch.ISportXmsApi"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"sport-xms-probe","message":"device_info",'
            '"device_connected":"true","support_somatosensory":"true",'
            '"device_name":"Xiaomi Smart Band 9 test-device","device_model":"M2346B1","did_present":"true"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"sport-xms-probe","message":"sport_started",'
            '"sport_type":"812","sport_state":"1"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"sport-xms-probe","message":"sensor_packet",'
            '"packet_index":"1","elapsed_ms":"250","accel_samples":"3","gyro_samples":"3",'
            '"first_accel_timestamp":"1000","last_accel_timestamp":"1040",'
            '"accel_x_min":"-0.5","accel_x_max":"1.5","accel_y_min":"-1.0",'
            '"accel_y_max":"2.0","accel_z_min":"9.1","accel_z_max":"10.2",'
            '"gyro_x_min":"-12.5","gyro_x_max":"13.5","gyro_y_min":"-2.5",'
            '"gyro_y_max":"3.5","gyro_z_min":"-1.5","gyro_z_max":"1.5"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"sport-xms-probe","message":"probe_complete",'
            '"started":"true","capture_ms":"6000","sport_type":"812",'
            '"sensor_packets":"1","accel_samples":"3","gyro_samples":"3"}'
        )
        self.assertEqual(
            {
                "status": "ok",
                "message": "probe_complete",
                "service_package": "com.mi.health",
                "interface": "com.xiaomi.fitness.sport_xms.launch.ISportXmsApi",
                "device_connected": True,
                "support_somatosensory": True,
                "device_name": "Xiaomi Smart Band 9 test-device",
                "device_model": "M2346B1",
                "did_present": True,
                "did_override_present": False,
                "started": True,
                "capture_ms": 6000,
                "sport_type": 812,
                "sensor_packets": 1,
                "accel_samples": 3,
                "gyro_samples": 3,
                "reason": "",
                "packets": [
                    {
                        "packet_index": 1,
                        "elapsed_ms": 250,
                        "accel_samples": 3,
                        "gyro_samples": 3,
                        "first_accel_timestamp": 1000,
                        "last_accel_timestamp": 1040,
                        "accel_x_min": -0.5,
                        "accel_x_max": 1.5,
                        "accel_y_min": -1.0,
                        "accel_y_max": 2.0,
                        "accel_z_min": 9.1,
                        "accel_z_max": 10.2,
                        "gyro_x_min": -12.5,
                        "gyro_x_max": 13.5,
                        "gyro_y_min": -2.5,
                        "gyro_y_max": 3.5,
                        "gyro_z_min": -1.5,
                        "gyro_z_max": 1.5,
                    }
                ],
            },
            parse_sport_xms_probe_log(log),
        )

    def test_parse_gb_sport_xms_open_keeps_full_payload_hex(self):
        payload_hex = "0808103552187A162A1408AC06150000803F1D000000402500004040"
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gb-sport-xms-open","message":"spp_packet",'
            '"packet_index":"7","channel":"ProtobufCommand","payload_length":"30",'
            '"payload_hex":"' + payload_hex + '","command_type":"8","command_subtype":"53"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gb-sport-xms-open","message":"opener_complete",'
            '"spp_packets":"1","protobuf_packets":"1","xms_sensor_8_53_packets":"1"}'
        )
        parsed = parse_gb_sport_xms_open_log(log)
        self.assertEqual("opener_complete", parsed["message"])
        self.assertEqual(payload_hex, parsed["packet_logs"][0]["payload_hex"])
        self.assertEqual(30, parsed["packet_logs"][0]["payload_length"])

    def test_parse_gb_sport_xms_stop_keeps_stop_tagged_spp_packets(self):
        payload_hex = "0808101A5217AA011408001A0E080010D48BF2D0061A02084038022802"
        log = (
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gb-sport-xms-stop","message":"spp_packet",'
            '"packet_index":"1","channel":"ProtobufCommand","payload_length":"36",'
            '"payload_hex":"' + payload_hex + '","command_type":"8","command_subtype":"26"}\n'
            'I/MI_HFIMU_STATE(123): '
            '{"status":"ok","command":"gb-sport-xms-stop","message":"stop_complete",'
            '"spp_packets":"1","protobuf_packets":"1","xms_response_8_26_packets":"1",'
            '"xms_sensor_8_53_packets":"0"}'
        )
        parsed = parse_gb_sport_xms_stop_log(log)
        self.assertEqual("stop_complete", parsed["message"])
        self.assertEqual(1, parsed["spp_packets"])
        self.assertEqual(0, parsed["xms_sensor_8_53_packets"])
        self.assertEqual(payload_hex, parsed["packet_logs"][0]["payload_hex"])
        self.assertEqual(26, parsed["packet_logs"][0]["command_subtype"])


if __name__ == "__main__":
    unittest.main()


class MiFindBandParsingTest(unittest.TestCase):
    def test_parse_mi_find_band_log(self):
        log = (
            'I/MI_HFIMU_STATE(123): {"status":"ok","command":"mi-find-band","message":"find_started",'
            '"duration_ms":"3000","did_present":"true","device_connected":"1"}\n'
            'I/MI_HFIMU_STATE(123): {"status":"ok","command":"mi-find-band","message":"find_complete",'
            '"duration_ms":"3000","did_present":"true","device_connected":"1"}'
        )
        parsed = parse_find_band_log(log, command="mi-find-band")
        self.assertEqual("find_complete", parsed["message"])
        self.assertTrue(parsed["did_present"])
        self.assertEqual(1, parsed["device_connected"])
        self.assertEqual(3000, parsed["duration_ms"])
