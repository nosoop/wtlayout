#!/usr/bin/python3

import argparse
import collections
import copy
import os
import pathlib
import string
import subprocess
import xml.etree.ElementTree as ET

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


def _walk(element: ET.Element, template_registry: collections.ChainMap) -> Action:
    child_registry = template_registry.new_child()

    for template in element.findall("template"):
        name = template.attrib.get("name")
        child_registry[name] = template

    children = [
        _walk(child, child_registry)
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
        if preset_type not in child_registry:
            raise ValueError(f"Unknown preset template name '{preset_type}'")
        return _walk(_process_template(child_registry[preset_type], element), child_registry)
    raise ValueError(f"Unknown tag '{element.tag}'")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("file", type=pathlib.Path)

    args = parser.parse_args()

    root = ET.fromstring(args.file.read_text("utf8"))
    result = _walk(root, collections.ChainMap())
    subprocess.run([os.path.expandvars(s) for s in result.command()], env=_get_unvenv())
