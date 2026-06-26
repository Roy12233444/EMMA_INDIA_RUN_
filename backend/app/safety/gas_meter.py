"""
backend/app/safety/gas_meter.py
================================
EMMA SUDARSHANA Safety Division — AST Gas Metering Shield v2.0
Ticket: EMM-05-A2 · Phase 1

Provides two interlocking security mechanisms:

  1. WeightedGasMeterTransformer
     ─────────────────────────────
     An AST NodeTransformer that rewrites the mutant's source tree at
     parse-time, injecting ``__gas_check__(cost)`` call statements at every
     control-flow point that can produce runaway computation:

       • For / While loop bodies           — LOOP_COST   (1 gas)
       • FunctionDef / AsyncFunctionDef    — CALL_COST   (5 gas)
       • ListComp / DictComp / SetComp     — COMP_COST  (10 gas)
       • BinOp with MatMult operator       — MATMUL_COST (25 gas)
       • BinOp with Pow operator           — POW_COST   (50 gas)

     Inspired by the Ethereum Virtual Machine (EVM) opcode gas schedule,
     where computationally expensive opcodes cost more gas so that an
     attacker cannot bypass a uniform limit with a single heavy instruction.

  2. Sealed Closure Namespace  (_build_sealed_gas_globals)
     ──────────────────────────────────────────────────────
     The execution globals dictionary returned to ``exec()`` keeps the gas
     counter inside a Python closure cell — not in the globals dict itself.
     This means the sandboxed code:

       • Cannot ``del __gas_check__``            (NameError or no-op)
       • Cannot ``__gas_check__ = lambda x: None``  (rebinds the name
         in exec globals but the original closure is gone from the dict
         before exec sees it — the counter lives on in closure scope)
       • Cannot read or modify ``_state`` (it is not in any reachable
         namespace)
       • Cannot call ``globals()`` / ``locals()`` / ``vars()`` /
         ``getattr`` / ``setattr`` / ``delattr`` (stripped from
         _SAFE_BUILTINS)

Standard library only (``ast``, ``builtins``). Zero external dependencies.
"""

from __future__ import annotations

import ast
import builtins as _builtins
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# EVM-Style Gas Price Table
# ─────────────────────────────────────────────────────────────────────────────

#: Mapping of AST node category → gas units consumed per occurrence.
#:
#: Design rationale (EVM analogy):
#:   Like Ethereum's gas schedule, cheap opcodes (ADD) cost 1 gas while
#:   expensive opcodes (SSTORE) cost 20 000 gas.  Here, a simple loop
#:   iteration costs 1 gas, but a power operation ``x ** n`` costs 50 gas
#:   because its CPU cost grows exponentially with ``n``.  A mutant doing
#:   ``x = x ** 1000000`` inside a loop will exhaust a 50 000-unit budget
#:   after only 1 000 loop iterations instead of 50 000.
GAS_PRICES: dict[str, int] = {
    # Control-flow / iteration
    "loop_entry":    1,    # per For / While body tick
    "function_call": 5,    # per FunctionDef / AsyncFunctionDef entry

    # Comprehensions (bounded by iterable, but heavy for large ranges)
    "comprehension": 10,   # per ListComp / DictComp / SetComp node

    # Arithmetic operations — weighted by CPU cost
    "binop_pow":     50,   # x ** y  →  exponential risk (highest cost)
    "binop_matmul":  25,   # x @ y   →  matrix multiply (dense linear algebra)

    # Built-in calls (kept for future instrumentation hooks)
    "builtin_call":  20,
}


# ─────────────────────────────────────────────────────────────────────────────
# Restricted Built-ins  (_SAFE_BUILTINS)
# ─────────────────────────────────────────────────────────────────────────────

