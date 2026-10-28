import ast
import calendar
import math
import operator
from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.agent.tools.base import ToolContext, ToolError, ToolResult, tool

# --- calculate -------------------------------------------------------------

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": lambda *args: sum(args),
    "sqrt": math.sqrt,
}


def safe_eval(expression: str) -> float:
    """Avalia uma expressão aritmética sem `eval`: só números, operadores e funções da allowlist."""

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolError("Expoente demasiado grande.")
            return _BINARY_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](visit(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
        ):
            return _FUNCTIONS[node.func.id](*[visit(arg) for arg in node.args])
        raise ToolError(f"Expressão não suportada: {ast.unparse(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(
            f"Expressão inválida: {expression}. Usar ponto decimal e sem separador de milhares (1250.50, não 1.250,50)."
        ) from exc
    try:
        return visit(tree)
    except ZeroDivisionError as exc:
        raise ToolError("Divisão por zero.") from exc


class CalculateParams(BaseModel):
    expression: str = Field(
        description="Expressão aritmética com ponto decimal, ex.: '(1650 - 1500) / 1500 * 100' ou "
        "'round(1250.5 * 14, 2)'. Funções: abs, round, min, max, sum, sqrt."
    )


@tool(
    name="calculate",
    description="Calcula uma expressão aritmética de forma exata. Usar sempre para contas em vez de calcular de cabeça.",
    params=CalculateParams,
)
def calculate(params: CalculateParams, ctx: ToolContext) -> ToolResult:
    value = safe_eval(params.expression)
    if isinstance(value, float):
        value = round(value, 10)
    return ToolResult(content={"expression": params.expression, "result": value}, summary=f"{params.expression} = {value}")


# --- percentage_change -----------------------------------------------------


class PercentageChangeParams(BaseModel):
    old_value: float = Field(description="Valor inicial (ex.: salário anterior).")
    new_value: float = Field(description="Valor final (ex.: salário novo).")


@tool(
    name="percentage_change",
    description="Diferença absoluta e variação percentual entre dois valores (ex.: aumento salarial).",
    params=PercentageChangeParams,
)
def percentage_change(params: PercentageChangeParams, ctx: ToolContext) -> ToolResult:
    if params.old_value == 0:
        raise ToolError("O valor inicial não pode ser 0.")
    difference = params.new_value - params.old_value
    percent = difference / abs(params.old_value) * 100
    content = {
        "old_value": params.old_value,
        "new_value": params.new_value,
        "difference": round(difference, 2),
        "percent_change": round(percent, 2),
    }
    return ToolResult(content=content, summary=f"{params.old_value} → {params.new_value}: {difference:+.2f} ({percent:+.2f}%)")


# --- datas -----------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def parse_date(value: str) -> date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ToolError(f"Data inválida: '{value}'. Formatos aceites: AAAA-MM-DD ou DD/MM/AAAA.")


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def calendar_difference(start: date, end: date) -> tuple[int, int, int]:
    """Diferença em (anos, meses, dias) de calendário, com start <= end."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if add_months(start, months) > end:
        months -= 1
    days = (end - add_months(start, months)).days
    return months // 12, months % 12, days


class DateDifferenceParams(BaseModel):
    start_date: str = Field(description="Data inicial (AAAA-MM-DD ou DD/MM/AAAA).")
    end_date: str | None = Field(default=None, description="Data final. Omitir para usar a data de hoje.")


@tool(
    name="date_difference",
    description="Tempo entre duas datas: total de dias e anos/meses/dias de calendário (ex.: antiguidade, duração de contrato).",
    params=DateDifferenceParams,
)
def date_difference(params: DateDifferenceParams, ctx: ToolContext) -> ToolResult:
    start = parse_date(params.start_date)
    end = parse_date(params.end_date) if params.end_date else date.today()
    sign = 1
    if end < start:
        start, end, sign = end, start, -1
    years, months, days = calendar_difference(start, end)
    content = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_days": sign * (end - start).days,
        "years": years,
        "months": months,
        "days": days,
        "direction": "end_after_start" if sign > 0 else "end_before_start",
    }
    return ToolResult(content=content, summary=f"{start} → {end}: {years}a {months}m {days}d ({(end - start).days} dias)")


class DateAddParams(BaseModel):
    start_date: str = Field(description="Data de partida (AAAA-MM-DD ou DD/MM/AAAA).")
    years: int = 0
    months: int = 0
    days: int = 0


@tool(
    name="date_add",
    description="Soma (ou subtrai, com valores negativos) anos/meses/dias a uma data (ex.: fim do período experimental).",
    params=DateAddParams,
)
def date_add(params: DateAddParams, ctx: ToolContext) -> ToolResult:
    start = parse_date(params.start_date)
    result = add_months(start, params.years * 12 + params.months)
    result = date.fromordinal(result.toordinal() + params.days)
    content = {"start_date": start.isoformat(), "result_date": result.isoformat(), "weekday": result.strftime("%A")}
    return ToolResult(content=content, summary=f"{start} + {params.years}a {params.months}m {params.days}d = {result}")
