from dataclasses import asdict
from functools import reduce
from operator import getitem

import tomlkit
from tomlkit.container import Container
from tomlkit.items import AbstractTable, AoT, Array, Comment, Item, Whitespace, _ArrayItemGroup, Key


def cannonicalize_key(k: Key | str | int) -> str | int:
    if isinstance(k, Key):
        return k.key
    return k


def walk(root: Container, path: list[str | int] | None = None):
    # Container._body: list[tuple[Key | None, Item]]
    # Table._value: Container
    # AoT._body: list[Table]
    # Array._value: list[_ArrayItemGroup]

    path = path or []
    # indent = '  ' * len(path)
    node = reduce(getitem, path, root)
    it = None
    trivia = None
    if isinstance(node, Container):
        it = node.body
    else:
        trivia = node.trivia
        if isinstance(node, AbstractTable):
            it = node.value.body
        elif isinstance(node, AoT):
            it = enumerate(node.body)
        elif isinstance(node, Array):
            it = enumerate(node._value)

    if it is None:
        raise ValueError(root)

    for k, v in it:
        # print(f'{indent}{k!r} = {type(v).__name__} {trivia=}')
        new_path = path if k is None else [*path, cannonicalize_key(k)]
        if isinstance(v, Container | AbstractTable | AoT | Array):
            yield from walk(root, new_path)
        else:
            yield new_path, v
            # if isinstance(v, _ArrayItemGroup):
            #     vc = getattr(v.comment, 'trivia', None)
            # elif isinstance(v, Comment):
            #     vc = v.trivia
            # elif isinstance(v, Whitespace):
            #     vc = None
            # else:
            #     vc = getattr(v, 'trivia', None)
            # if vc is not None:
            #     vc = asdict(vc)
            # vv = getattr(v, 'value', v)
            # print(f'{indent}  {vv=} {vc=}')


def main():
    doc = tomlkit.load(open('/opt/mantis/pyproject.toml'))

    for k, v in walk(doc):
        print('.'.join(map(str, k)), '=', repr(v))


if __name__ == '__main__':
    main()
