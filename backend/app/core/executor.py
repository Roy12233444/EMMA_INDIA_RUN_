"""
executor.py
===========
EMMA — Evolutionary Draft Coordinator

Constructs the live bridge between the EMMA Cognitive Core and a locally-hosted
LLM endpoint (Ollama / qwen2.5-coder). Orchestrates three parallel inference
requests at distinct temperatures and system prompts to generate structurally
diverse mutant code candidates, extracts clean Python from XML boundary tags,
and falls back to deterministic simulation mutants when the LLM service is
offline.

Standard library only. Python 3.9+. Zero external dependencies.
"""

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# System Prompt Constants — Evolutionary Diversification Engine
# =============================================================================

_SYSTEM_PROMPT_A: str = """\
You are an elite Python software engineer optimising for parsimony.
Your ONLY output is a single Python function or class wrapped inside
<CODE_PROPOSAL> ... </CODE_PROPOSAL> XML tags.

RULES:
- Use the fewest lines possible. Prefer list comprehensions, generator
  expressions, and single-expression returns over multi-step assignments.
- Never write docstrings longer than one line.
- Never define helper variables unless strictly required for clarity.
- The code block must be syntactically complete and self-contained.
- Output NOTHING outside the <CODE_PROPOSAL> tags. No explanation.
  No preamble. No markdown fences."""

_SYSTEM_PROMPT_B: str = """\
You are a senior Python architect who designs structurally diverse solutions.
Your ONLY output is a single Python function or class wrapped inside
<CODE_PROPOSAL> ... </CODE_PROPOSAL> XML tags.

RULES:
- Use a structurally different approach from the obvious solution.
  If a loop is typical, use a map/filter pipeline. If recursion is
  typical, use an iterative stack. If a dict is obvious, consider
  a named tuple or dataclass.
- You may define one private helper function inside the main function
  body if it improves structural clarity.
- Favour explicit, readable variable names over terse one-letter names.
- The code block must be syntactically complete and self-contained.
- Output NOTHING outside the <CODE_PROPOSAL> tags. No explanation.
  No preamble. No markdown fences."""

_SYSTEM_PROMPT_C: str = """\
You are a creative Python engineer who approaches problems through radical
modular decomposition. Your ONLY output is a single Python function or class
wrapped inside <CODE_PROPOSAL> ... </CODE_PROPOSAL> XML tags.

RULES:
- Decompose the problem into the smallest possible logical units.
  Use inner classes, closures, or factory patterns if they produce
  a more composable and testable interface.
- It is acceptable to be more verbose if it yields superior reusability.
- Use descriptive, expressive naming conventions throughout.
- The code block must be syntactically complete and self-contained.
- Output NOTHING outside the <CODE_PROPOSAL> tags. No explanation.
  No preamble. No markdown fences."""

# Temperature coefficients aligned with cognitive axis targets
_TEMPERATURES: Tuple[float, float, float] = (0.20, 0.70, 0.95)

# Human-readable labels for diagnostic output
_LABELS: Tuple[str, str, str] = ("A", "B", "C")

# System prompts in slot order: [A, B, C]
_SYSTEM_PROMPTS: Tuple[str, str, str] = (
    _SYSTEM_PROMPT_A,
    _SYSTEM_PROMPT_B,
    _SYSTEM_PROMPT_C,
)

# Maximum file context characters forwarded to the LLM user message
_MAX_CONTEXT_CHARS: int = 2_000


# =============================================================================
# Offline Fallback Simulation Mutants
# =============================================================================
# A and B are syntactically valid — they pass the MutantCodeSelector fitness
# gate with positive scores. C is intentionally invalid (missing colon) to
# exercise the -100.0 SyntaxError rejection path in the test suite.

def _FALLBACK_A(task: str, signature: str) -> str:
    """Simulation fallback for Mutant A — minimal valid implementation."""
    fn = _extract_sig_name(signature) or "generated_function"
    has_ret = "->" in signature and "-> None" not in signature
    ret_line = "    return result\n" if has_ret else ""
    return (
        f'def {fn}(*args, **kwargs):\n'
        f'    """[FALLBACK-A] {task[:60]}"""\n'
        f'    result = None\n'
        f'{ret_line}'
    )


def _FALLBACK_B(task: str, signature: str) -> str:
    """Simulation fallback for Mutant B — valid but verbose implementation."""
    fn = _extract_sig_name(signature) or "generated_function"
    has_ret = "->" in signature and "-> None" not in signature
    ret_line = "    return result\n" if has_ret else ""
    preview = task[:50].replace('"', "'")
    return (
        f'def {fn}(*args, **kwargs):\n'
        f'    """\n'
        f'    [FALLBACK-B] {task[:60]}\n'
        f'    Structural alternative simulation stub.\n'
        f'    """\n'
        f'    # Initialise result container\n'
        f'    result = None\n'
        f'    # Task context reference\n'
        f'    _task_label = "{preview}"\n'
        f'    _ = _task_label\n'
        f'{ret_line}'
    )


