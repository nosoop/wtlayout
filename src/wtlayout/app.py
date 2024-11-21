#!/usr/bin/python3

import argparse
import collections
import contextlib
import copy
import os
import pathlib
import string
import subprocess
import xml.etree.ElementTree as ET
from typing import Iterator, Self

# mslex is shlex but for Windows; this ensures the 'process' string is correctly passed
import mslex

from .layout import Action, LayoutDirection, LayoutTab, Pane, PaneGroup, Window


def _process_template(template: ET.Element, impl: ET.Element) -> ET.Element:
    # substitutes value items from a template element with attributes from a 'preset' element
    # we currently only support one element
    resolved = copy.deepcopy(template[0])
    for element in resolved.iter():
        for key, value in element.items():
            t = string.Template(value)
            element.set(key, t.substitute(impl.attrib))
    return resolved


def _get_unvenv() -> dict[str, str]:
    # HACK: resets the environment such that the subprocess doesn't have the virtualenv
    # this effectively simulates running the default 'deactivate.bat'
    # wt will otherwise run the process with the given environment
    env: dict[str, str | None] = dict(os.environ.copy())
    env.update(
        {
            "PROMPT": env.pop("_OLD_VIRTUAL_PROMPT", None),
            "PYTHONHOME": env.pop("_OLD_VIRTUAL_PYTHONHOME", None),
            "PATH": env.pop("_OLD_VIRTUAL_PATH", None),
        }
    )
    for k in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"):
        env.pop(k, None)
    return {k: v for k, v in env.items() if v is not None}


class ContextChainMap(collections.ChainMap):
    # chain map that ensures new mappings only available in the same nesting level
    @contextlib.contextmanager
    def push_ctx(self) -> Iterator[Self]:
        yield self.new_child()


def _walk(element: ET.Element, template_registry: ContextChainMap) -> Action:
    with template_registry.push_ctx() as reg:
        for template in element.findall("template"):
            name = template.attrib.get("name")
            reg[name] = template

        children = [
            _walk(child, reg)
            for child in element
            if child.tag != "template" and child is not None
        ]
        if element.tag == "window":
            return Window(*children)
        elif element.tag == "tab":
            return LayoutTab(*children)
        elif element.tag in ("row", "column"):
            weights = None
            if element.attrib.get("weights"):
                weights = list(map(float, element.attrib.get("weights").split()))
            return PaneGroup(
                LayoutDirection.COLUMN if element.tag == "column" else LayoutDirection.ROW,
                children,
                weights=weights,
            )
        elif element.tag == "pane":
            process = None
            if "process" in element.attrib:
                process = mslex.split(element.attrib.get("process"))
            return Pane(starting_directory=element.attrib.get("directory"), process=process)
        elif element.tag == "preset":
            preset_type = element.attrib.get("name")
            if preset_type not in reg:
                raise ValueError(f"Unknown preset template name '{preset_type}'")
            return _walk(_process_template(reg[preset_type], element), reg)
        raise ValueError(f"Unknown tag '{element.tag}'")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("file", type=pathlib.Path)

    args = parser.parse_args()

    root = ET.fromstring(args.file.read_text("utf8"))
    result = _walk(root, ContextChainMap())
    subprocess.run([os.path.expandvars(s) for s in result.command()], env=_get_unvenv())
