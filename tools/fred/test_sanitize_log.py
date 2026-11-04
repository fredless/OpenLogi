"""Tests for sanitize_log.py — run with: python -m unittest tools/fred/test_sanitize_log.py"""

from __future__ import annotations

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sanitize_log import Sanitizer, _has_ascii_run, parse_feature_index, run  # noqa: E402

TS = "2026-11-03T17:48:20.506151Z TRACE"


def make(**kwargs) -> Sanitizer:
    kwargs.setdefault("usernames", ["fred"])
    return Sanitizer(**kwargs)


def raw(payload: str) -> str:
    return (
        f"{TS} hidpp::channel: raw report received len=20 matched=true "
        f"stale=false pending_count=0 payload=[{payload}]"
    )


class IdentityTokens(unittest.TestCase):
    def test_serial_unit_receiver_tokens(self):
        s = make()
        out = s.line(
            "INFO openlogi_agent_core: armed device=serial:2131LZ0ABCD8 "
            "key=unit:6be9d300 link=receiver:82839805:slot:6"
        )
        self.assertIn("serial:XXXX", out)
        self.assertIn("unit:XXXX", out)
        self.assertIn("receiver:XXXX:slot:6", out)
        self.assertNotIn("2131LZ0ABCD8", out)
        self.assertNotIn("6be9d300", out)
        self.assertNotIn("82839805", out)

    def test_mac_address(self):
        out = make().line("DEBUG bluetooth peer address=D4:3A:2C:11:22:33 rssi=-40")
        self.assertIn("XX:XX:XX:XX:XX:XX", out)
        self.assertNotIn("D4:3A", out)

    def test_windows_instance_id_keeps_vid_pid_and_collection(self):
        path = r"\\?\HID#VID_046D&PID_C354&MI_00&Col02#7&1a2b3c4d&0&0001#{4d1e55b2-f16f-11cf-88cb-001111000030}"
        out = make().line(f"DEBUG openlogi_hid::transport::windows: open path={path}")
        self.assertIn("VID_046D&PID_C354&MI_00&Col02", out)
        self.assertIn("#XXXX#{4d1e55b2", out)
        self.assertNotIn("1a2b3c4d", out)

    def test_ansi_colour_is_stripped(self):
        out = make().line("\x1b[2m2026\x1b[0m \x1b[35mTRACE\x1b[0m hidpp::channel: x serial:ABC")
        self.assertNotIn("\x1b", out)
        self.assertIn("serial:XXXX", out)


class UserNamesAndPaths(unittest.TestCase):
    def test_windows_and_macos_home_paths(self):
        s = make(usernames=["Fred"])
        out = s.line(r"WARN config at C:\Users\Fred\AppData\Roaming\openlogi\config.toml")
        self.assertEqual(out, r"WARN config at C:\Users\XXXX\AppData\Roaming\openlogi\config.toml")
        out = s.line("WARN config at /Users/fred/Library/Application Support/openlogi")
        self.assertIn("/Users/XXXX/Library", out)

    def test_username_is_whole_word_only(self):
        out = make(usernames=["fred"]).line("INFO frederick and alfred are fine; fred is not")
        self.assertEqual(out, "INFO frederick and alfred are fine; XXXX is not")

    def test_unc_share_host(self):
        out = make().line(r"DEBUG resolved \\nas01\media\shortcuts")
        self.assertIn(r"\\XXXX\media", out)

    def test_extended_length_path_prefix_is_not_a_unc_host(self):
        out = make().line(r"DEBUG \\?\C:\Program Files\OpenLogi")
        self.assertIn(r"\\?\C:\Program Files", out)

    def test_lnk_lines_are_dropped(self):
        buf = io.StringIO()
        run(
            io.StringIO("keep 1\nDEBUG shortcut C:\\ProgramData\\Start Menu\\x.lnk target=\nkeep 2\n"),
            buf,
            make(),
        )
        self.assertEqual(buf.getvalue(), "keep 1\nkeep 2\n")