def _FALLBACK_C(task: str, signature: str) -> str:
    """
    Simulation fallback for Mutant C — deliberate SyntaxError (missing colon).

    This is intentional: Mutant C is the high-entropy wildcard.
    The -100.0 penalty in MutantCodeSelector correctly rejects it,
    demonstrating the fitness gate in action during offline test runs.
    """
    fn = _extract_sig_name(signature) or "generated_function"
    return (
        f'def {fn}(*args, **kwargs):\n'
        f'    """[FALLBACK-C] Deliberate SyntaxError for gate validation."""\n'
        f'    if True\n'           # <- intentional SyntaxError: missing colon
        f'        pass\n'
    )


def _extract_sig_name(signature: str) -> str:
    """Extract the bare function name from a signature string."""
    if not signature:
        return ""
    try:
        import ast as _ast
        tree = _ast.parse(signature.rstrip().rstrip(":") + ": pass")
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                return node.name
    except SyntaxError:
        pass
    return ""


# =============================================================================
# Class: DraftCoordinator
# =============================================================================

class DraftCoordinator:
    """
    Evolutionary Draft Coordinator — live LLM inference bridge for EMMA.

    Dispatches three concurrent inference requests to a locally-hosted Ollama
    endpoint (OpenAI-compatible) using Python's standard ``urllib.request``
    module, offloaded to worker threads via ``asyncio.to_thread`` to preserve
    FastAPI's async event loop throughput.

    Each request carries a distinct system prompt and temperature coefficient
    to guarantee structural diversification across Mutants A, B, and C:

    +-----------+----------------------------+-------------+
    | Slot      | Cognitive Axis             | Temperature |
    +-----------+----------------------------+-------------+
    | Mutant A  | Parsimonious Architect     | 0.20        |
    | Mutant B  | Structural Alternative     | 0.70        |
    | Mutant C  | Creative Decoupler         | 0.95        |
    +-----------+----------------------------+-------------+

    XML Extraction
    --------------
    Every response is parsed with a pre-compiled ``re.DOTALL | re.IGNORECASE``
    regex to extract the code body from ``<CODE_PROPOSAL>`` boundary tags.
    Extracted code is verified via ``compile(..., "exec")`` before being
    returned. Responses that fail extraction or compilation trigger a
    per-slot simulation fallback without affecting sibling slots.

    Offline Resilience
    ------------------
    ``asyncio.gather(return_exceptions=True)`` is used so that a connection
    failure or timeout on any one slot does not cancel its siblings. Each
    exception is caught per-slot and replaced with a deterministic simulation
    fallback. A structured diagnostic log is emitted for every fallback
    activation.

    Parameters
    ----------
    llm_url : str
        Base URL of the Ollama OpenAI-compatible endpoint.
        Default: ``http://localhost:11434/v1``.
    model : str
        Model identifier forwarded in the JSON request body.
        Default: ``qwen2.5-coder``.
    timeout : float
        Hard wall-clock ceiling in seconds for ``urllib.request.urlopen``.
        Covers both TCP connect and full response read phases. Default: 10.0.
    max_tokens : int
        ``max_tokens`` field in the LLM request body. Default: 1024.
    """

    def __init__(
        self,
        llm_url:    str   = "http://localhost:11434/v1",
        model:      str   = "qwen2.5-coder",
        timeout:    float = 10.0,
        max_tokens: int   = 1024,
    ) -> None:
        self.llm_url:    str   = llm_url.rstrip("/")
        self.model:      str   = model
        self.timeout:    float = max(0.5, timeout)
        self.max_tokens: int   = max(64, max_tokens)

        # Pre-compile the XML extraction regex at construction time.
        # re.DOTALL  — "." matches newlines, enabling multi-line code capture.
        # re.IGNORECASE — tolerates minor casing deviations from the model.
        self._code_proposal_re: re.Pattern[str] = re.compile(
            r"<CODE_PROPOSAL>"           # Opening anchor tag
            r"\s*"                       # Optional whitespace / newlines
            r"(?:```python\s*)?"         # Optional opening markdown fence
            r"(.*?)"                     # Group 1: code body (non-greedy)
            r"(?:\s*```)?"              # Optional closing markdown fence
            r"\s*"                       # Optional whitespace / newlines
            r"</CODE_PROPOSAL>",         # Closing anchor tag
            re.DOTALL | re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # User message construction
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        task:             str,
        target_signature: str,
        file_context:     str,
    ) -> str:
        """
        Construct the user-role message shared across all three parallel
        requests.

        Includes the task description, optional function signature, and a
        truncated snippet of the active file context to guide the model.
        Context is hard-truncated at ``_MAX_CONTEXT_CHARS`` characters to
        stay within token budget.

        Parameters
        ----------
        task : str
            Natural-language description of the code-generation objective.
        target_signature : str
            Optional target function signature the candidate must satisfy.
        file_context : str
            Current source content of the file being modified.

        Returns
        -------
        str
            Fully assembled user-role message string.
        """
        parts: List[str] = [f"TASK: {task}"]

        if target_signature.strip():
            parts.append(f"TARGET SIGNATURE:\n{target_signature.strip()}")

        if file_context.strip():
            truncated = file_context.strip()[:_MAX_CONTEXT_CHARS]
            parts.append(
                f"ACTIVE FILE CONTEXT "
                f"(truncated to {_MAX_CONTEXT_CHARS} chars):\n"
                f"```python\n{truncated}\n```"
            )

        parts.append(
            "Wrap your ENTIRE solution inside <CODE_PROPOSAL> and "
            "</CODE_PROPOSAL> tags. Output absolutely nothing else."
        )

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Synchronous LLM HTTP call (executed inside a worker thread)
    # ------------------------------------------------------------------

    def _sync_llm_call(
        self,
        system_prompt: str,
        user_message:  str,
        temperature:   float,
    ) -> str:
        """
        Perform a synchronous HTTP POST to the local LLM endpoint.

        This method is intentionally synchronous — it must be called via
        ``asyncio.to_thread`` to avoid blocking the async event loop.

        Constructs a minimal OpenAI-compatible JSON payload, opens the
        connection with ``urllib.request.urlopen``, and returns the raw
        text content of the first completion choice.

        Parameters
        ----------
        system_prompt : str
            Role-specific system instruction for this mutant slot.
        user_message : str
            Shared user-role message containing the task and context.
        temperature : float
            Temperature coefficient controlling output entropy.

        Returns
        -------
        str
            Raw content string from ``choices[0].message.content``.

        Raises
        ------
        urllib.error.URLError
            On connection failure, DNS resolution failure, or timeout.
        urllib.error.HTTPError
            On HTTP error responses (4xx / 5xx) from the server.
        ValueError
            If the JSON response does not match the expected schema.
        json.JSONDecodeError
            If the server response body is not valid JSON.
        """
        endpoint: str = f"{self.llm_url}/chat/completions"

        payload: Dict[str, Any] = {
            "model":       self.model,
            "temperature": temperature,
            "max_tokens":  self.max_tokens,
            "stream":      False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        }

        body: bytes = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url     = endpoint,
            data    = body,
            headers = {
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            method  = "POST",
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            raw: str = resp.read().decode("utf-8")

        data: Dict[str, Any] = json.loads(raw)

        try:
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"Unexpected LLM response schema. "
                f"Top-level keys present: {list(data.keys())}"
            ) from exc

        return content

    # ------------------------------------------------------------------
    # XML extraction and bytecode verification
    # ------------------------------------------------------------------

    def _extract_code_proposal(self, raw_response: str) -> Optional[str]:
        """
        Extract and verify the code body from a raw LLM response string.

        Pipeline
        --------
        1. Apply the pre-compiled ``_code_proposal_re`` regex to locate the
           ``<CODE_PROPOSAL>`` block anywhere in the response (ignoring
           preambles, postambles, and markdown wrappers).
        2. Strip leading/trailing whitespace from Group 1.
        3. Reject empty extractions.
        4. Call ``compile(code, "<sandbox>", "exec")`` to verify bytecode
           viability — the same compilation mode used by the sandbox exec.
           A ``SyntaxError`` here returns ``None``, triggering fallback.

        Parameters
        ----------
        raw_response : str
            Full text response from the LLM endpoint.

        Returns
        -------
        str | None
            Clean, verified Python code string on success.
            ``None`` when no valid ``<CODE_PROPOSAL>`` block is found or
            when the extracted code fails syntax verification.
        """
        match = self._code_proposal_re.search(raw_response)
        if match is None:
            return None

        code: str = match.group(1).strip()
        if not code:
            return None

        # Bytecode viability gate — identical compilation mode to sandbox exec
        try:
            compile(code, "<sandbox>", "exec")
        except SyntaxError:
            return None

        return code

    # ------------------------------------------------------------------
    # Diagnostic logging
    # ------------------------------------------------------------------

    def _log_fallback(self, label: str, exc: BaseException) -> None:
        """
        Emit the mandatory structured fallback diagnostic log.

        The exact format is specified in EMMA_02_A2_plan_v2.md §3.7 and
        must not be altered — the test suite asserts on this string signature.

        Parameters
        ----------
        label : str
            Mutant slot label: "A", "B", or "C".
        exc : BaseException
            The exception that triggered the fallback.
        """
        exc_type: str = type(exc).__name__
        exc_msg:  str = str(exc)
        print(
            f"[DraftCoordinator] FALLBACK: Mutant {label} \u2014 LLM unreachable. "
            f"Reason: {exc_type}: {exc_msg} "
            f"Substituting simulation mutant."
        )

    def _log_extraction_failure(self, label: str, raw_preview: str) -> None:
        """
        Emit a diagnostic log when XML extraction or compilation fails.

        Parameters
        ----------
        label : str
            Mutant slot label: "A", "B", or "C".
        raw_preview : str
            First 200 characters of the raw response, for diagnostics.
        """
        print(
            f"[DraftCoordinator] EXTRACTION_FAIL: Mutant {label} \u2014 "
            f"No valid <CODE_PROPOSAL> block or SyntaxError in extracted code. "
            f"Response preview: {repr(raw_preview[:200])} "
            f"Substituting simulation mutant."
        )

    # ------------------------------------------------------------------
    # Simulation fallback mutants
    # ------------------------------------------------------------------

    def _fallback_mutant(
        self,
        slot_index: int,
        task:       str,
        signature:  str,
    ) -> str:
        """
        Return the deterministic simulation fallback for a given slot index.

        Fallback contract:
          - Slot 0 (Mutant A): syntactically valid   → passes fitness gate
          - Slot 1 (Mutant B): syntactically valid   → passes fitness gate
          - Slot 2 (Mutant C): deliberate SyntaxError → rejected at -100.0

        Parameters
        ----------
        slot_index : int
            Zero-based index of the mutant slot (0=A, 1=B, 2=C).
        task : str
            Task description forwarded to the simulation template.
        signature : str
            Target function signature forwarded to the simulation template.

        Returns
        -------
        str
            Simulation mutant code string.
        """
        if slot_index == 0:
            return _FALLBACK_A(task, signature)
        if slot_index == 1:
            return _FALLBACK_B(task, signature)
        return _FALLBACK_C(task, signature)

    # ------------------------------------------------------------------
    # Primary public interface
    # ------------------------------------------------------------------

    async def generate_drafts(
        self,
        task:             str,
        target_signature: str = "",
        file_context:     str = "",
    ) -> List[str]:
        """
        Generate three structurally diverse Python code candidates.

        Orchestrates the full parallel inference pipeline:

        1. Build the shared user message from task, signature, and context.
        2. Dispatch three concurrent ``asyncio.to_thread`` coroutines, each
           calling ``_sync_llm_call`` with a distinct system prompt and
           temperature coefficient.
        3. Collect all results via ``asyncio.gather(return_exceptions=True)``.
           This guarantees that an exception in any single slot does not
           cancel or disrupt its siblings — each slot is handled independently.
        4. For each result:
           a. If the result is a ``BaseException``, emit the fallback
              diagnostic log and substitute the simulation fallback.
           b. If the result is a string, attempt XML extraction and
              bytecode verification via ``_extract_code_proposal``.
              On failure, emit the extraction-failure log and substitute
              the simulation fallback.
           c. If extraction succeeds, use the clean code string directly.
        5. Return a list of exactly three code strings: [Mutant_A, Mutant_B, Mutant_C].

        Parameters
        ----------
        task : str
            Natural-language description of the code-generation objective.
        target_signature : str
            Optional function signature the generated code must satisfy.
        file_context : str
            Current source content of the file being modified (for LLM context).

        Returns
        -------
        List[str]
            Exactly three Python code strings corresponding to Mutants A, B, C.
            Slots that encountered errors contain deterministic fallback code.
        """
        user_message: str = self._build_user_message(
            task, target_signature, file_context
        )

        # Build three coroutines, one per slot
        coroutines = [
            asyncio.to_thread(
                self._sync_llm_call,
                _SYSTEM_PROMPTS[i],
                user_message,
                _TEMPERATURES[i],
            )
            for i in range(3)
        ]

        # Gather concurrently — return_exceptions=True prevents a single
        # failure from cancelling healthy sibling threads
        raw_results: List[Any] = await asyncio.gather(
            *coroutines,
            return_exceptions=True,
        )

        mutants: List[str] = []

        for i, result in enumerate(raw_results):
            label: str = _LABELS[i]

            # ── Slot failure: connection error, timeout, or schema error ──
            if isinstance(result, BaseException):
                self._log_fallback(label, result)
                mutants.append(self._fallback_mutant(i, task, target_signature))
                continue

            # ── Slot success: attempt XML extraction + syntax verification ──
            extracted: Optional[str] = self._extract_code_proposal(result)

            if extracted is None:
                # Extraction failed or code contained a SyntaxError
                self._log_extraction_failure(label, result)
                mutants.append(self._fallback_mutant(i, task, target_signature))
                continue

            # Clean, verified code — append directly
            mutants.append(extracted)

        return mutants