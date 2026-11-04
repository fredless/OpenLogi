#!/usr/bin/env python3
"""Redact identifiers from OpenLogi debug/trace logs before sharing them.

Personal tooling (fred/notes branch) — not part of OpenLogi.

Usage:
    python sanitize_log.py agent.log -o agent-sanitized.log
    python sanitize_log.py < agent.log > agent-sanitized.log
    python sanitize_log.py agent.log --username fred --feature-index 255:2

What it redacts (replaced with XX / XXXX, structure kept so the log stays
diagnosable):

* identity tokens: ``serial:<v>``, ``unit:<hex>``, ``receiver:<hex>`` (the
  ``:slot:N`` that follows is kept), Bluetooth MAC addresses, and the instance
  segment of Windows device paths (``\\\\?\\HID#VID_046D&PID_C354&MI_00#<inst>#{guid}``)
* the user name in paths (``C:\\Users\\<name>``, ``/Users/<name>``,
  ``/home/<name>``) and anywhere else it appears as a word, plus UNC share
  hosts (``\\\\host\\share``)
* HID++ payload bytes in ``hidpp::channel`` trace lines
  (``payload=[11, ff, 02, 2b, ...]``):
    - ``0x0003`` DeviceInformation fn 0 (unit ID) and fn 2 (ASCII serial)
      replies — the 0x0003 feature index per device index is learned from
      ``hidpp::device`` "feature" lines (``index=255 slot=2 id=0x0003``) or
      given with ``--feature-index DEV:IDX``
    - Bolt receiver register replies ``0x83 0xb5`` (pairing info: the
      sub-page byte is kept, the rest masked) and ``0x83 0xfb`` (receiver
      unique ID)
    - any reply whose parameters contain a printable-ASCII run of 8+ chars
      (a serial the index learning missed)
* whole lines that dump Start Menu shortcuts (``.lnk``) — dropped

A summary of what was changed goes to stderr. ``--paranoid`` masks the
parameter bytes of *every* HID++ payload (headers kept) for when the 0x0003
index cannot be learned.

Always skim the output before posting: this is a safety net, not a proof.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, TextIO

MASK_BYTE = "XX"
ASCII_RUN = 8

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
PAYLOAD_RE = re.compile(r"(payload=\[)([0-9a-fA-F]{2}(?:, [0-9a-fA-F]{2})*)(\])")
FEATURE_LINE_RE = re.compile(
    r"\bindex=(?P<dev>\d+)\b.*?\bslot=(?P<slot>\d+)\b.*?\bid=0x(?P<id>[0-9a-fA-F]{4})\b"
)
SERIAL_RE = re.compile(r"\bserial:[^\s,;\"')\]}]+")
UNIT_RE = re.compile(r"\bunit:[0-9a-fA-F]+\b")
RECEIVER_RE = re.compile(r"\breceiver:[0-9a-fA-F]+\b")
MAC_RE = re.compile(r"\b[0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5}\b")
# \\?\HID#VID_046D&PID_C354&MI_00&Col01#7&1a2b3c4d&0&0000#{4d1e55b2-...}
WIN_INSTANCE_RE = re.compile(r"(#(?:VID|PID|MI|COL|Col|{)?[^#\\\s]*#)([^#\\\s{}]+)(#\{)")
UNC_RE = re.compile(r"(?<![\\\w])\\\\(?![?.]\\)([A-Za-z0-9._-]+)\\")
LNK_RE = re.compile(r"\.lnk\b", re.IGNORECASE)

DEVICE_INFO_ID = 0x0003
BOLT_REGISTER_SUB_IDS = {0x83}  # get long register reply
PAIRING_REGISTER = 0xB5
UNIQUE_ID_REGISTER = 0xFB
RECEIVER_INDEX = 0xFF
HIDPP_REPORT_IDS = {0x10, 0x11, 0x12}


@dataclass
class Sanitizer:
    usernames: list[str]
    feature_index: dict[int, int] = field(default_factory=dict)
    paranoid: bool = False
    stats: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        names = sorted({u for u in self.usernames if len(u) >= 2}, key=len, reverse=True)
        self._user_res = [
            re.compile(rf"(?i)(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
            for name in names
        ]
        self._seen_payload_devices: set[int] = set()

    # ── per line ────────────────────────────────────────────────────────────

    def line(self, raw: str) -> str | None:
        text = ANSI_RE.sub("", raw)
        if LNK_RE.search(text):
            self.stats["dropped .lnk lines"] += 1
            return None
        self._learn(text)
        text = PAYLOAD_RE.sub(self._payload, text)
        text = self._sub(SERIAL_RE, text, "serial:XXXX", "serial tokens")
        text = self._sub(UNIT_RE, text, "unit:XXXX", "unit tokens")
        text = self._sub(RECEIVER_RE, text, "receiver:XXXX", "receiver tokens")
        text = self._sub(MAC_RE, text, "XX:XX:XX:XX:XX:XX", "MAC addresses")
        text = self._sub(WIN_INSTANCE_RE, text, r"\1XXXX\3", "Windows instance IDs")
        text = self._sub(UNC_RE, text, r"\\\\XXXX\\", "UNC hosts")
        for user_re in self._user_res:
            text = self._sub(user_re, text, "XXXX", "user names")
        return text

    def _sub(self, pattern: re.Pattern[str], text: str, repl: str, stat: str) -> str:
        new, count = pattern.subn(repl, text)
        if count:
            self.stats[stat] += count
        return new

    def _learn(self, text: str) -> None:
        if "hidpp::device" not in text and " feature" not in text:
            return
        match = FEATURE_LINE_RE.search(text)
        if match and int(match["id"], 16) == DEVICE_INFO_ID:
            dev, slot = int(match["dev"]), int(match["slot"])
            if self.feature_index.get(dev) != slot:
                self.feature_index[dev] = slot
                self.stats[f"learned 0x0003 index dev={dev} -> {slot}"] += 1

    # ── payloads ────────────────────────────────────────────────────────────

    def _payload(self, match: re.Match[str]) -> str:
        parts = match[2].split(", ")
        masked = self.mask(parts)
        if masked != parts:
            self.stats["masked payloads"] += 1
        return f"{match[1]}{', '.join(masked)}{match[3]}"

    def mask(self, parts: list[str]) -> list[str]:
        """Return ``parts`` (hex byte strings) with sensitive bytes masked."""
        try:
            data = [int(p, 16) for p in parts]
        except ValueError:
            return parts
        if len(data) < 4 or data[0] not in HIDPP_REPORT_IDS:
            return parts
        report_id, dev, sub_or_feat, fn_or_addr = data[:4]
        self._seen_payload_devices.add(dev)

        def keep_first(n: int) -> list[str]:
            return parts[:n] + [MASK_BYTE] * (len(parts) - n)

        if self.paranoid:
            return keep_first(4)
        # HID++ 1.0 receiver register reply: [rid, 0xff, 0x83, addr, params…]
        if dev == RECEIVER_INDEX and sub_or_feat in BOLT_REGISTER_SUB_IDS:
            if fn_or_addr == PAIRING_REGISTER:
                return keep_first(5)  # keep the sub-page byte
            if fn_or_addr == UNIQUE_ID_REGISTER:
                return keep_first(4)
        # HID++ 2.0 error replies carry no identifiers.
        if sub_or_feat == 0xFF:
            return parts
        function = fn_or_addr >> 4
        if self.feature_index.get(dev) == sub_or_feat and function in (0, 2):
            return keep_first(4)
        if _has_ascii_run(data[4:]):
            self.stats["masked by ASCII heuristic"] += 1
            return keep_first(4)
        return parts

    def unknown_devices(self) -> list[int]:
        return sorted(self._seen_payload_devices - set(self.feature_index))


def _has_ascii_run(params: Iterable[int]) -> bool:
    run = 0
    for byte in params:
        run = run + 1 if 0x20 <= byte <= 0x7E and chr(byte).isalnum() else 0
        if run >= ASCII_RUN:
            return True
    return False


def default_usernames() -> list[str]:
    names = {os.environ.get("USERNAME", ""), os.environ.get("USER", "")}
    try:
        names.add(getpass.getuser())
    except Exception:  # noqa: BLE001 — no login name is fine
        pass
    home = os.path.expanduser("~")
    names.add(os.path.basename(home.rstrip("\\/")))
    return [n for n in names if n and n.lower() not in {"root", "user", "users", "home"}]


def parse_feature_index(values: list[str]) -> dict[int, int]:
    out: dict[int, int] = {}
    for value in values:
        dev, _, idx = value.partition(":")
        out[int(dev, 0)] = int(idx, 0)
    return out


def run(src: TextIO, dst: TextIO, sanitizer: Sanitizer) -> None:
    for raw in src:
        cleaned = sanitizer.line(raw.rstrip("\r\n"))
        if cleaned is not None:
            dst.write(cleaned + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", nargs="?", help="log file (default: stdin)")
    parser.add_argument("-o", "--output", help="output file (default: stdout)")
    parser.add_argument(
        "--username",
        action="append",
        default=[],
        help="user name to redact (repeatable; the current login is always added)",
    )
    parser.add_argument(
        "--feature-index",
        action="append",
        default=[],
        metavar="DEV:IDX",
        help="0x0003 feature index for a device index, e.g. 255:2 (repeatable)",
    )
    parser.add_argument(
        "--paranoid", action="store_true", help="mask parameter bytes of every HID++ payload"
    )
    args = parser.parse_args(argv)

    sanitizer = Sanitizer(
        usernames=args.username + default_usernames(),
        feature_index=parse_feature_index(args.feature_index),
        paranoid=args.paranoid,
    )
    src = open(args.input, encoding="utf-8", errors="replace") if args.input else sys.stdin
    dst = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else sys.stdout
    try:
        run(src, dst, sanitizer)
    finally:
        if args.input:
            src.close()
        if args.output:
            dst.close()

    print("sanitize_log summary:", file=sys.stderr)
    for key, count in sorted(sanitizer.stats.items()):
        print(f"  {key}: {count}", file=sys.stderr)
    unknown = sanitizer.unknown_devices()
    if unknown and not args.paranoid:
        print(
            "  WARNING: 0x0003 feature index unknown for device index(es) "
            f"{', '.join(map(str, unknown))}; unit-ID replies there are NOT masked "
            "(serials are, by the ASCII heuristic). Pass --feature-index DEV:IDX "
            "(see `openlogi diag features`) or --paranoid.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
