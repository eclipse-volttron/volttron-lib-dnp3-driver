"""Runs the end-to-end harness (interface + proxy manager + proxy subprocess + dnp3py outstation) in a subprocess.

Needs only the installed packages and two free local ports; no hardware. Skipped if dnp3py is not installed.
"""
import os
import socket
import subprocess
import sys

from pathlib import Path

import pytest

pytest.importorskip('dnp3.outstation')

HARNESS = Path(__file__).with_name('e2e_harness.py')
SERVER_HARNESS = Path(__file__).with_name('e2e_server_harness.py')
EXPECTED_CHECKS = 13
EXPECTED_SERVER_CHECKS = 17


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _run(harness: Path, log: Path, expected: int):
    proc = subprocess.run([sys.executable, str(harness), str(_free_port())], capture_output=True, text=True,
                          timeout=180, env={**os.environ, 'DNP3_E2E_LOG': str(log)})
    report = proc.stdout + proc.stderr
    if proc.returncode != 0 and log.exists():
        report += '\n--- log ---\n' + log.read_text()[-4000:]
    assert proc.returncode == 0, report
    assert f'{expected}/{expected} passed' in proc.stdout, report


def test_end_to_end(tmp_path):
    """Master role against dnp3py's own outstation."""
    _run(HARNESS, tmp_path / 'e2e.log', EXPECTED_CHECKS)


def test_end_to_end_outstation_role(tmp_path):
    """Outstation role served by the proxy, read and operated by a master-role interface through the same proxy."""
    _run(SERVER_HARNESS, tmp_path / 'e2e_server.log', EXPECTED_SERVER_CHECKS)