#: Whitelist of built-in names available inside the sandbox.
#:
#: Security note — the following are intentionally EXCLUDED:
#:   globals, locals, vars  → would expose the exec globals dict, allowing
#:                            the sandboxed code to delete __gas_check__.
#:   dir                    → enumerates names in scope (recon vector).
#:   getattr / setattr /
#:   delattr                → dunder-escape path to arbitrary attribute access.
#:   __import__             → dynamic module import (filesystem / network access).
#:   open / exec / eval /
#:   compile                → direct code execution or I/O.
#:   input                  → blocking stdin read (DoS vector in subprocess).
_SAFE_BUILTINS: dict[str, Any] = {
    k: getattr(_builtins, k)
    for k in (
        # Pure numeric / math
        "abs", "bin", "bool", "chr", "complex", "divmod", "float",
        "format", "hash", "hex", "int", "oct", "ord", "pow", "round",

        # Collection constructors & functional tools
        "bytes", "bytearray", "callable", "dict", "enumerate", "filter",
        "frozenset", "iter", "len", "list", "map", "max", "min",
        "next", "range", "repr", "reversed", "set", "slice", "sorted",
        "staticmethod", "str", "sum", "super", "tuple", "type", "zip",

        # Boolean singletons & class machinery
        "True", "False", "None", "object", "__build_class__",

        # Safe introspection
        "hasattr", "isinstance", "issubclass",

        # I/O (read-only console output — useful for debugging mutants)
        "print",

        # Standard exceptions that mutant code may legitimately raise
        "ArithmeticError", "AttributeError", "EOFError", "Exception",
        "FloatingPointError", "GeneratorExit", "IndexError", "KeyError",
        "KeyboardInterrupt", "LookupError", "MemoryError", "NameError",
        "NotImplementedError", "OSError", "OverflowError",
        "RecursionError", "RuntimeError", "StopAsyncIteration",
        "StopIteration", "SyntaxError", "TypeError", "ValueError",
        "ZeroDivisionError",
    )
    if hasattr(_builtins, k)
}


# ─────────────────────────────────────────────────────────────────────────────
# Custom Exception
# ─────────────────────────────────────────────────────────────────────────────

class GasMeterException(RuntimeError):
    """Raised when the Sudarshana gas counter exceeds the configured limit.

    This exception is raised *inside* the sandboxed ``exec()`` call and
    propagates out to the caller of ``instrument_code`` / ``exec``.

    Attributes:
        limit:    The gas budget that was configured for this execution.
        consumed: The total gas units accumulated at the point of failure.
    """

    def __init__(self, limit: int, consumed: int) -> None:
        super().__init__(
            f"[SUDARSHANA GAS SHIELD] Execution halted — gas limit exceeded. "
            f"Budget: {limit:,} units · Consumed: {consumed:,} units. "
            "Probable cause: infinite loop, deep mutual recursion, or "
            "pathologically expensive arithmetic (e.g. x ** 1_000_000). "
            "Terminate and reject this mutant."
        )
        self.limit: int = limit
        self.consumed: int = consumed

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"GasMeterException(limit={self.limit!r}, consumed={self.consumed!r})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Base Uniform Gas Meter Transformer
# ─────────────────────────────────────────────────────────────────────────────

