# backend/app/utils/ast_utils.py
"""
EMMA Cognitive Core — AST Utility Layer
========================================
EMM-02-A4: Zero-Dependency Structural AST Extraction & Normalization

This module provides the three foundational utilities consumed by
``backend/app/core/critic_v2.py``:

    ASTNormalizer               — Structural fingerprinting of AST nodes.
    get_top_level_structures    — Top-level function/class extraction.
    count_all_ast_nodes         — Full deep-walk node counter.

Zero-dependency constraint: only Python standard library modules are used.
All public interfaces are 100% API-compatible with the inline stubs that
were previously defined directly inside ``critic_v2.py``.

Design authority: EMM-02-A3 Implementation Plan v2.0, Section 3.2
"""

from __future__ import annotations

import ast
from typing import Dict


# ---------------------------------------------------------------------------
# ASTNormalizer
# ---------------------------------------------------------------------------


class ASTNormalizer:
    """
    Serialize an AST node into a normalized structural string representation
    that is completely immune to formatting differences, comments, docstrings,
    line numbers, and column offsets.

    Two AST nodes are considered **structurally equivalent** if and only if
    their normalized strings are identical.  This invariant is the foundation
    of the structural immunity guarantee: pure whitespace or comment edits will
    never produce a different fingerprint and will therefore never be surfaced
    as a ``"modified"`` entry in ``CodeCritic.compare_ast``.

    Implementation note
    -------------------
    ``ast.dump`` with ``annotate_fields=False`` and
    ``include_attributes=False`` suppresses:

    * All field names (leaving only node-type and child structure).
    * All source-location attributes (``lineno``, ``col_offset``,
      ``end_lineno``, ``end_col_offset``).

    This produces the most compact, position-independent representation
    available from the standard library without any third-party dependency.
    The behavior is stable across CPython 3.8 through 3.12+.
    """

    @classmethod
    def normalize(cls, node: ast.AST) -> str:
        """
        Return the canonical structural fingerprint string for *node*.

        Parameters
        ----------
        node:
            Any ``ast.AST`` instance — typically a ``FunctionDef``,
            ``AsyncFunctionDef``, or ``ClassDef`` node retrieved from
            ``get_top_level_structures``, but any AST node is accepted.

        Returns
        -------
        str
            A deterministic, position-free structural dump of the node tree.
            Two nodes are structurally equivalent iff their fingerprints are
            equal under strict string equality (``==``).

        Examples
        --------
        >>> import ast
        >>> src_a = "def f(x):\\n    return x + 1"
        >>> src_b = "def f(x):\\n\\n    # comment\\n    return x + 1"
        >>> tree_a = ast.parse(src_a).body[0]
        >>> tree_b = ast.parse(src_b).body[0]
        >>> ASTNormalizer.normalize(tree_a) == ASTNormalizer.normalize(tree_b)
        True
        """
        return ast.dump(node, annotate_fields=False, include_attributes=False)


# ---------------------------------------------------------------------------
# get_top_level_structures
# ---------------------------------------------------------------------------


def get_top_level_structures(code: str) -> Dict[str, ast.AST]:
    """
    Parse Python *code* and return all top-level ``FunctionDef``,
    ``AsyncFunctionDef``, and ``ClassDef`` nodes, keyed by a
    ``"<kind>:<name>"`` string.

    Key format
    ----------
    * Functions and coroutines → ``"def:<name>"``
      e.g. ``"def:train_model"``, ``"def:_internal_helper"``
    * Classes → ``"class:<name>"``
      e.g. ``"class:DataPipeline"``, ``"class:_PrivateBase"``

    This namespacing convention prevents silent key collisions between a
    function and a class that share the same identifier (a valid, if unusual,
    Python pattern).

    Parameters
    ----------
    code:
        Raw Python source string to parse.  May be a complete module, a
        single-function snippet, or any syntactically valid Python source.

    Returns
    -------
    Dict[str, ast.AST]
        Ordered mapping (insertion order preserved, Python 3.7+) of
        ``"<kind>:<name>"`` → AST node.  The AST nodes retain their
        original ``lineno`` and ``end_lineno`` attributes so that
        ``CodeCritic.splice_node`` can compute exact 0-indexed line slices.

    Raises
    ------
    ValueError
        Wraps any ``SyntaxError`` raised by ``ast.parse`` with a descriptive
        message.  This ensures callers receive a clean, typed exception rather
        than a raw parser traceback leaking into the orchestrator log.

    Notes
    -----
    Only **top-level** nodes (direct children of the module body) are
    extracted.  Nested functions and inner classes are intentionally excluded
    because the JIT splicer operates at module-level granularity.

    Examples
    --------
    >>> structs = get_top_level_structures("def foo(): pass\\nclass Bar: pass")
    >>> list(structs.keys())
    ['def:foo', 'class:Bar']
    """
    try:
        tree: ast.Module = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(
            f"AST parsing failed — the source contains a syntax error: {exc}"
        ) from exc

    structures: Dict[str, ast.AST] = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = f"def:{node.name}"
            structures[key] = node
        elif isinstance(node, ast.ClassDef):
            key = f"class:{node.name}"
            structures[key] = node
        # Import, Assign, AnnAssign, Expr, and all other top-level statement
        # types are intentionally omitted — the Critic operates on callable
        # and class boundaries only, as specified in the v2 plan.

    return structures


# ---------------------------------------------------------------------------
# count_all_ast_nodes
# ---------------------------------------------------------------------------


def count_all_ast_nodes(code: str) -> int:
    """
    Return the total count of **every** AST node produced by a full
    ``ast.walk`` traversal of the parse tree for *code*.

    This includes all node types at every depth: ``Module``, ``FunctionDef``,
    ``arguments``, ``arg``, ``Return``, ``BinOp``, ``Name``, ``Constant``,
    ``Compare``, ``Call``, decorator nodes, and all others — providing
    sub-function structural resolution for the STAI-DW deep-walk variant.

    Parameters
    ----------
    code:
        Raw Python source string to parse and traverse.

    Returns
    -------
    int
        The exact total count of all nodes yielded by
        ``ast.walk(ast.parse(code))``.  Always ≥ 1 (the root ``Module``
        node is always present in a non-empty parse).

    Raises
    ------
    ValueError
        Wraps any ``SyntaxError`` raised by ``ast.parse`` with a descriptive
        message.

    Notes
    -----
    This function is the backing implementation for the deep-walk cardinality
    measurement in ``CodeCritic._calculate_stai_dw``.  It is exposed as a
    standalone utility so that external diagnostic tooling can query raw node
    counts without instantiating a ``CodeCritic``.

    Examples
    --------
    >>> count_all_ast_nodes("x = 1")
    4   # Module → Assign → Name + Constant
    >>> count_all_ast_nodes("")
    1   # Module node only
    """
    try:
        tree: ast.Module = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(
            f"AST parsing failed — the source contains a syntax error: {exc}"
        ) from exc

    return sum(1 for _ in ast.walk(tree))