class HidppPayloads(unittest.TestCase):
    def test_learns_device_information_index_and_masks_fn0_and_fn2(self):
        s = make()
        s.line(f"{TS} hidpp::device: feature index=255 slot=2 id=0x0003 version=4")
        fn2 = s.line(raw("11, ff, 02, 2b, 32, 31, 33, 31, 4c, 5a, 30, 41, 42, 43, 44, 38"))
        self.assertIn("payload=[11, ff, 02, 2b, XX, XX", fn2)
        self.assertNotIn("4c, 5a", fn2)
        fn0 = s.line(raw("11, ff, 02, 0b, 03, 6b, e9, d3, 00, 00, 07, c3, 54, 00, 00, 00"))
        self.assertIn("payload=[11, ff, 02, 0b, XX, XX, XX", fn0)

    def test_other_functions_of_that_feature_survive(self):
        s = make(feature_index={255: 2})
        line = raw("11, ff, 02, 1b, 02, 00, 55, 31, 36, 36, 00, 00, 00, 00, 00, 00")
        self.assertEqual(s.line(line), line)  # fn 1 = firmware info, diagnostic

    def test_other_features_survive(self):
        s = make(feature_index={255: 2})
        line = raw("11, ff, 0a, 0b, 00, 53, 00, 3c, 04, 31, 00, 00, 00, 00, 00, 00")
        self.assertEqual(s.line(line), line)

    def test_index_is_per_device(self):
        s = make(feature_index={6: 3})
        line = raw("11, ff, 03, 0b, 03, 6b, e9, d3, 00, 00, 07, c3, 54, 00, 00, 00")
        self.assertEqual(s.line(line), line)  # dev 0xff has no learned index
        self.assertEqual(s.unknown_devices(), [255])

    def test_hidpp20_error_reply_survives(self):
        s = make(feature_index={255: 2})
        line = raw("11, ff, ff, 02, 2b, 05, 00, 00, 00, 00, 00, 00, 00, 00, 00, 00")
        self.assertEqual(s.line(line), line)

    def test_bolt_pairing_register_keeps_sub_page(self):
        out = make().line(raw("11, ff, 83, b5, 56, 82, 83, 98, 05, 1a, 40, 00, 00, 00, 00, 00"))
        self.assertIn("payload=[11, ff, 83, b5, 56, XX, XX", out)

    def test_bolt_unique_id_register(self):
        out = make().line(raw("11, ff, 83, fb, 82, 83, 98, 05, 00, 00, 00, 00, 00, 00, 00, 00"))
        self.assertIn("payload=[11, ff, 83, fb, XX", out)

    def test_ascii_serial_heuristic_without_learned_index(self):
        s = make()
        out = s.line(raw("11, 06, 04, 2b, 32, 31, 33, 31, 4c, 5a, 30, 41, 42, 43, 44, 38"))
        self.assertIn("payload=[11, 06, 04, 2b, XX", out)
        self.assertEqual(s.stats["masked by ASCII heuristic"], 1)

    def test_device_name_is_not_masked_by_heuristic(self):
        # "MX Master" has a space → no 8-long alphanumeric run.
        line = raw("11, 01, 05, 1b, 4d, 58, 20, 4d, 61, 73, 74, 65, 72, 20, 34, 00")
        self.assertEqual(make().line(line), line)

    def test_paranoid_masks_every_hidpp_payload_but_keeps_header(self):
        out = make(paranoid=True).line(raw("10, 01, 0a, 1b, 00, 53, 00"))
        self.assertIn("payload=[10, 01, 0a, 1b, XX, XX, XX]", out)

    def test_vendor_reports_are_left_alone(self):
        # Keypad grid-key / image-ack report 0x13 is diagnostic, not HID++.
        line = (
            f"{TS} hidpp::channel: report not HID++ — dropped len=32 foreign=true "
            "payload=[13, ff, 02, 2b, 01, 00, 01, 00, 00, 00, 00, 00, 00, 00, 00, 00]"
        )
        self.assertEqual(make().line(line), line)


class Helpers(unittest.TestCase):
    def test_ascii_run(self):
        self.assertTrue(_has_ascii_run(b"2131LZ0ABCD8"))
        self.assertFalse(_has_ascii_run(b"MX Keys"))
        self.assertFalse(_has_ascii_run(bytes([0x00, 0x53, 0x00, 0x3C])))

    def test_parse_feature_index(self):
        self.assertEqual(parse_feature_index(["255:2", "0x06:0x03"]), {255: 2, 6: 3})


if __name__ == "__main__":
    unittest.main()
