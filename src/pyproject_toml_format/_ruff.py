import importlib.util
import io
import json
import subprocess
import sys
from typing import NotRequired, TypedDict, cast

import tomlkit.items


class LinterCategory(TypedDict):
    prefix: str
    name: str


class Linter(TypedDict):
    prefix: str
    name: str
    categories: NotRequired[list[LinterCategory]]


class Rule(TypedDict):
    name: str
    code: str
    linter: str
    summary: str
    message_formats: list[str]
    fix: str
    explanation: str
    preview: bool


FORMATTER_RULES = [
    ('W191', 'tab-indentation - conflicts with formatter'),
    ('E111', 'indentation-with-invalid-multiple - conflicts with formatter'),
    ('E114', 'indentation-with-invalid-multiple-comment - conflicts with formatter'),
    ('E117', 'over-indented - conflicts with formatter'),
    ('D206', 'indent-with-spaces - conflicts with formatter'),
    ('D300', 'triple-single-quotes - conflicts with formatter'),
    ('Q000', 'bad-quotes-inline-string - conflicts with formatter'),
    ('Q001', 'bad-quotes-multiline-string - conflicts with formatter'),
    ('Q002', 'bad-quotes-docstring - conflicts with formatter'),
    ('Q003', 'avoidable-escaped-quote - conflicts with formatter'),
    ('COM812', 'missing-trailing-comma - conflicts with formatter'),
    ('COM819', 'prohibited-trailing-comma - conflicts with formatter'),
    ('E501', 'line-too-long - see formatter documentation'),
]
FORMATTER_RULES_SET = {i[0] for i in FORMATTER_RULES}


def format_ruff_lint_ignore(pyproject_toml: tomlkit.TOMLDocument) -> bool:
    if not importlib.util.find_spec('ruff'):
        return False

    try:
        tool_ruff_lint = cast('tomlkit.items.Table', pyproject_toml['tool']['ruff']['lint'])
        if tool_ruff_lint['select'] != ['ALL']:
            return False
    except (KeyError, TypeError):
        return False

    try:
        linters_data: list[Linter] = json.loads(subprocess.check_output([sys.executable, '-m', 'ruff', 'linter', '--output-format=json']))  # noqa: S603
        rules_data: list[Rule] = json.loads(subprocess.check_output([sys.executable, '-m', 'ruff', 'rule', '--all', '--output-format=json']))  # noqa: S603
    except subprocess.CalledProcessError:
        return False

    linter_prefixes = [(linter['prefix'] + category['prefix'], linter['name']) for linter in linters_data for category in linter.get('categories', [{'prefix': ''}])]
    linters_by_prefix = {i[0]: i for i in linter_prefixes}
    linter_weights_by_prefix = {i[0]: idx for idx, i in enumerate(linter_prefixes)}

    rules_by_code = {rule['code']: rule for rule in rules_data}

    linter_weights_by_name = {linter['name']: idx for idx, linter in enumerate(linters_data)}

    rule_weights = {rule['code']: (linter_weights_by_name[rule['linter']], rule['code']) for rule in rules_data}

    raw_codes = tool_ruff_lint.get('ignore', [])
    out_linters = []
    out_rules = []

    for code in raw_codes:
        if code in FORMATTER_RULES_SET:
            continue

        if code in linters_by_prefix:
            out_linters.append(linters_by_prefix[code])
            continue

        if code in rules_by_code:
            out_rules.append(rules_by_code[code])
            continue

        out_rules.extend(rule for rule in rules_data if rule['code'].startswith(code))

    out_linters.sort(key=lambda i: linter_weights_by_prefix[i[0]])
    out_rules.sort(key=lambda rule: rule_weights[rule['code']])

    ignore_toml_buf = io.StringIO()
    print('[', file=ignore_toml_buf)
    print(*('    "{}", # {}'.format(*i) for i in FORMATTER_RULES), sep='\n', file=ignore_toml_buf)
    if out_linters:
        print(file=ignore_toml_buf)
        print(*('    "{}", # linter: {}'.format(*i) for i in out_linters), sep='\n', file=ignore_toml_buf)
    if out_rules:
        print(file=ignore_toml_buf)
        print(*('    "{code}", # {name}'.format(**rule) for rule in out_rules), sep='\n', file=ignore_toml_buf)
    print(']', end='', file=ignore_toml_buf)

    formatted = ignore_toml_buf.getvalue()

    try:
        if formatted == tool_ruff_lint['ignore'].as_string():
            return False
    except KeyError:
        pass

    tool_ruff_lint['ignore'] = tomlkit.array(formatted)

    return True
