import os
import shutil
from pathlib import Path

import docutils
import pytest
import sphinx
from _pytest.config import Config
from _pytest.main import Session

pytest_plugins = "sphinx.testing.fixtures"

# Exclude 'fixtures' dirs for pytest test collector
collect_ignore = ["fixtures"]


@pytest.fixture(scope="session")
def rootdir() -> Path:
    return Path(__file__).parent.resolve() / "fixtures"


def pytest_report_header(config: Config) -> str:
    header = (
        f"libraries: Sphinx-{sphinx.__display_version__}, "
        f"docutils-{docutils.__version__}"
    )
    tmp_path_factory = getattr(config, "_tmp_path_factory", None)
    if tmp_path_factory is not None:
        header += f"\nbase tempdir: {tmp_path_factory.getbasetemp()}"

    return header


def _initialize_test_directory() -> None:
    if "SPHINX_TEST_TEMPDIR" in os.environ:
        tempdir = Path(os.environ["SPHINX_TEST_TEMPDIR"]).resolve()
        print(f"Temporary files will be placed in {tempdir}.")  # noqa: T201

        if tempdir.exists():
            shutil.rmtree(tempdir)

        tempdir.mkdir(parents=True)


def pytest_sessionstart(session: Session) -> None:  # noqa: ARG001
    _initialize_test_directory()