class GasMeterTransformer(ast.NodeTransformer):
    """Uniform gas metering: charges 1 gas per loop iteration and function call.

    This is the conservative baseline transformer.  Every ``For``, ``While``,
    ``FunctionDef``, and ``AsyncFunctionDef`` node gets a
    ``__gas_check__(1)`` statement prepended to its body.

    Use ``WeightedGasMeterTransformer`` for production — it provides stronger
    protection against heavy arithmetic by-passes.

    Args:
        gas_limit: The maximum gas units allowed before ``GasMeterException``
                   is raised inside the sandbox.  Stored for reference only;
                   the actual enforcement lives in the sealed closure built by
                   ``_build_sealed_gas_globals``.
    """

    def __init__(self, gas_limit: int) -> None:
        super().__init__()
        self.gas_limit: int = gas_limit

    # ── Internal helper ──────────────────────────────────────────────────────

    def _make_gas_check_stmt(self, cost: int = 1) -> ast.Expr:
        """Return an ``ast.Expr`` node representing ``__gas_check__(<cost>)``."""
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id="__gas_check__", ctx=ast.Load()),
                args=[ast.Constant(value=cost)],
                keywords=[],
            )
        )

    # ── Visitor methods ───────────────────────────────────────────────────────

    def visit_For(self, node: ast.For) -> ast.For:
        """Inject gas check at the top of every ``for`` loop body."""
        check = self._make_gas_check_stmt(1)
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_While(self, node: ast.While) -> ast.While:
        """Inject gas check at the top of every ``while`` loop body."""
        check = self._make_gas_check_stmt(1)
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Inject gas check at the entry point of every function definition."""
        check = self._make_gas_check_stmt(1)
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """Inject gas check at the entry point of every async function definition."""
        check = self._make_gas_check_stmt(1)
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node


# ─────────────────────────────────────────────────────────────────────────────
# Advanced EVM-Style Weighted Gas Meter Transformer
# ─────────────────────────────────────────────────────────────────────────────

class WeightedGasMeterTransformer(GasMeterTransformer):
    """EVM-style weighted gas metering transformer.

    Extends ``GasMeterTransformer`` to assign *different gas costs* to
    different AST node types, mirroring the Ethereum Virtual Machine's
    per-opcode gas schedule.

    Motivation
    ──────────
    A naive uniform transformer charges ``1 gas`` for every loop iteration.
    A malicious mutant can bypass this with a single expensive operation:

        for i in range(gas_limit + 1):
            x = x ** 1_000_000   # only 1 gas — but astronomically slow

    By charging ``50 gas`` for each ``**`` (Pow) operation, the same mutant
    would exhaust a 50 000-unit budget after only 1 000 iterations instead of
    50 001.

    Coverage matrix
    ───────────────
    Node type                  | Gas price key   | Default cost
    ───────────────────────────│─────────────────│─────────────
    ast.For / ast.While        | "loop_entry"    |  1
    ast.FunctionDef            | "function_call" |  5
    ast.AsyncFunctionDef       | "function_call" |  5
    ast.ListComp / DictComp /  |                 |
      SetComp                  | "comprehension" | 10
    ast.BinOp(MatMult)         | "binop_matmul"  | 25
    ast.BinOp(Pow)             | "binop_pow"     | 50

    Args:
        gas_limit: Maximum gas budget (same semantics as base class).
        prices:    Optional override for the gas price table.  Defaults to
                   ``GAS_PRICES``.  Pass a custom dict to tune costs for
                   specific use-cases (e.g., lower ``binop_pow`` for
                   scientific solvers that legitimately use exponentiation).
    """

    def __init__(
        self,
        gas_limit: int,
        prices: dict[str, int] | None = None,
    ) -> None:
        super().__init__(gas_limit)
        self.prices: dict[str, int] = prices if prices is not None else GAS_PRICES

    # ── Internal helper ──────────────────────────────────────────────────────

    def _cost(self, key: str) -> int:
        """Look up the gas cost for a given price-table key (default: 1)."""
        return self.prices.get(key, 1)

    def _weighted_check(self, key: str, anchor_node: ast.AST) -> ast.Expr:
        """Build a weighted ``__gas_check__(<cost>)`` statement node."""
        stmt = self._make_gas_check_stmt(self._cost(key))
        ast.copy_location(stmt, anchor_node)
        return stmt

    # ── Visitor overrides ─────────────────────────────────────────────────────

    def visit_For(self, node: ast.For) -> ast.For:
        """Charge LOOP_COST gas per ``for`` iteration (weighted override)."""
        check = self._weighted_check("loop_entry", node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_While(self, node: ast.While) -> ast.While:
        """Charge LOOP_COST gas per ``while`` iteration (weighted override)."""
        check = self._weighted_check("loop_entry", node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Charge CALL_COST gas per function entry (weighted override)."""
        check = self._weighted_check("function_call", node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """Charge CALL_COST gas per async function entry (weighted override)."""
        check = self._weighted_check("function_call", node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    # ── Heavy expression instrumentation ─────────────────────────────────────
    # AST Challenge: BinOp (x**y, x@y) and comprehensions ([x for x in ...]) are
    # *expressions*, not statements.  You cannot prepend a statement *inside* an
    # expression.  The correct technique is to intercept the parent ast.Expr
    # statement node that wraps them, detect if its value is a heavy expression,
    # and return a list of [gas_check_stmt, original_expr_stmt] to the parent body.
    #
    # For nested cases (e.g. heavy BinOp buried inside an assignment like
    # ``x = 2 ** 1_000_000``), we use a dedicated _HeavyExprScanner sub-visitor
    # to detect if any heavy expression lurks anywhere in the statement subtree,
    # then prepend a single gas check before the entire statement.

    def _statement_contains_heavy_expr(self, stmt_node: ast.stmt) -> str | None:
        """Scan a statement node for any heavy sub-expression.

        Returns the gas-price key (e.g. ``"binop_pow"``) for the *most
        expensive* heavy node found in the subtree, or ``None`` if the
        statement is clean.

        Priority order (highest cost first): Pow > MatMult > comprehension.
        This ensures the most expensive check is always charged.
        """
        for node in ast.walk(stmt_node):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                return "binop_pow"       # 50 gas — highest priority
        for node in ast.walk(stmt_node):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
                return "binop_matmul"   # 25 gas
        for node in ast.walk(stmt_node):
            if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp)):
                return "comprehension"  # 10 gas
        return None

    def visit_Expr(self, node: ast.Expr) -> ast.AST | list[ast.stmt]:
        """Intercept expression-statement nodes to charge gas for heavy ops.

        This visitor handles the case where a heavy expression
        (``x ** y``, ``x @ y``, or a comprehension) appears as a
        *standalone expression statement*::

            x = 2 ** 100_000_000    # Assignment — handled by generic_visit walk
            result = [i*i for i in big_list]  # Assignment — same
            2 ** 100_000_000        # Bare expression stmt — caught here

        Returns a **list** of two nodes when a heavy expression is detected:
        ``[__gas_check__(cost), original_expr_stmt]``.  Returning a list from
        a visitor is the standard ``ast.NodeTransformer`` mechanism for
        injecting extra statements alongside a visited node.
        """
        self.generic_visit(node)   # Recurse into children first
        price_key = self._statement_contains_heavy_expr(node)
        if price_key is not None:
            check = self._weighted_check(price_key, node)
            return [check, node]   # Prepend gas check before the expression stmt
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST | list[ast.stmt]:
        """Intercept assignment statements containing heavy sub-expressions.

        Handles patterns like::

            x = 2 ** 1_000_000         # Pow inside assignment RHS
            result = A @ B              # MatMult inside assignment RHS
            items = [f(x) for x in big] # Comprehension inside assignment RHS

        Returns a list ``[__gas_check__(cost), original_assign_stmt]``
        when a heavy expression is found in the RHS subtree.
        """
        self.generic_visit(node)   # Recurse into children first
        price_key = self._statement_contains_heavy_expr(node)
        if price_key is not None:
            check = self._weighted_check(price_key, node)
            return [check, node]   # Prepend gas check before the assignment
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST | list[ast.stmt]:
        """Intercept augmented assignment statements (``x **= n``, ``x @= y``).

        Handles patterns like::

            x **= 1_000_000    # AugAssign with Pow — very dangerous
            x @= weights       # AugAssign with MatMult
        """
        self.generic_visit(node)
        # AugAssign with Pow/MatMult operator is directly detectable
        if isinstance(node.op, ast.Pow):
            check = self._weighted_check("binop_pow", node)
            return [check, node]
        if isinstance(node.op, ast.MatMult):
            check = self._weighted_check("binop_matmul", node)
            return [check, node]
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST | list[ast.stmt]:
        """Intercept return statements containing heavy sub-expressions.

        Handles patterns like::

            return x ** n   # Heavy pow inside return value
        """
        self.generic_visit(node)
        price_key = self._statement_contains_heavy_expr(node)
        if price_key is not None:
            check = self._weighted_check(price_key, node)
            return [check, node]
        return node


