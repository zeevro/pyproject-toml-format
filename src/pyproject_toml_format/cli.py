from __future__ import annotations

import argparse
from collections.abc import Callable, Generator, Iterable, Mapping
from difflib import unified_diff
import pathlib
import sys
from typing import TYPE_CHECKING, Literal, TextIO, TypeVar

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
import tomlkit
from tomlkit.items import Item, String, _ArrayItemGroup

from pyproject_toml_format._ruff import format_ruff_lint_ignore


if TYPE_CHECKING:
    from tomlkit.container import Container


_T = TypeVar('_T')

_OP_ORDER = {op: i for i, op in enumerate(['~=', '==', '===', '>', '>=', '<=', '<', '!='])}


class Pipe:
    @staticmethod
    def open(mode: Literal['r', 'w'] = 'r') -> TextIO:
        return {'r': sys.stdin, 'w': sys.stdout}[mode]

    @staticmethod
    def absolute() -> type[Pipe]:
        return Pipe

    def __str__(self) -> str:
        return ''


def document_paths(parent: Container | Item, paths: Iterable[str]) -> Generator[Container | Item, None, None]:
    for path in paths:
        if not path:
            yield parent
            continue
        k, _, rest = path.partition('.')
        if k == '*':
            values = parent.values() if isinstance(parent, Mapping) else parent
            for v in values:
                yield from document_paths(v, [rest])
            continue
        if k not in parent:
            continue
        yield from document_paths(parent[k], [rest])


def format_requirement(r: str) -> str:
    req = Requirement(r)
    ret = canonicalize_name(req.name, validate=True)
    if req.extras:
        ret += f'[{",".join(sorted(e.lower() for e in req.extras))}]'
    if req.specifier:
        ret += f' {",".join(str(s) for s in sorted(req.specifier, key=lambda s: (_OP_ORDER[s.operator], s.version)))}'
    elif req.url:
        ret += f' @ {req.url}'
    if req.marker:
        ret += f' ; {req.marker}'
    return ret


class UnmovableItem:
    def __hash__(self) -> int:
        return 0

    def __eq__(self, other: object) -> bool:
        return True

    def __lt__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False


def array_sort_key(x: _ArrayItemGroup, key: Callable[[str], _T] = str) -> _T | UnmovableItem:
    if isinstance(x.value, String):
        return key(x.value)
    return UnmovableItem()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--check', action='store_true')
    p.add_argument('-d', '--diff', action='store_true')
    p.add_argument('--no-sort', action='store_true')
    p.add_argument('--no-ruff', action='store_true')
    p.add_argument('path', nargs='?', type=pathlib.Path)

    if TYPE_CHECKING:

        class Args:
            check: bool
            diff: bool
            no_sort: bool
            no_ruff: bool
            path: pathlib.Path | type[Pipe] | None

        args = Args()
    else:
        args = p.parse_args()

    if args.path is None:
        args.path = pathlib.Path('pyproject.toml') if sys.stdin.isatty() else Pipe

    with args.path.open() as f:
        orig_str = f.read()
    doc = tomlkit.loads(orig_str)
    modified = False

    format_paths = [
        'project.dependencies',
        'dependency-groups.*',
        'tool.uv.constraint-dependencies',
        'tool.uv.override-dependencies',
    ]

    sort_paths = [
        'project.dependencies',
        'tool.uv.constraint-dependencies',
        'tool.uv.override-dependencies',
    ]

    for x in document_paths(doc, format_paths):
        if not x:
            continue
        it = x.items() if isinstance(x, Mapping) else enumerate(x)
        for k, v in it:
            if not isinstance(v, str):
                continue
            if v != (f := format_requirement(v)):
                modified = True
                x[k] = f

    for x in document_paths(doc, sort_paths):
        t = x._value.copy()
        x._value.sort(key=lambda v: array_sort_key(v, lambda r: Requirement(r).name))
        if x._value != t:
            modified = True

    if not args.no_ruff:
        modified = format_ruff_lint_ignore(doc) or modified

    if not modified:
        return

    modified_str = doc.as_string()

    if args.diff:
        print(
            *unified_diff(
                orig_str.splitlines(keepends=True),
                modified_str.splitlines(keepends=True),
                str(args.path),
                str(args.path),
            ),
            sep='',
        )
    else:
        tomlkit.dump(doc, args.path.open('w'))

    if args.check:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
