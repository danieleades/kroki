"""sphinxcontrib_kroki — embed diagrams via Kroki in Sphinx docs."""

from importlib.metadata import version
from typing import Any

from sphinx.application import Sphinx

from .kroki import Kroki
from .transform import KrokiToImageTransform

__version__ = version("sphinx-kroki")


def setup(app: Sphinx) -> dict[str, Any]:
    """Register the Kroki extension with Sphinx."""
    app.add_directive("kroki", Kroki)
    app.add_transform(KrokiToImageTransform)
    app.add_config_value("kroki_url", "https://kroki.io", "env")
    app.add_config_value("kroki_output_format", "svg", "env")
    app.add_config_value("kroki_inline_svg", default=False, rebuild="env")

    return {"version": __version__, "parallel_read_safe": True}
