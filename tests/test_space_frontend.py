"""Run the offline shipped-frontend fixtures through existing test discovery."""
import shutil
import subprocess
from pathlib import Path


def test_space_availability_behavior():
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the Space frontend fixtures"
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("space_availability.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
