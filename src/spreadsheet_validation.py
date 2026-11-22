"""Deterministic validation for a deliberately small spreadsheet-formula subset.

This is not an Excel or Google Sheets emulator. It evaluates common tutorial examples
so incorrect worked-example outputs can be caught before a Blogger draft is created.
Unsupported functions, references, or formula syntax are reported explicitly.
"""
import ast
import math
import operator
import re
from typing import Any, Dict, Iterable, List, Tuple


class FormulaValidationError(ValueError):
    """Raised when a spreadsheet example cannot be safely evaluated."""


_CELL_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")
_RANGE_RE = re.compile(r"^([A-Z]{1,3}[1-9][0-9]*):([A-Z]{1,3}[1-9][0-9]*)$", re.I)
_FUNCTIONS = {"SUM", "AVERAGE", "COUNT", "COUNTA", "MIN", "MAX", "COUNTIF", "AVERAGEIF", "IF"}
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow,
}
_CMPOPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _column_number(label: str) -> int:
    result = 0
    for char in label:
        result = result * 26 + ord(char) - 64
    return result


def _cell_parts(reference: str) -> Tuple[int, int]:
    match = _CELL_RE.fullmatch(reference.upper())
    if not match:
        raise FormulaValidationError(f"Unsupported cell reference: {reference}")
    return int(match.group(2)), _column_number(match.group(1))


def _coerce(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            number = float(stripped.replace(",", ""))
            return int(number) if number.is_integer() else number
        except ValueError:
            return stripped
    return value


def _flatten(values: Iterable[Any]) -> List[Any]:
    flattened = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        else:
            flattened.append(value)
    return flattened


def _functions():
    def numeric(values):
        return [float(v) for v in _flatten(values) if isinstance(v, (int, float)) and not isinstance(v, bool)]

    def average(values):
        nums = numeric(values)
        if not nums:
            raise FormulaValidationError("AVERAGE has no numeric values.")
        return sum(nums) / len(nums)

    def countif(values, criteria):
        return sum(1 for value in _flatten([values]) if value == criteria)

    def averageif(criteria_values, criteria, average_values=None):
        left = _flatten([criteria_values])
        right = _flatten([average_values]) if average_values is not None else left
        if len(left) != len(right):
            raise FormulaValidationError("AVERAGEIF criteria and average ranges must have equal lengths.")
        chosen = [value for test, value in zip(left, right) if test == criteria]
        return average(chosen)

    return {
        "SUM": lambda *args: sum(numeric(args)),
        "AVERAGE": lambda *args: average(args),
        "COUNT": lambda *args: len(numeric(args)),
        "COUNTA": lambda *args: sum(1 for v in _flatten(args) if v not in ("", None)),
        "MIN": lambda *args: min(numeric(args)),
        "MAX": lambda *args: max(numeric(args)),
        "COUNTIF": countif,
        "AVERAGEIF": averageif,
        "IF": lambda condition, yes, no: yes if condition else no,
    }


def _eval_node(node, functions):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, functions)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)):
            return node.value
        raise FormulaValidationError("Unsupported constant in formula.")
    if isinstance(node, ast.List):
        return [_eval_node(item, functions) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(item, functions) for item in node.elts)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_node(node.left, functions), _eval_node(node.right, functions))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval_node(node.operand, functions))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMPOPS:
        return _CMPOPS[type(node.ops[0])](_eval_node(node.left, functions), _eval_node(node.comparators[0], functions))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions:
        return functions[node.func.id](*[_eval_node(arg, functions) for arg in node.args])
    raise FormulaValidationError(f"Unsupported formula expression: {type(node).__name__}")


