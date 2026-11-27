"""Run checkout receipt behavior checks as part of the shop suite."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_checkout_receipt_javascript():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for checkout receipt behavior checks")
    root = Path(__file__).resolve().parents[2]
    subprocess.run([node, str(root / "shop/tests/test_checkout_receipt.js")], cwd=root, check=True)
