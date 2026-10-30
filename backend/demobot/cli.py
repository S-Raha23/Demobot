"""`demobot` command line."""

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
def version() -> None:
    from importlib.metadata import version as v

    typer.echo(v("demobot"))