def evaluate_formula(formula: str, cells: Dict[str, Any]) -> Any:
    """Evaluate a supported formula against explicit A1-style cell values."""
    if not isinstance(formula, str) or not formula.strip().startswith("="):
        raise FormulaValidationError("Formula must begin with '='.")
    grid = {}
    for reference, value in (cells or {}).items():
        row, col = _cell_parts(str(reference).upper())
        grid[(row, col)] = _coerce(value)

    expression = formula.strip()[1:]
    # Preserve quoted text while normalizing function names and references.
    quoted = []
    def stash(match):
        quoted.append(match.group(0))
        return f"__STRING_{len(quoted)-1}__"
    expression = re.sub(r'"(?:[^"]|"")*"', stash, expression)
    expression = expression.upper()

    def range_value(match):
        first, last = match.group(1).upper(), match.group(2).upper()
        r1, c1 = _cell_parts(first)
        r2, c2 = _cell_parts(last)
        if r2 < r1 or c2 < c1:
            raise FormulaValidationError(f"Reversed range: {first}:{last}")
        values = []
        for row in range(r1, r2 + 1):
            for col in range(c1, c2 + 1):
                if (row, col) not in grid:
                    raise FormulaValidationError(
                        f"Range {first}:{last} is missing sample cell at row {row}, column {col}."
                    )
                values.append(grid[(row, col)])
        return repr(values)

    expression = re.sub(r"\b([A-Z]{1,3}[1-9][0-9]*):([A-Z]{1,3}[1-9][0-9]*)\b", range_value, expression)

    def cell_value(match):
        reference = match.group(0)
        row, col = _cell_parts(reference)
        if (row, col) not in grid:
            raise FormulaValidationError(f"Formula references missing cell {reference}.")
        return repr(grid[(row, col)])

    expression = re.sub(r"\b[A-Z]{1,3}[1-9][0-9]*\b", cell_value, expression)
    for index, literal in enumerate(quoted):
        expression = expression.replace(f"__STRING_{index}__", repr(literal[1:-1].replace('""', '"')))
    expression = expression.replace("<>", "!=")
    expression = re.sub(r"(?<![<>=!])=(?!=)", "==", expression)
    expression = expression.replace("^", "**")
    expression = re.sub(r"\b([A-Z]+)\s*\(", lambda m: m.group(1) + "(", expression)
    try:
        tree = ast.parse(expression, mode="eval")
        return _eval_node(tree, _functions())
    except FormulaValidationError:
        raise
    except Exception as exc:
        raise FormulaValidationError(f"Could not evaluate formula safely: {exc}") from exc


def validate_spreadsheet_examples(examples: List[Dict[str, Any]]) -> List[str]:
    """Check supplied formula examples and their expected results."""
    failures = []
    for index, example in enumerate(examples or [], start=1):
        if not isinstance(example, dict):
            failures.append(f"Spreadsheet example {index} is not an object.")
            continue
        formula = str(example.get("formula") or "")
        application = str(example.get("application") or "").strip()
        formula_cell = str(example.get("formula_cell") or "").strip().upper()
        if not application:
            failures.append(f"Spreadsheet example {index} must name Excel or Google Sheets.")
            continue
        try:
            _cell_parts(formula_cell)
        except FormulaValidationError:
            failures.append(f"Spreadsheet example {index} must provide a valid formula cell such as D2.")
            continue
        cells = example.get("cells")
        if not isinstance(cells, list):
            failures.append(f"Spreadsheet example {index} must provide a list of cell references and values.")
            continue
        cell_map = {}
        try:
            for item in cells:
                if not isinstance(item, dict) or not item.get("reference"):
                    raise FormulaValidationError("Each sample cell needs a reference and value.")
                ref = str(item["reference"]).upper()
                if ref in cell_map:
                    raise FormulaValidationError(f"Duplicate sample cell {ref}.")
                cell_map[ref] = item.get("value", "")
            actual = evaluate_formula(formula, cell_map)
        except (FormulaValidationError, TypeError, ValueError) as exc:
            failures.append(f"Spreadsheet example {index} could not be verified: {exc}")
            continue

        expected = _coerce(example.get("expected_result"))
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            matches = math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
        else:
            matches = actual == expected
        if not matches:
            failures.append(
                f"Spreadsheet example {index} has an incorrect expected result: "
                f"formula calculates {actual!r}, but the draft states {expected!r}."
            )
    return failures
