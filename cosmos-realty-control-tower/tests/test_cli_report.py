from pathlib import Path

from typer.testing import CliRunner

from cosmos_control_tower.cli.app import app


def test_demo_report_cli_generates_all_formats(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "report",
            "--demo",
            "--department",
            "2",
            "--period",
            "week",
            "--output",
            str(tmp_path),
            "--calibration-output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Bitrix24 writes: 0" in result.output
    assert {
        "rop-dashboard.html",
        "rop-report.md",
        "rop-report.json",
        "rop-control.csv",
        "rop-brokers.csv",
        "dry-run-actions.csv",
    }.issubset({path.name for path in tmp_path.iterdir()})
    assert (tmp_path / "calibration-summary.html").exists()
    assert (tmp_path / "calibration-summary.csv").exists()
