from __future__ import annotations

import json
from pathlib import Path

import click

from app.pipeline import process_document


@click.group()
def main() -> None:
    """SledgeCO-AI change-order extraction tools."""


@main.command()
@click.argument("document", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", type=click.Path(path_type=Path), help="Write JSON output to this file.")
def extract(document: Path, output: Path | None) -> None:
    """Extract and validate one document."""
    result = process_document(document)
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, indent=2, default=str)
    if output:
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        click.echo(rendered)


if __name__ == "__main__":
    main()
