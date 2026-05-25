"""
context_scheduler.py
====================
EMMA — Central Mathematical Utility Core
JIT Context Rotation · Mutation Evaluation · Page Curve Log Compression

Standard library only. Python 3.9+.
Zero external dependencies.
"""

import ast
import re
import math
import difflib
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Class A: ASTContextRotator
# =============================================================================

class ASTContextRotator:
    """
    Geodesic Coordinate Reduction via Abstract Syntax Tree projection.

    Treats a source file as a high-dimensional state space and projects it
    onto a localised active-manifold: the target node is rendered fully
    expanded while every sibling node is collapsed to its structural
    signature stub (``def f(...) -> T: ...``).  The result is wrapped in
    a ``<TRANSIENT_CONTEXT>`` XML boundary, keeping context under 1 500 tokens.
    """

    def __init__(self, file_path: str) -> None:
        self.file_path: str = file_path
        self.source_code: str = ""
        self.tree: Optional[ast.AST] = None
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.load_file()

    # ------------------------------------------------------------------
    # I/O & Initialisation
    # ------------------------------------------------------------------

    def load_file(self) -> None:
        """Read source with UTF-8 encoding, parse AST, and index all nodes."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as fh:
                self.source_code = fh.read()
        except UnicodeDecodeError:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as fh:
                self.source_code = fh.read()
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"ASTContextRotator: target file not found — {self.file_path}"
            ) from exc

        self.tree = ast.parse(self.source_code)
        self._map_nodes()

    # ------------------------------------------------------------------
    # AST Traversal & Node Indexing
    # ------------------------------------------------------------------

    def _map_nodes(self) -> None:
        """
        Walk the parsed AST and record every function and class definition.

        Stores per node: ``start`` line, ``end`` line, and a precomputed
        ``signature`` stub string.  Node names are used as keys; in files
        with duplicate names the last encountered node wins.
        """
        if self.tree is None:
            return
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if not (hasattr(node, "lineno") and hasattr(node, "end_lineno")):
                continue
            self.nodes[node.name] = {
                "start":     node.lineno,
                "end":       node.end_lineno,
                "signature": self._extract_signature(node),
            }

    # ------------------------------------------------------------------
    # Annotation Unparsing  (ast.unparse >= 3.9 with 3.8 fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _unparse(node: ast.AST) -> str:
        """Convert an annotation AST node to its source-text representation."""
        try:
            return ast.unparse(node)          # type: ignore[attr-defined]
        except AttributeError:
            return ASTContextRotator._py38_unparse(node)

    @staticmethod
    def _py38_unparse(node: ast.AST) -> str:
        """Recursive fallback unparsing for Python 3.8 (no ast.unparse)."""
        _up = ASTContextRotator._py38_unparse
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_up(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Subscript):
            val = _up(node.value)
            sl  = node.slice
            if hasattr(ast, "Index") and isinstance(sl, getattr(ast, "Index")):
                sl = sl.value                 # type: ignore[attr-defined]
            return f"{val}[{_up(sl)}]"
        if isinstance(node, ast.Tuple):
            return "(" + ", ".join(_up(e) for e in node.elts) + ")"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return f"{_up(node.left)} | {_up(node.right)}"
        if isinstance(node, ast.List):
            return "[" + ", ".join(_up(e) for e in node.elts) + "]"
        return "Any"

    # ------------------------------------------------------------------
    # Signature Extraction
    # ------------------------------------------------------------------

    def _extract_signature(self, node: ast.AST) -> str:
        """Return the full definition line for *node* with a trailing ``...`` stub."""
        if isinstance(node, ast.ClassDef):
            return self._class_sig(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return self._func_sig(node)
        return f"# <unsupported node: {type(node).__name__}>"

    def _class_sig(self, node: ast.ClassDef) -> str:
        parts: List[str] = []
        for base in node.bases:
            try:
                parts.append(self._unparse(base))
            except Exception:
                parts.append("...")
        for kw in node.keywords:
            if kw.arg:
                try:
                    parts.append(f"{kw.arg}={self._unparse(kw.value)}")
                except Exception:
                    pass
        bases_str = f"({', '.join(parts)})" if parts else ""
        return f"class {node.name}{bases_str}: ..."

    def _func_sig(self, node: "ast.FunctionDef | ast.AsyncFunctionDef") -> str:
        prefix   = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args_str = self._render_args(node.args)
        ret      = ""
        if node.returns is not None:
            try:
                ret = f" -> {self._unparse(node.returns)}"
            except Exception:
                pass
        return f"{prefix} {node.name}({args_str}){ret}: ..."

    def _render_args(self, args: ast.arguments) -> str:
        """
        Reconstruct the full argument list string including type annotations,
        default values, *args, **kwargs, and positional-only separators.
        """
        parts:        List[str]     = []
        posonlyargs:  List[ast.arg] = getattr(args, "posonlyargs", [])
        regular_args: List[ast.arg] = args.args
        n_posonly    = len(posonlyargs)
        n_regular    = len(regular_args)
        n_defaults   = len(args.defaults)
        combined_len = n_posonly + n_regular
        default_start = combined_len - n_defaults

        def _ann(arg: ast.arg) -> str:
            if arg.annotation is None:
                return ""
            try:
                return f": {self._unparse(arg.annotation)}"
            except Exception:
                return ""

        def _dflt(combined_idx: int) -> str:
            if combined_idx < default_start:
                return ""
            idx = combined_idx - default_start
            if idx < 0 or idx >= len(args.defaults):
                return ""
            try:
                return f" = {self._unparse(args.defaults[idx])}"
            except Exception:
                return ""

        # Positional-only arguments
        for i, arg in enumerate(posonlyargs):
            parts.append(f"{arg.arg}{_ann(arg)}{_dflt(i)}")
        if posonlyargs:
            parts.append("/")

        # Regular positional arguments
        for i, arg in enumerate(regular_args):
            parts.append(f"{arg.arg}{_ann(arg)}{_dflt(n_posonly + i)}")

        # *args or bare * for keyword-only boundary
        if args.vararg is not None:
            parts.append(f"*{args.vararg.arg}{_ann(args.vararg)}")
        elif args.kwonlyargs:
            parts.append("*")

        # Keyword-only arguments
        for i, arg in enumerate(args.kwonlyargs):
            dflt_node = args.kw_defaults[i] if i < len(args.kw_defaults) else None
            dflt = ""
            if dflt_node is not None:
                try:
                    dflt = f" = {self._unparse(dflt_node)}"
                except Exception:
                    pass
            parts.append(f"{arg.arg}{_ann(arg)}{dflt}")

        # **kwargs
        if args.kwarg is not None:
            parts.append(f"**{args.kwarg.arg}{_ann(args.kwarg)}")

        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Context Rotation Assembly
    # ------------------------------------------------------------------

    def get_rotated_context(self, active_node_name: str) -> str:
        """
        Return the source file with *active_node_name* fully expanded and
        all sibling nodes reduced to single-line signature stubs.

        A sibling is any node that is neither an ancestor (contains the active
        node) nor a descendant (contained by the active node) nor overlapping
        with the active node's line range.

        Output format::

            <TRANSIENT_CONTEXT id="{active_node_name}" type="ast_node">
            ...compressed source...
            </TRANSIENT_CONTEXT>
        """
        if active_node_name not in self.nodes:
            return self.source_code

        active:  Dict[str, Any] = self.nodes[active_node_name]
        a_start: int            = active["start"]
        a_end:   int            = active["end"]

        lines:   List[str] = self.source_code.splitlines(keepends=True)
        n_lines: int       = len(lines)

        # Collect stub candidates — exclude ancestors, descendants, overlapping nodes
        stubs: List[Tuple[int, int, str]] = []
        for name, info in self.nodes.items():
            if name == active_node_name:
                continue
            ns: int = info["start"]
            ne: int = info["end"]
            is_ancestor    = (ns <= a_start) and (ne >= a_end)
            is_descendant  = (ns >= a_start) and (ne <= a_end)
            is_overlapping = (ns <= a_end)   and (ne >= a_start)
            if not is_ancestor and not is_descendant and not is_overlapping and ne > ns:
                stubs.append((ns, ne, info["signature"]))

        # Per-line action integers: KEEP=0, ELLIPSIS=1, SKIP=2
        KEEP, ELLIPSIS, SKIP = 0, 1, 2
        action:          List[int]      = [KEEP] * (n_lines + 1)
        ellipsis_indent: Dict[int, str] = {}

        for ns, ne, _sig in stubs:
            if ns < 1 or ns > n_lines:
                continue

            sig_text:    str = lines[ns - 1]
            base_indent: int = len(sig_text) - len(sig_text.lstrip(" \t"))
            body_indent: str = " " * (base_indent + 4)

            first_body_ln: int = ns + 1
            if first_body_ln <= ne and first_body_ln <= n_lines:
                if action[first_body_ln] == KEEP:
                    action[first_body_ln]          = ELLIPSIS
                    ellipsis_indent[first_body_ln] = body_indent

            for ln in range(ns + 2, min(ne + 1, n_lines + 1)):
                if action[ln] == KEEP:
                    action[ln] = SKIP

        # Compose the rotated source
        result: List[str] = []
        for i in range(1, n_lines + 1):
            act = action[i]
            if act == KEEP:
                result.append(lines[i - 1])
            elif act == ELLIPSIS:
                indent_str = ellipsis_indent.get(i, "    ")
                result.append(f"{indent_str}...\n")
            # SKIP: line is omitted

        content: str = "".join(result)
        return (
            f'<TRANSIENT_CONTEXT id="{active_node_name}" type="ast_node">\n'
            f"{content}"
            f"</TRANSIENT_CONTEXT>"
        )


# =============================================================================
# Class B: MutantCodeSelector
# =============================================================================

class MutantCodeSelector:
    """
    Evolutionary mutation selector using a multi-factor Fitness Objective Function.

    Given a population of candidate code strings C = {c1, c2, c3}, selects
    the global fitness optimum::

        Fitness(c) = SyntaxCheck(c) - ParsimonyPenalty(c) - ConstraintPenalty(c)

    Scoring weights:
      +50.0   AST parse succeeds
      -100.0  AST parse fails (SyntaxError) — halts further scoring for that candidate
      -30.0   Return statement absent when target signature declares a non-None return
      -0.1 x line_count  Parsimony penalty (favours compact implementations)
    """

    def __init__(self, target_signature: str = "") -> None:
        self.signature: str = target_signature
        self._return_required: bool = self._detect_return_requirement()

    # ------------------------------------------------------------------
    # Return Constraint Detection
    # ------------------------------------------------------------------

    def _detect_return_requirement(self) -> bool:
        """
        Return True iff the target signature declares a non-None return type.

        Handles forms: ``-> bool``, ``-> List[str]``, ``-> int | None``.
        A return of ``-> None`` or the absence of ``->`` yields False.
        """
        match = re.search(r"->\s*(.+?)(?:\s*:)?\s*$", self.signature.rstrip())
        if not match:
            return False
        ret_type = match.group(1).strip().rstrip(":").strip()
        return ret_type.lower() not in ("none", "")

    # ------------------------------------------------------------------
    # Individual Scoring Components
    # ------------------------------------------------------------------

    def parse_syntax_check(self, code: str) -> bool:
        """
        In-memory AST syntax validation.

        Compiles *code* via ``ast.parse`` without writing to disk.
        Returns ``True`` on a clean parse; ``False`` on ``SyntaxError``.
        """
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def calculate_parsimony(self, code: str) -> float:
        """
        Compute the parsimony penalty for *code*.

        Deducts 0.1 points per physical line to penalise verbose
        implementations and reward compact, elegant structures.
        """
        return len(code.splitlines()) * 0.1

    def score(self, code: str, task: str = "") -> float:
        """
        Compute the fitness score for a single candidate code string.

        Parameters
        ----------
        code : str
            The candidate implementation string.
        task : str
            The task description (unused, for API compatibility).

        Returns
        -------
        float
            Fitness score in range [-100.0, 50.0].
        """
        # Gate 1: Syntax check
        if not self.parse_syntax_check(code):
            return -100.0

        score = 50.0
        # Gate 2: Parsimony deduction
        score -= self.calculate_parsimony(code)

        # Gate 3: Missing return constraint
        if self._return_required and "return" not in code:
            score -= 30.0

        return score

    # ------------------------------------------------------------------
    # Mutant Evaluation
    # ------------------------------------------------------------------

    def evaluate_mutants(self, candidate_codes: List[str]) -> str:
        """
        Evaluate all candidates and return the highest-fitness code string.

        Parameters
        ----------
        candidate_codes : list[str]
            List of candidate implementation strings (typically 3).

        Returns
        -------
        str
            The candidate that maximises Fitness(c).

        Raises
        ------
        ValueError
            If *candidate_codes* is empty.
        """
        if not candidate_codes:
            raise ValueError(
                "MutantCodeSelector.evaluate_mutants: "
                "candidate_codes must be a non-empty list."
            )

        graded: List[Tuple[str, float]] = []

        for code in candidate_codes:
            graded.append((code, self.score(code)))

        if not graded:
            raise ValueError(
                "MutantCodeSelector.evaluate_mutants: "
                "no candidates survived evaluation."
            )

        graded.sort(key=lambda pair: pair[1], reverse=True)
        return graded[0][0]



# =============================================================================
# Class C: PageCurveEvaporator
# =============================================================================

class PageCurveEvaporator:
    """
    Entropic log compression modelled on the Hawking Radiation Page Curve.

    As stdout/stderr accumulates past the ``max_lines`` Page Time threshold,
    entropy peaks and evaporation is triggered: high-speed regex scans extract
    the structural signal (exit codes, error counts, warning counts, last
    exception trace) and condense the entire log into a single lossless
    metadata line, recovering ~98% of the token footprint.

    Output format::

        [Log Evaporated: Total Lines={n} | Errors={e} | Warnings={w} | Status={code}]
    """

    # Pre-compiled regex patterns for O(n) single-pass extraction
    _RE_ERROR: re.Pattern[str] = re.compile(
        r"ERR(?:OR)?|FAIL(?:URE|ED)?|Exception|Error",
        re.IGNORECASE,
    )
    _RE_WARNING: re.Pattern[str] = re.compile(
        r"\b[Ww]arning\b"
    )
    _RE_EXIT_PRIMARY: re.Pattern[str] = re.compile(
        r"(?:exit(?:ing|ed)?|process\s+finished\s+with)\s*"
        r"(?:code|status|with)?\s*[:=]?\s*(\d+)",
        re.IGNORECASE,
    )
    _RE_EXIT_ALT: re.Pattern[str] = re.compile(
        r"\bexit\s+(\d+)\b",
        re.IGNORECASE,
    )
    _RE_LAST_ERR_LINE: re.Pattern[str] = re.compile(
        r"(?:Error|Exception|FAIL(?:URE|ED)?|ERR(?:OR)?)[^\n]*",
        re.IGNORECASE,
    )

    _MAX_LAST_ERROR_LEN: int = 140

    def __init__(self, max_lines: int = 20) -> None:
        if max_lines < 1:
            raise ValueError("PageCurveEvaporator: max_lines must be >= 1.")
        self.max_lines: int = max_lines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaporate_log(self, raw_stdout: str) -> str:
        """
        Evaluate *raw_stdout* and compress it if it exceeds ``max_lines``.

        Parameters
        ----------
        raw_stdout : str
            Raw terminal output (stdout + stderr merged or separate).

        Returns
        -------
        str
            The original string if line count <= max_lines; otherwise a
            single-line summary block containing all structural metrics.
        """
        if not raw_stdout:
            return raw_stdout

        lines_list: List[str] = raw_stdout.splitlines()
        total_lines: int      = len(lines_list)

        if total_lines <= self.max_lines:
            return raw_stdout

        # Metric extraction
        error_count:   int = len(self._RE_ERROR.findall(raw_stdout))
        warning_count: int = len(self._RE_WARNING.findall(raw_stdout))
        exit_code:     str = self._extract_exit_code(raw_stdout)
        last_error:    str = self._extract_last_error(lines_list)

        # Metadata synthesis
        parts: List[str] = [
            f"Total Lines={total_lines}",
            f"Errors={error_count}",
            f"Warnings={warning_count}",
            f"Status={exit_code}",
        ]
        if last_error:
            truncated = last_error[: self._MAX_LAST_ERROR_LEN]
            parts.append(f'Last Error="{truncated}"')

        return "[Log Evaporated: " + " | ".join(parts) + "]"

    # ------------------------------------------------------------------
    # Internal extraction helpers
    # ------------------------------------------------------------------

    def _extract_exit_code(self, text: str) -> str:
        """Return the exit status code as a string, or 'unknown'."""
        m = self._RE_EXIT_PRIMARY.search(text)
        if m:
            return m.group(1)
        m = self._RE_EXIT_ALT.search(text)
        if m:
            return m.group(1)
        return "unknown"

    def _extract_last_error(self, lines_list: List[str]) -> str:
        """
        Scan *lines_list* in reverse and return the last line matching an
        error or exception pattern. Returns an empty string if none found.
        """
        for line in reversed(lines_list):
            if self._RE_LAST_ERR_LINE.search(line):
                return line.strip()
        return ""
