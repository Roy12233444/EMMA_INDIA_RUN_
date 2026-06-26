# backend/app/core/critic.py
"""
EMMA Cognitive Core — EMM-02-A3: CodeCritic Module
====================================================
Stateless AST Diff Reviewer · Surgical Patcher · STAI Calculator ·
Error Frequency Diagnostic Monitor

This module is the sole arbiter of structural code quality within the EMMA
Metacognitive Loop. It enforces four invariants on every candidate mutant
before it may be committed to the filesystem:

    1. Structural correctness  — AST-level diff analysis (not string comparison).
    2. Surgical precision      — JIT line-range splice replacing only the target node.
    3. Structural integrity    — STAI / STAI-DW scalar gate post-splice.
    4. Regression detection    — Error-log frequency monitor breaking looping states.

Zero-dependency constraint: only Python standard library modules are used.
All public methods are pure and stateless, guaranteeing safe concurrent
invocation across async executor coroutines without any locking.

Design authority: EMM-02-A3 Implementation Plan v2.0
"""

from __future__ import annotations

import ast
import difflib
import os
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# AST Utilities Import
# ---------------------------------------------------------------------------
from app.core.ast_utils import (
    ASTNormalizer,
    get_top_level_structures,
    count_all_ast_nodes,
)


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

#: Default STAI acceptance threshold below which the orchestrator commit gate
#: fires and the pending filesystem write is aborted.  Override via the
#: ``EMMA_STAI_THRESHOLD`` environment variable for stricter deployments
#: (e.g. public API surface files should use 0.95 or 1.0).
STAI_COMMIT_THRESHOLD: float = float(
    os.environ.get("EMMA_STAI_THRESHOLD", "0.85")
)

#: Number of consecutive identical error signatures that constitute an active
#: infinite regression loop.
ERROR_LOOP_THRESHOLD: int = int(
    os.environ.get("EMMA_ERROR_LOOP_THRESHOLD", "3")
)

#: Minimum number of top-level structural nodes required to use the standard
#: STAI calculation.  Files with fewer nodes automatically route to STAI-DW.
STAI_DW_ROUTING_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# CodeCritic
# ---------------------------------------------------------------------------


