"""CLI argument tests for main.py (run with pytest from the repo root)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skip_md_and_skip_epub_together_is_rejected(tmp_path):
    """Passing both --skip-md and --skip-epub must fail fast (exit 2).

    Accepting both flags silently does nothing and reports success,
    which misleads callers into thinking a conversion happened.
    """
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    out = tmp_path / "out"
    md_dir = out / "doc"
    md_dir.mkdir(parents=True)
    (md_dir / "doc.md").write_text("# hi", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "main.py", str(pdf), str(out), "--skip-md", "--skip-epub"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "nothing would be done" in result.stderr
