import shutil
import subprocess
import pytest
from floorwise.paths import ROOT


def test_frontend_sse_parser_handles_chunks_cancellation_and_interruption():
    node=shutil.which('node')
    if not node:pytest.skip('Node runtime unavailable')
    result=subprocess.run([node,'--experimental-strip-types','web/tests/api-contracts.mjs'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