class CodeCritic:
    """
    Stateless AST-level structural diff reviewer, surgical patcher,
    STAI integrity calculator, and diagnostic error frequency monitor.

    **Concurrency guarantee:** All methods are pure and stateless — no
    instance attribute is ever mutated after ``__init__``.  The class is
    therefore safe to share across coroutines and threads without locking.

    **Zero-dependency guarantee:** Only Python standard-library modules
    (``ast``, ``difflib``, ``os``, ``typing``) are used.

    Typical orchestrator call sequence
    -----------------------------------
    ::

        critic = CodeCritic()

        # 1. Understand what changed structurally.
        diff = critic.compare_ast(original_code, mutant_code)

        # 2. For each modified node, surgically splice it.
        for node_key in diff["modified"]:
            spliced = critic.splice_node(original_code, mutant_code, node_key)

            # 3. Gate on STAI before writing to disk.
            report = critic.calculate_stai(original_code, spliced)
            if report["stai"] >= STAI_COMMIT_THRESHOLD:
                atomic_commit(spliced, target_path)
            else:
                error_history.extend(report["drift_details"])

        # 4. Detect regression loops.
        loop_report = critic.analyze_errors(error_history)
        if loop_report["looping_detected"]:
            llm_system_prompt += loop_report["critique"]
    """

    def __init__(self) -> None:  # noqa: D107
        # No instance state — intentional.
        pass

    # ------------------------------------------------------------------
    # 1. AST Structural Comparison Engine
    # ------------------------------------------------------------------

    def compare_ast(
        self,
        original_code: str,
        mutant_code: str,
    ) -> Dict[str, Any]:
        """
        Compare *original_code* and *mutant_code* at the AST structural level
        and classify every top-level node into one of three change categories.

        Parameters
        ----------
        original_code:
            The current contents of the target source file.
        mutant_code:
            The LLM-generated candidate patch.

        Returns
        -------
        dict with three keys:

        ``"added"``
            List of node keys present in *mutant_code* but absent from
            *original_code*.
        ``"deleted"``
            List of node keys present in *original_code* but absent from
            *mutant_code*.
        ``"modified"``
            List of node keys present in **both** but whose normalized AST
            fingerprints differ (i.e. structural logic has changed).

        Node keys follow the ``"<kind>:<name>"`` convention — for example
        ``"def:process_batch"`` or ``"class:DataPipeline"`` — which prevents
        silent collisions between a function and a class sharing an identifier.

        Raises
        ------
        ValueError
            If either source string fails ``ast.parse`` (propagated from
            ``get_top_level_structures``).

        Notes
        -----
        Whitespace, comment, and docstring changes do **not** alter the
        normalized AST fingerprint and will therefore **not** appear as
        ``"modified"`` entries.  This is the structural immunity guarantee.
        """
        orig_structs: Dict[str, ast.AST] = get_top_level_structures(original_code)
        mut_structs: Dict[str, ast.AST]  = get_top_level_structures(mutant_code)

        comparison: Dict[str, List[str]] = {
            "added":    [],
            "deleted":  [],
            "modified": [],
        }

        all_keys = set(orig_structs.keys()) | set(mut_structs.keys())

        for key in sorted(all_keys):  # sorted for deterministic output ordering
            in_orig = key in orig_structs
            in_mut  = key in mut_structs

            if in_mut and not in_orig:
                comparison["added"].append(key)
            elif in_orig and not in_mut:
                comparison["deleted"].append(key)
            else:
                # Both exist — compare normalized structural fingerprints.
                orig_fingerprint = ASTNormalizer.normalize(orig_structs[key])
                mut_fingerprint  = ASTNormalizer.normalize(mut_structs[key])
                if orig_fingerprint != mut_fingerprint:
                    comparison["modified"].append(key)
                # If fingerprints are equal the node is structurally unchanged;
                # it does not appear in any category (implicit "unchanged" set).

        return comparison

    # ------------------------------------------------------------------
    # 2. Unified Diff Generator
    # ------------------------------------------------------------------

    def generate_unified_diff(
        self,
        original_code: str,
        mutant_code: str,
        filename: str = "target.py",
    ) -> str:
        """
        Produce a minimal unified diff patch representing the line-level delta
        between *original_code* and *mutant_code*.

        Parameters
        ----------
        original_code:
            The current file contents (the "a" side of the diff).
        mutant_code:
            The proposed mutant (the "b" side of the diff).
        filename:
            Logical filename embedded in the patch header lines
            (``--- a/<filename>`` / ``+++ b/<filename>``).
            Defaults to ``"target.py"``.

        Returns
        -------
        str
            A unified diff string suitable for display in CI logs, storage in
            audit trails, or direct application via ``patch(1)``.  Returns an
            empty string when the two inputs are identical.

        Notes
        -----
        This method performs a **line-level** diff only.  For structural
        analysis use :meth:`compare_ast`; for surgical application use
        :meth:`splice_node`.
        """
        orig_lines: List[str] = original_code.splitlines(keepends=True)
        mut_lines:  List[str] = mutant_code.splitlines(keepends=True)

        diff_generator = difflib.unified_diff(
            orig_lines,
            mut_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
        return "".join(diff_generator)

    # ------------------------------------------------------------------
    # 3. JIT AST Node Splicer
    # ------------------------------------------------------------------

    def splice_node(
        self,
        original_code: str,
        mutant_code: str,
        target_node_name: str,
    ) -> str:
        """
        Surgically replace the source lines of *target_node_name* in
        *original_code* with the corresponding implementation from
        *mutant_code*, leaving every other line in the original file
        completely intact.

        The splice is performed using AST-defined line boundaries
        (``node.lineno`` → ``node.end_lineno``), which are 1-indexed per the
        CPython AST spec and converted internally to 0-indexed Python slices.

        Parameters
        ----------
        original_code:
            Full source of the file currently on disk.
        mutant_code:
            Full source of the LLM-proposed patch (must contain the target
            node).
        target_node_name:
            A ``"<kind>:<name>"`` key as returned by
            :meth:`compare_ast` — e.g. ``"def:train_model"`` or
            ``"class:Pipeline"``.

        Returns
        -------
        str
            The post-splice source string.  This value must be passed to
            :meth:`calculate_stai` before being committed to disk.

        Raises
        ------
        ValueError
            If *target_node_name* is absent from either *original_code* or
            *mutant_code*, or if either source fails ``ast.parse``.

        Notes
        -----
        **Edge cases handled:**

        * **Single-line nodes:** When ``end_lineno`` equals ``lineno`` (a
          one-liner function or class), the slice ``[start:start+1]`` still
          produces a valid single-element list.
        * **Missing ``end_lineno``:** Python 3.7 does not populate
          ``end_lineno``; the fallback ``getattr(node, "end_lineno",
          node.lineno)`` safely degrades to a single-line replacement.
        * **Trailing newline preservation:** The result is joined with
          ``"\\n"``; a trailing newline is appended only when the original
          source ended with one, preserving the file's newline contract.
        """
        orig_structs: Dict[str, ast.AST] = get_top_level_structures(original_code)
        mut_structs:  Dict[str, ast.AST] = get_top_level_structures(mutant_code)

        if target_node_name not in orig_structs:
            raise ValueError(
                f"Target node '{target_node_name}' not found in original_code. "
                "Cannot splice a node that does not exist in the original file."
            )
        if target_node_name not in mut_structs:
            raise ValueError(
                f"Target node '{target_node_name}' not found in mutant_code. "
                "Cannot splice a node that the mutant does not provide."
            )

        orig_node: ast.AST = orig_structs[target_node_name]
        mut_node:  ast.AST = mut_structs[target_node_name]

        orig_lines: List[str] = original_code.splitlines()
        mut_lines:  List[str] = mutant_code.splitlines()

        # ── Convert 1-indexed AST positions to 0-indexed Python slices ──
        #
        # AST node.lineno     → first line of the definition (1-indexed)
        # AST node.end_lineno → last line of the definition  (1-indexed, inclusive)
        #
        # Python slice [start:end] is 0-indexed and end-exclusive, so:
        #   start = lineno - 1
        #   end   = end_lineno          (already acts as exclusive upper bound
        #                                after the -1 + 1 cancellation)

        mut_start: int = mut_node.lineno - 1
        mut_end:   int = getattr(mut_node, "end_lineno", mut_node.lineno)
        # mut_lines[mut_start:mut_end] captures lines mut_start..mut_end-1
        # which corresponds to AST lines mut_node.lineno..mut_node.end_lineno ✓

        orig_start: int = orig_node.lineno - 1
        orig_end:   int = getattr(orig_node, "end_lineno", orig_node.lineno)

        mutant_slice: List[str] = mut_lines[mut_start:mut_end]

        spliced_lines: List[str] = (
            orig_lines[:orig_start]
            + mutant_slice
            + orig_lines[orig_end:]
        )

        result = "\n".join(spliced_lines)

        # Preserve trailing newline if the original source had one.
        if original_code.endswith("\n") and not result.endswith("\n"):
            result += "\n"

        return result

    # ------------------------------------------------------------------
    # 4. STAI / STAI-DW Calculator
    # ------------------------------------------------------------------

    def calculate_stai(
        self,
        original_code: str,
        spliced_code: str,
    ) -> Dict[str, Any]:
        """
        Compute the **Syntax-Tree Alignment Index (STAI)** for a post-splice
        result and return a structured integrity report.

        The STAI quantifies the fraction of the original module's top-level
        structural nodes that are **identically preserved** in the spliced
        result:

        .. code-block:: text

            STAI = |N_identical| / |N_original|

        Where:

        * ``N_original`` — set of top-level AST nodes (``FunctionDef``,
          ``AsyncFunctionDef``, ``ClassDef``) in *original_code*, keyed by
          ``"<kind>:<name>"``.
        * ``N_identical`` ⊆ ``N_original`` — subset whose normalized AST
          fingerprints are **exactly equal** in the spliced result.

        **Routing rule (STAI vs STAI-DW):**

        When ``|N_original| < STAI_DW_ROUTING_THRESHOLD`` (default 3), the
        top-level node count provides insufficient resolution for meaningful
        comparison.  In that case the method automatically routes to the
        **Deep-Walk variant (STAI-DW)** which traverses the entire AST tree
        via ``ast.walk`` and computes node-level parity at sub-function
        granularity.

        Parameters
        ----------
        original_code:
            Full source of the file as it existed *before* splicing.
        spliced_code:
            Full source of the file *after* :meth:`splice_node` has been
            applied.

        Returns
        -------
        dict conforming to the STAI Report Schema (Section 6.4):

        ``"stai"``       — float in [0.0, 1.0], rounded to 6 decimal places.
        ``"identical_nodes"``       — int, ``|N_identical|``.
        ``"total_original_nodes"``  — int, ``|N_original|``.
        ``"drift_detected"``        — bool, ``True`` when STAI < 1.0.
        ``"drift_details"``         — list of per-node drift description strings.
        ``"verdict"``               — ``"PASS"`` or ``"FAIL — structural drift exceeds tolerance"``.
        ``"variant"``               — ``"STAI"`` or ``"STAI-DW"`` indicating which
                                      calculation path was taken.

        Raises
        ------
        ValueError
            If either source string fails ``ast.parse``.

        Notes
        -----
        **Edge case — empty original:** When ``|N_original| = 0`` (module
        contains only expressions or imports, no functions/classes) the STAI
        is defined as ``1.0`` and ``drift_detected`` is ``False`` to prevent
        division-by-zero and to reflect that no structural identity exists to
        violate.
        """
        orig_structs: Dict[str, ast.AST] = get_top_level_structures(original_code)
        total_original: int = len(orig_structs)

        # ── Edge case: no top-level structures in original ──────────────────
        if total_original == 0:
            return {
                "stai":                 1.0,
                "identical_nodes":      0,
                "total_original_nodes": 0,
                "drift_detected":       False,
                "drift_details":        [],
                "verdict":              "PASS — original source contained no top-level structures.",
                "variant":              "STAI",
            }

        # ── Routing: STAI vs STAI-DW ────────────────────────────────────────
        if total_original < STAI_DW_ROUTING_THRESHOLD:
            return self._calculate_stai_dw(
                original_code=original_code,
                spliced_code=spliced_code,
            )

        # ── Standard STAI ───────────────────────────────────────────────────
        spliced_structs: Dict[str, ast.AST] = get_top_level_structures(spliced_code)

        identical_count: int     = 0
        drift_details:   List[str] = []

        for key, orig_node in orig_structs.items():
            if key not in spliced_structs:
                drift_details.append(
                    f"MISSING: '{key}' was deleted from the spliced result."
                )
                continue

            orig_fp    = ASTNormalizer.normalize(orig_node)
            spliced_fp = ASTNormalizer.normalize(spliced_structs[key])

            if orig_fp == spliced_fp:
                identical_count += 1
            else:
                drift_details.append(
                    f"MODIFIED: '{key}' structural fingerprint diverged post-splice."
                )

        stai_score: float = identical_count / total_original
        drift_flag: bool  = stai_score < 1.0
        verdict: str = (
            "PASS"
            if stai_score >= STAI_COMMIT_THRESHOLD
            else "FAIL — structural drift exceeds tolerance"
        )

        return {
            "stai":                 round(stai_score, 6),
            "identical_nodes":      identical_count,
            "total_original_nodes": total_original,
            "drift_detected":       drift_flag,
            "drift_details":        drift_details,
            "verdict":              verdict,
            "variant":              "STAI",
        }

    def _calculate_stai_dw(
        self,
        original_code: str,
        spliced_code: str,
    ) -> Dict[str, Any]:
        """
        Deep-Walk variant of STAI (STAI-DW) for sparse modules.

        Instead of comparing only top-level nodes, this variant walks the
        **entire** AST tree of both source versions via ``ast.walk`` and
        computes the fraction of total nodes — including sub-expressions,
        arguments, return statements, and binary operators — that are
        structurally preserved.

        .. code-block:: text

            STAI-DW = |W_identical| / |W_original|

        Where ``W`` is the multiset of all nodes produced by
        ``ast.walk(ast.parse(code))``, normalized individually via
        ``ASTNormalizer.normalize``.

        This method is called automatically by :meth:`calculate_stai` when
        ``|N_original| < STAI_DW_ROUTING_THRESHOLD``.  It should not be
        invoked directly by the orchestrator.

        Parameters
        ----------
        original_code:
            Source as it existed before splicing.
        spliced_code:
            Source after splicing.

        Returns
        -------
        dict
            Same schema as :meth:`calculate_stai` with ``"variant"`` set to
            ``"STAI-DW"``.
        """
        # Build normalized fingerprint multisets via ast.walk.
        # We use a list (multiset) rather than a set so that duplicate
        # sub-node shapes (e.g. two identical ``Return`` nodes) are counted
        # individually — preserving correct cardinality.

        def _walk_fingerprints(code: str) -> List[str]:
            try:
                tree = ast.parse(code)
            except SyntaxError as exc:
                raise ValueError(f"AST parsing failed: {exc}") from exc
            return [ASTNormalizer.normalize(node) for node in ast.walk(tree)]

        orig_fps:    List[str] = _walk_fingerprints(original_code)
        spliced_fps: List[str] = _walk_fingerprints(spliced_code)

        total_original: int = len(orig_fps)

        if total_original == 0:
            return {
                "stai":                 1.0,
                "identical_nodes":      0,
                "total_original_nodes": 0,
                "drift_detected":       False,
                "drift_details":        [],
                "verdict":              "PASS — original source AST was empty.",
                "variant":              "STAI-DW",
            }

        # Count how many fingerprints from the original survive in the spliced
        # result.  We consume matches greedily from a mutable copy of
        # spliced_fps so that each spliced node is matched at most once.
        spliced_pool: List[str] = list(spliced_fps)
        identical_count: int = 0

        for fp in orig_fps:
            if fp in spliced_pool:
                identical_count += 1
                spliced_pool.remove(fp)  # consume the match

        stai_score: float = identical_count / total_original
        drift_flag: bool  = stai_score < 1.0

        # Drift details at DW level are high-level summaries only; per-node
        # attribution at walk depth is too verbose for the orchestrator log.
        drift_details: List[str] = []
        if drift_flag:
            lost = total_original - identical_count
            drift_details.append(
                f"STAI-DW: {lost} of {total_original} deep-walk AST nodes "
                "changed or were lost post-splice."
            )

        verdict: str = (
            "PASS"
            if stai_score >= STAI_COMMIT_THRESHOLD
            else "FAIL — structural drift exceeds tolerance"
        )

        return {
            "stai":                 round(stai_score, 6),
            "identical_nodes":      identical_count,
            "total_original_nodes": total_original,
            "drift_detected":       drift_flag,
            "drift_details":        drift_details,
            "verdict":              verdict,
            "variant":              "STAI-DW",
        }

    # ------------------------------------------------------------------
    # 5. Error Log Frequency Monitor
    # ------------------------------------------------------------------

    def analyze_errors(
        self,
        error_history: List[str],
        threshold: int = ERROR_LOOP_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        Inspect a chronological list of stderr / traceback strings and detect
        repeating error signatures that indicate an active infinite regression
        loop in the executor.

        The algorithm:

        1. For each entry in *error_history*, extract the **exception class
           name** from the final line of the traceback (the line that begins
           with ``ExceptionClass: message``).
        2. Examine the *threshold* most-recent signatures.  If they are all
           identical (and non-empty), a regression loop is declared.
        3. Map the repeating exception class to a targeted natural-language
           remedy string and compose a structured critique prompt ready for
           injection into the LLM's system prompt.

        Parameters
        ----------
        error_history:
            Chronologically ordered list of raw stderr / traceback strings,
            oldest first.  Each element may be a single-line error message or
            a full multi-line Python traceback.
        threshold:
            Minimum number of *consecutive* identical signatures required to
            declare a loop.  Defaults to ``ERROR_LOOP_THRESHOLD`` (3), which
            is configurable via the ``EMMA_ERROR_LOOP_THRESHOLD`` environment
            variable.

        Returns
        -------
        dict with three keys:

        ``"looping_detected"``
            ``bool`` — ``True`` when the last *threshold* entries share the
            same exception class name.
        ``"frequent_error"``
            ``str | None`` — The repeating exception class name, or ``None``
            when no loop is detected.
        ``"critique"``
            ``str`` — A structured, actionable critique prompt fragment.
            Empty string when no loop is detected.

        Notes
        -----
        * An empty *error_history* returns safe defaults without raising.
        * Entries that produce an empty signature string (blank or unparseable
          traceback) are skipped and **do not** count toward loop detection,
          preventing false positives from noise entries.
        * The returned ``"critique"`` string is prefixed with ``"[CRITIQUE]"``
          so the orchestrator can reliably detect and append it to the LLM
          system prompt with a simple ``str.startswith`` check.
        """
        if not error_history:
            return {
                "looping_detected": False,
                "frequent_error":   None,
                "critique":         "",
            }

        # ── Extract exception class names ────────────────────────────────────
        signatures: List[str] = []
        for entry in error_history:
            sig = self._extract_exception_signature(entry)
            if sig:  # skip empty / unparseable entries
                signatures.append(sig)

        if not signatures:
            return {
                "looping_detected": False,
                "frequent_error":   None,
                "critique":         "",
            }

        # ── Detect sequential repetition in the most-recent `threshold` items ─
        looping:       bool          = False
        frequent_sig:  Optional[str] = None

        if len(signatures) >= threshold:
            recent_window: List[str] = signatures[-threshold:]
            unique_in_window = set(recent_window)
            if len(unique_in_window) == 1:
                looping      = True
                frequent_sig = recent_window[0]

        # ── Compose structured critique ──────────────────────────────────────
        critique: str = ""
        if frequent_sig:
            hint: str = self._get_exception_hint(frequent_sig)
            critique = (
                f"[CRITIQUE] Critical regression pattern found: "
                f"'{frequent_sig}' occurred {threshold} times consecutively. "
                f"Action item: {hint}"
            )

        return {
            "looping_detected": looping,
            "frequent_error":   frequent_sig,
            "critique":         critique,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_exception_signature(traceback_entry: str) -> str:
        """
        Extract the exception class name from a raw traceback or error string.

        Strategy: the final non-empty line of a Python traceback always has
        the form ``ExceptionClass: message``.  We take the last non-blank
        line and split on the first ``":"`` to isolate the class name.

        Parameters
        ----------
        traceback_entry:
            A single stderr / traceback string, possibly multi-line.

        Returns
        -------
        str
            The exception class name (e.g. ``"TypeError"``), or an empty
            string if the entry is blank or does not match the expected format.
        """
        stripped = traceback_entry.strip()
        if not stripped:
            return ""

        # Use the last non-empty line — the most informative line in a
        # Python traceback is always the final one.
        lines = [ln for ln in stripped.splitlines() if ln.strip()]
        if not lines:
            return ""

        last_line = lines[-1].strip()

        if ":" in last_line:
            candidate = last_line.split(":")[0].strip()
            # Sanity check: exception class names are valid Python identifiers
            # and start with a capital letter.  This guards against false
            # matches on lines like "File: path/to/script.py".
            if candidate.isidentifier() and candidate[0].isupper():
                return candidate

        # Fallback: if no colon is present, treat the entire last line as the
        # signature (handles bare ``AssertionError`` with no message).
        if last_line.isidentifier() and last_line[0].isupper():
            return last_line

        return ""

    @staticmethod
    def _get_exception_hint(exception_name: str) -> str:
        """
        Map an exception class name to a targeted, actionable natural-language
        remedy string for LLM self-correction.

        Parameters
        ----------
        exception_name:
            The repeating exception class name as extracted by
            :meth:`_extract_exception_signature`.

        Returns
        -------
        str
            A concise, imperative instruction directing the LLM toward a
            concrete fix.  Falls back to a generic remediation guide for
            unrecognised exception types.
        """
        hints: Dict[str, str] = {
            "TypeError": (
                "Ensure that every function call provides arguments that match "
                "the declared type signature exactly. Verify variable unpacking "
                "tuples match the expected element count and that no ``None`` "
                "values are passed to operations that require concrete types."
            ),
            "IndexError": (
                "Guard every list, tuple, and sequence access with explicit "
                "bounds checking (``if index < len(seq)``). Prefer safe slice "
                "notation and avoid assumptions about collection length when "
                "operating on LLM-generated or user-supplied data."
            ),
            "AttributeError": (
                "Confirm that every attribute access targets an object that is "
                "fully initialised and of the expected type. Check for typos in "
                "attribute names and verify that all required ``__init__`` "
                "assignments are present before the first attribute read."
            ),
            "KeyError": (
                "Replace all bare ``dict[key]`` accesses with "
                "``dict.get(key, default)`` or an explicit ``if key in dict`` "
                "guard. Audit all dictionary literals and dynamic key "
                "construction to ensure the key is populated before retrieval."
            ),
            "SyntaxError": (
                "Carefully inspect the generated code for: missing colons after "
                "``if``/``for``/``def``/``class`` statements, unclosed "
                "parentheses or brackets, incorrect indentation (mixed tabs "
                "and spaces), and invalid f-string expressions."
            ),
            "ModuleNotFoundError": (
                "Verify that the imported module name is spelled correctly and "
                "that the package is listed in the project's dependency manifest "
                "(``pyproject.toml`` or ``requirements.txt``). Confirm the "
                "virtual environment is activated and the package is installed."
            ),
            "ImportError": (
                "Check that the specific symbol being imported exists in the "
                "target module at the expected path. Confirm there are no "
                "circular imports and that ``__init__.py`` files expose the "
                "required names."
            ),
            "RecursionError": (
                "Introduce an explicit base-case guard or a depth counter "
                "(``if depth >= MAX_DEPTH: return``). Consider refactoring "
                "the recursive descent into an iterative loop with an explicit "
                "stack to eliminate the recursion limit entirely."
            ),
            "ValueError": (
                "Validate all input arguments against their expected domains "
                "before processing (e.g. non-empty strings, positive integers, "
                "non-null objects). Raise ``ValueError`` with a descriptive "
                "message at the entry point rather than allowing it to propagate "
                "from deep within the call chain."
            ),
            "RuntimeError": (
                "Inspect the runtime state at the point of failure — this "
                "exception typically signals a logic invariant violation. Add "
                "assertion guards at critical state transitions and confirm "
                "that coroutine lifecycle (``async``/``await``) is respected."
            ),
            "NameError": (
                "Ensure all variables are defined before use. Check for typos "
                "in variable names and confirm that variables defined inside "
                "conditional blocks are initialised on all code paths before "
                "the first read."
            ),
            "NotImplementedError": (
                "Provide a concrete implementation for the abstract method or "
                "stub that raised this exception. The orchestrator should not "
                "invoke placeholder methods; verify the correct concrete "
                "subclass is being instantiated."
            ),
            "AssertionError": (
                "An ``assert`` statement evaluated to ``False``. Inspect the "
                "assertion condition and the actual runtime values — add "
                "diagnostic logging before the assertion to capture the "
                "offending state for analysis."
            ),
            "StopIteration": (
                "A generator or iterator was exhausted unexpectedly. Wrap "
                "``next()`` calls in a try/except or use the two-argument form "
                "``next(iterator, default)`` to provide a safe sentinel value "
                "instead of propagating the exception."
            ),
            "OSError": (
                "A filesystem or I/O operation failed. Verify that the target "
                "path exists and the process has the required read/write "
                "permissions. Wrap file operations in try/except and provide "
                "clear error messages that include the offending path."
            ),
            "OverflowError": (
                "An arithmetic result exceeded the representable range for its "
                "numeric type. Introduce explicit range checks before the "
                "computation and consider using Python's arbitrary-precision "
                "``int`` or the ``decimal`` module for high-magnitude values."
            ),
            "ZeroDivisionError": (
                "A division or modulo operation has a zero denominator. Add an "
                "explicit ``if denominator == 0`` guard before every division "
                "and decide on the correct semantic for the degenerate case "
                "(return 0, raise a domain-specific error, or use ``math.inf``)."
            ),
        }

        return hints.get(
            exception_name,
            (
                "Isolate the regression point by adding targeted ``assert`` "
                "statements and logging at each stage of the pipeline. "
                "Validate all inputs against their declared types, confirm "
                "all referenced names are in scope, and review the most "
                "recent structural change for unintended side-effects."
            ),
        )
