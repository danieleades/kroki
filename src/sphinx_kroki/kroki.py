"""Kroki directive and rendering helpers."""

from __future__ import annotations

import json
from hashlib import sha1
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, ClassVar, cast

import requests
import yaml
from docutils import nodes
from docutils.nodes import Element, General, Inline, Node
from docutils.parsers.rst import directives
from sphinx.errors import SphinxError
from sphinx.ext.graphviz import align_spec
from sphinx.locale import __
from sphinx.util.docutils import SphinxDirective
from sphinx.util.i18n import search_image_for_language
from sphinx.util.nodes import set_source_info

if TYPE_CHECKING:
    from sphinx.builders import Builder

formats = ("png", "svg", "jpeg", "base64", "txt", "utxt")

types = {
    "actdiag": "actdiag",
    "blockdiag": "blockdiag",
    "bpmn": "bpmn",
    "bytefield": "bytefield",
    "c4plantuml": "c4plantuml",
    "d2": "d2",
    "dot": "graphviz",
    "ditaa": "ditaa",
    "er": "erd",
    "erd": "erd",
    "excalidraw": "excalidraw",
    "graphviz": "graphviz",
    "mermaid": "mermaid",
    "nomnoml": "nomnoml",
    "nwdiag": "nwdiag",
    "packetdiag": "packetdiag",
    "pikchr": "pikchr",
    "plantuml": "plantuml",
    "rackdiag": "rackdiag",
    "structurizr": "structurizr",
    "seqdiag": "seqdiag",
    "svgbob": "svgbob",
    "umlet": "umlet",
    "vega": "vega",
    "vegalite": "vegalite",
    "wavedrom": "wavedrom",
}

extension_type_map = {
    "bob": "svgbob",
    "c4": "c4plantuml",
    "c4puml": "c4plantuml",
    "dot": "graphviz",
    "dsl": "structurizr",
    "er": "erd",
    "gv": "graphviz",
    "iuml": "plantuml",
    "pu": "plantuml",
    "puml": "plantuml",
    "uxf": "umlet",
    "vg": "vega",
    "vgl": "vegalite",
    "vl": "vegalite",
    "wsd": "plantuml",
}


def type_spec(argument: str) -> str:
    """Validate a Kroki diagram type option or argument."""
    return directives.choice(argument, tuple(types.keys()))


def format_spec(argument: str) -> str:
    """Validate a Kroki output format option or argument."""
    return directives.choice(argument, formats)


class KrokiError(SphinxError):
    """Raised when Kroki fails to render or persist a diagram."""

    category = "Kroki error"


class KrokiNode(General, Inline, Element):
    """Docutils node used to carry Kroki diagram metadata."""


