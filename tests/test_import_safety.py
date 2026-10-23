"""Importing the package must be side-effect free (WP0, R10, R12).

The import runs in a fresh interpreter with sockets disabled, an empty working
directory and an empty TMPDIR. It must not open a connection, print anything,
or create a file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PROBE = textwrap.dedent(
    """
    import importlib, pkgutil, socket, sys

    class _Blocked(socket.socket):
        def __init__(self, *a, **k):
            raise RuntimeError("network access during import")

    def _no_dns(*a, **k):
        raise RuntimeError("DNS lookup during import")

    socket.socket = _Blocked
    socket.create_connection = _no_dns
    socket.getaddrinfo = _no_dns

    import coned_billing
    names = sorted(
        m.name for m in pkgutil.walk_packages(coned_billing.__path__, "coned_billing.")
    )
    for name in names:
        importlib.import_module(name)
    sys.stderr.write("IMPORTED:" + ",".join(names))
    """
)


def test_importing_every_submodule_has_no_side_effects(tmp_path):
    work = tmp_path / "cwd"
    tmp = tmp_path / "tmp"
    work.mkdir()
    tmp.mkdir()
    env = {
        **os.environ,
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "", f"import printed to stdout: {proc.stdout!r}"
    # The probe's own marker is the only permitted stderr output.
    marker, _, rest = proc.stderr.rpartition("IMPORTED:")
    assert marker == "", f"import wrote to stderr: {marker!r}"
    imported = set(rest.split(","))
    assert {"coned_billing.supply_charge", "coned_billing.summary", "coned_billing.cli"} <= imported
    assert list(work.iterdir()) == []
    assert list(tmp.iterdir()) == []
