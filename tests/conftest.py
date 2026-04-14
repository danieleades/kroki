import base64
import os
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path

import docutils
import pytest
import sphinx
from _pytest.config import Config
from _pytest.main import Session

from sphinx_kroki import kroki as kroki_module

pytest_plugins = "sphinx.testing.fixtures"

# Exclude 'fixtures' dirs for pytest test collector
collect_ignore = ["fixtures"]

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WHZ"
    "xQAAAABJRU5ErkJggg=="
)


class _MockKrokiResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int = 1) -> Iterator[bytes]:
        for index in range(0, len(self._content), chunk_size):
            yield self._content[index : index + chunk_size]


def _rendered_diagram(payload: Mapping[str, object]) -> bytes:
    if payload["output_format"] == "png":
        return _PNG_BYTES

    return (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        f"<title>{payload['diagram_type']}</title>"
        "</svg>"
    ).encode()


@pytest.fixture(scope="session")
def rootdir() -> Path:
    return Path(__file__).parent.resolve() / "fixtures"


@pytest.fixture(autouse=True)
def mock_kroki_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(
        _url: str, *, json: Mapping[str, object], **_kwargs: object
    ) -> _MockKrokiResponse:
        return _MockKrokiResponse(_rendered_diagram(json))

    monkeypatch.setattr(kroki_module.requests, "post", fake_post)


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
