# ~\~ language=Python filename=pylsoFoam/clean.py
# ~\~ begin <<lit/architecture.md|pylsoFoam/clean.py>>[init]
import argh  # type:ignore
from pathlib import Path
from .vector import BaseCase


@argh.arg("target", help="target path to clean")
@argh.arg("--base_case", help="name of the base-case")
def main(target: Path, base_case: str = "baseCase"):
    """Auxiliary function that deletes all vectors of this base-case."""
    BaseCase(Path(target), base_case).clean()


if __name__ == "__main__":
    argh.dispatch_command(main)
# ~\~ end
