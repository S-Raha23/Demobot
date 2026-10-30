"""`demobot` command line."""

from pathlib import Path

import typer

from demobot import budget

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def costs() -> None:
    """Print the ledger: spend per provider and model, and the caps left."""
    s = budget.summary()
    typer.echo(f"{'provider':<10} {'spent $':>9} {'today $':>9} {'calls':>6} {'hits':>6}")
    for name, t in sorted(s["by_provider"].items()):
        typer.echo(
            f"{name:<10} {t['usd']:>9.4f} {t['today_usd']:>9.4f} {int(t['calls']):>6} "
            f"{int(t['cache_hits']):>6}"
        )
    typer.echo("")
    typer.echo(f"{'model':<40} {'spent $':>9} {'calls':>6} {'hits':>6}")
    for name, t in sorted(s["by_model"].items()):
        typer.echo(f"{name:<40} {t['usd']:>9.4f} {int(t['calls']):>6} {int(t['cache_hits']):>6}")
    typer.echo("")
    for provider, caps in s["remaining"].items():
        left = ", ".join(f"{k} ${v:.2f}" for k, v in caps.items())
        typer.echo(f"left on {provider}: {left}")


@app.command()
def calibrate(clip: Path, out: Path = Path("data/calibrate_out")) -> None:
    """Ingest a clip, then find the markers and fit the metric table plane."""
    from demobot import calibrate as cal_stage
    from demobot import media

    info = media.ingest(clip, out)
    cal = cal_stage.run(out / "analysis.mp4", out)
    typer.echo(f"{info.width}x{info.height}, {info.duration_s:.1f} s after trimming")
    for m in cal.markers:
        typer.echo(f"marker {m.id}: ({m.center_cm[0]:6.1f}, {m.center_cm[1]:6.1f}) cm")
    c = cal.camera
    typer.echo(
        f"reprojection {cal.reprojection_px:.2f} px; camera {c.position_cm[2]:.0f} cm high, "
        f"tilt {c.tilt_deg:.0f}°, focal {c.focal_px:.0f} px ({c.focal_source})"
    )
    for w in cal.warnings:
        typer.echo(f"warning: {w}")
    typer.echo(f"wrote {out}/calibration.json")


@app.command()
def version() -> None:
    from importlib.metadata import version as v

    typer.echo(v("demobot"))