class Kroki(SphinxDirective):
    """Directive to insert arbitrary kroki markup."""

    has_content = True
    required_arguments = 0
    optional_arguments = 3
    final_argument_whitespace = False
    option_spec: ClassVar = {
        "align": align_spec,
        "caption": directives.unchanged,
        "class": directives.class_option,
        "filename": directives.unchanged,
        "format": format_spec,
        "name": directives.unchanged,
        "options": directives.unchanged,
        "type": type_spec,
    }

    def run(self) -> list[Node]:
        """Parse directive input into a placeholder Kroki node."""
        source = "\n".join(self.content)
        filename, diagram_type, output_format = self._parse_arguments()

        filename, warning = self._resolve_filename(filename)
        if warning is None:
            source, warning = self._resolve_source(source, filename)
        if warning is not None:
            return [warning]

        if not source.strip():
            return [
                self._warning(
                    "Ignoring kroki directive without content. It is necessary "
                    "to specify filename argument/option or content"
                )
            ]

        diagram_type, warning = self._resolve_diagram_type(diagram_type, filename)
        if warning is not None:
            return [warning]

        output_format, warning = self._resolve_output_format(output_format)
        if warning is not None:
            return [warning]

        diagram_options, warning = self._load_diagram_options()
        if warning is not None:
            return [warning]

        diagram_type = cast("str", diagram_type)
        node = self._create_node(diagram_type, source, output_format, diagram_options)
        return self._wrap_node(node, diagram_type)

    def _parse_arguments(self) -> tuple[str | None, str | None, str | None]:
        filename: str | None = None
        diagram_type: str | None = None
        output_format: str | None = None

        for argument in self.arguments:
            if argument in types:
                diagram_type = types[argument]
            elif argument in formats:
                output_format = argument
            else:
                filename = argument

        return filename, diagram_type, output_format

    def _resolve_filename(self, filename: str | None) -> tuple[str | None, Node | None]:
        if "filename" in self.options:
            if filename is not None:
                return None, self._warning(
                    "Kroki directive cannot have both filename option and a "
                    "filename argument"
                )
            filename = cast("str", self.options["filename"])
        return filename, None

    def _resolve_source(
        self, source: str, filename: str | None
    ) -> tuple[str, Node | None]:
        if source.strip() and filename is not None:
            return source, self._warning(
                "Kroki directive cannot have both content and a filename argument"
            )

        if filename is None:
            return source, None

        argument = search_image_for_language(filename, self.env)
        rel_filename, resolved_filename = self.env.relfn2path(argument)
        self.env.note_dependency(rel_filename)
        try:
            return Path(resolved_filename).read_text(encoding="utf-8"), None
        except OSError:
            return source, self._warning(
                "External kroki file %r not found or reading it failed",
                resolved_filename,
            )

    def _resolve_diagram_type(
        self, diagram_type: str | None, filename: str | None
    ) -> tuple[str | None, Node | None]:
        if "type" in self.options:
            if diagram_type is not None:
                return None, self._warning(
                    "Kroki directive cannot have both type option and a type argument"
                )
            diagram_type = types[cast("str", self.options["type"])]
        elif diagram_type is None and filename is not None:
            suffix = Path(filename).suffix.lstrip(".")
            diagram_type = extension_type_map.get(suffix, types.get(suffix))

        if diagram_type is None:
            return None, self._warning("Kroki directive has to define diagram type.")

        return diagram_type, None

    def _resolve_output_format(
        self, output_format: str | None
    ) -> tuple[str | None, Node | None]:
        if "format" in self.options:
            if output_format is not None:
                return None, self._warning(
                    "Kroki directive cannot have both format option and a "
                    "format argument"
                )
            output_format = cast("str", self.options["format"])

        return output_format, None

    def _load_diagram_options(self) -> tuple[dict[str, object] | None, Node | None]:
        if "options" not in self.options:
            return None, None

        loaded = yaml.safe_load(cast("str", self.options["options"]))
        if loaded is None:
            return {}, None
        if not isinstance(loaded, dict):
            return None, self._warning("Kroki directive options must be a YAML mapping")
        return cast("dict[str, object]", loaded), None

    def _create_node(
        self,
        diagram_type: str,
        source: str,
        output_format: str | None,
        diagram_options: dict[str, object] | None,
    ) -> KrokiNode:
        node = KrokiNode()
        node["type"] = diagram_type
        if output_format is not None:
            node["format"] = output_format
        node["source"] = source

        if diagram_options is not None:
            node["options"] = diagram_options

        classes = ["kroki", f"kroki-{diagram_type}"]
        node["classes"] = classes + self.options.get("class", [])
        if "align" in self.options:
            node["align"] = self.options["align"]

        return node

    def _wrap_node(self, node: KrokiNode, diagram_type: str) -> list[Node]:
        if "caption" not in self.options:
            self.add_name(node)
            return [node]

        caption = cast("str", self.options["caption"])
        node["caption"] = caption
        figure = nodes.figure("", node)
        if "align" in node:
            figure["align"] = node.attributes.pop("align")
        inodes, messages = self.parse_inline(caption)
        caption_node = nodes.caption(caption, "", *inodes)
        caption_node.extend(messages)
        set_source_info(self, caption_node)
        figure += caption_node
        figure["classes"] = ["kroki", f"kroki-{diagram_type}"]
        self.add_name(figure)
        return [figure]

    def _warning(self, message: str, *args: object) -> Node:
        translated = __(message)
        if args:
            translated = translated % args
        return self.state.document.reporter.warning(translated, line=self.lineno)


def render_kroki(
    builder: Builder,
    node: KrokiNode,
    output_format: str,
    prefix: str = "kroki",
) -> Path:
    """Render a Kroki diagram and cache it under the Sphinx output directory."""
    kroki_url: str = builder.config.kroki_url
    payload = _render_payload(node, output_format)
    outfn = _render_output_path(builder, kroki_url, payload, output_format, prefix)

    if outfn.is_file():
        return outfn

    try:
        outfn.parent.mkdir(parents=True, exist_ok=True)

        response = requests.post(kroki_url, json=payload, stream=True, timeout=30)
        response.raise_for_status()
        _write_rendered_diagram(outfn, response)
    except requests.exceptions.RequestException as e:
        raise KrokiError(__("kroki did not produce a diagram")) from e
    except OSError as e:
        raise KrokiError(__("Unable to write diagram to file %r") % outfn) from e
    else:
        return outfn


def _render_payload(
    node: KrokiNode, output_format: str
) -> dict[str, str | dict[str, object]]:
    diagram_options = cast("dict[str, object]", node.get("options", {}))
    return {
        "diagram_source": cast("str", node["source"]),
        "diagram_type": cast("str", node["type"]),
        "diagram_options": diagram_options,
        "output_format": output_format,
    }


def _render_output_path(
    builder: Builder,
    kroki_url: str,
    payload: dict[str, str | dict[str, object]],
    output_format: str,
    prefix: str,
) -> Path:
    hashkey = (kroki_url + json.dumps(payload, sort_keys=True)).encode()
    digest = sha1(hashkey, usedforsecurity=False).hexdigest()
    fname = f"{prefix}-{digest}.{output_format}"
    return Path(builder.outdir).joinpath(builder.imagedir, fname)


def _write_rendered_diagram(outfn: Path, response: requests.Response) -> None:
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=outfn.parent,
            prefix=f".{outfn.stem}-",
            suffix=outfn.suffix,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)

        temp_path.replace(outfn)
    except (OSError, requests.exceptions.RequestException):
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
