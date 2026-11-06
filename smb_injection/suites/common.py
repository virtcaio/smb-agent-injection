from __future__ import annotations

from typing import Any

import yaml


class _Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    # Multi-line text (email bodies, documents, articles) is shown verbatim as a literal block,
    # not as a quoted scalar with escaped quotes and doubled line breaks.
    if "\n" in data:
        data = "\n".join(line.rstrip() for line in data.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _represent_str)


def fmt(obj: Any) -> str:
    """Tool results are YAML, readable by the model in either language."""
    if obj in (None, [], {}):
        return "No results."
    return yaml.dump(obj, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1000).strip()


def matches(query: str, *fields: Any) -> bool:
    terms = [t for t in query.casefold().split() if t]
    text = " ".join(str(f) for f in fields if f is not None).casefold()
    return all(t in text for t in terms) if terms else True


def next_id(items: dict[str, Any] | list[Any], prefix: str) -> str:
    n = len(items) + 1
    return f"{prefix}{n:02d}"