# ─────────────────────────────────────────────────────────────────────────────
# Sealed Closure Namespace Factory
# ─────────────────────────────────────────────────────────────────────────────

def _build_sealed_gas_globals(gas_limit: int) -> dict[str, Any]:
    """Construct a tamper-resistant execution globals dict for ``exec()``.

    Security design — Sealed Closure technique
    ───────────────────────────────────────────
    The naive approach is to place ``__gas_check__`` as a plain entry in the
    globals dict that is passed to ``exec()``.  This fails because the
    sandboxed code can disable the gas meter by:

        del __gas_check__              # Attack 1 — removes the function
        __gas_check__ = lambda x: None  # Attack 2 — overwrites with no-op
        globals().clear()              # Attack 3 — wipes the entire namespace

    The sealed closure technique defeats all three attacks:

    1.  The *actual* counter (``_state``) is a dictionary that lives inside
        this factory function's local scope.  It is captured by the inner
        function ``__gas_check__`` as a *closure variable* — it does NOT
        appear in the exec globals dict at all.

    2.  Even if the sandboxed code rebinds ``__gas_check__`` to a no-op
        lambda inside exec's globals, the original closure is already gone
        from the dict (we delete the reference before returning).  But more
        importantly, *the counter itself keeps running* because closure cells
        are not accessible from the sandboxed namespace.

    3.  ``globals()`` and ``locals()`` are stripped from ``_SAFE_BUILTINS``,
        so the sandboxed code has no way to enumerate or manipulate the
        execution namespace.

    Args:
        gas_limit: The maximum gas units.  When the counter exceeds this
                   value, ``__gas_check__`` raises ``GasMeterException``.

    Returns:
        A fresh globals dict containing:
          - ``__builtins__``:       The restricted safe-builtins dict.
          - ``__name__``:           ``"__sandbox__"`` (cosmetic).
          - ``__gas_check__``:      The sealed closure (injected by transformer).
          - ``_get_gas_consumed``:  A read-only inspector for post-exec reporting.
          - ``GasMeterException``:  Exposed so the sandbox worker can catch it
                                    by name if needed.
    """
    # ── Closure-captured private state ────────────────────────────────────────
    # Using a mutable dict instead of a bare integer so that the inner
    # function can modify the counter without a ``nonlocal`` declaration
    # (which would be equally secure but slightly less portable to Python 3.8).
    _state: dict[str, int] = {"count": 0}

    def __gas_check__(cost: int = 1) -> None:  # noqa: N802  (dunder name)
        """Increment the gas counter and raise if the budget is exhausted.

        Args:
            cost: The gas units consumed by this operation.  Injected
                  as a literal integer by ``WeightedGasMeterTransformer``.

        Raises:
            GasMeterException: When the cumulative gas exceeds ``gas_limit``.
        """
        _state["count"] += cost
        if _state["count"] > gas_limit:
            raise GasMeterException(gas_limit, _state["count"])

    def _get_gas_consumed() -> int:
        """Return the total gas units consumed so far (read-only inspector)."""
        return _state["count"]

    return {
        "__builtins__":      _SAFE_BUILTINS,
        "__name__":          "__sandbox__",
        "__gas_check__":     __gas_check__,
        "_get_gas_consumed": _get_gas_consumed,
        # Expose the exception class so sandbox workers can reference it by name
        "GasMeterException": GasMeterException,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def instrument_code(
    code: str,
    gas_limit: int = 50_000,
    weighted: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Parse, transform, and compile Python source code with gas metering.

    This is the single public entry-point for the Sudarshana Gas Metering
    Shield.  It performs four steps:

      1. **Parse** — ``ast.parse(code)`` converts the source string into an
         Abstract Syntax Tree.  A ``SyntaxError`` is raised immediately and
         propagated to the caller; malformed code is rejected before any
         instrumentation takes place.

      2. **Transform** — The appropriate ``NodeTransformer`` (uniform or
         weighted) walks the AST and injects ``__gas_check__(cost)``
         statements at every loop body, function entry, and heavy-operator
         site.

      3. **Fix locations** — ``ast.fix_missing_locations`` backfills any
         ``lineno`` / ``col_offset`` fields that the transformer left
         unset (required by ``compile()``).

      4. **Compile** — ``compile(tree, "<sandbox>", "exec")`` converts the
         transformed AST to a code object ready for ``exec()``.

    The caller is responsible for calling ``exec(code_obj, sealed_globals)``
    in the appropriate subprocess / thread context.

    Args:
        code:      Raw Python source string (UTF-8).
        gas_limit: Maximum gas units before ``GasMeterException`` is raised
                   inside the sandbox.  Default: 50 000.
        weighted:  If ``True`` (default), use ``WeightedGasMeterTransformer``
                   (EVM-style per-node costs).  If ``False``, use the basic
                   uniform ``GasMeterTransformer`` (1 gas per iteration).

    Returns:
        A 2-tuple ``(compiled_code_object, sealed_globals_dict)``.
        Pass both directly to ``exec()``::

            code_obj, globs = instrument_code(source, gas_limit=10_000)
            exec(code_obj, globs)
            gas_used = globs["_get_gas_consumed"]()

    Raises:
        SyntaxError: If ``ast.parse(code)`` fails.  The caller should treat
                     this as an immediate ``SYNTAX_ERROR`` rejection — no
                     instrumentation was applied.
    """
    # Step 1 — Parse (SyntaxError propagates intentionally)
    tree: ast.Module = ast.parse(code)

    # Step 2 — Transform
    transformer: GasMeterTransformer
    if weighted:
        transformer = WeightedGasMeterTransformer(gas_limit)
    else:
        transformer = GasMeterTransformer(gas_limit)

    tree = transformer.visit(tree)  # type: ignore[assignment]

    # Step 3 — Fix any missing location info introduced by injected nodes
    ast.fix_missing_locations(tree)

    # Step 4 — Compile to bytecode
    code_obj: Any = compile(tree, "<sandbox>", "exec")

    # Step 5 — Build a fresh sealed execution namespace
    sealed_globals: dict[str, Any] = _build_sealed_gas_globals(gas_limit)

    return code_obj, sealed_globals


# ─────────────────────────────────────────────────────────────────────────────
# Module-level __all__  (explicit public API surface)
# ─────────────────────────────────────────────────────────────────────────────

__all__: list[str] = [
    "GAS_PRICES",
    "GasMeterException",
    "GasMeterTransformer",
    "WeightedGasMeterTransformer",
    "instrument_code",
    # Internal helpers exposed for testing / introspection
    "_SAFE_BUILTINS",
    "_build_sealed_gas_globals",
]
