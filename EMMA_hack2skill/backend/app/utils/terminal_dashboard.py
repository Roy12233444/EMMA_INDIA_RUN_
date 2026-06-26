"""
terminal_dashboard.py
=====================
EMMA UI Visualisation Layer — Live Cognitive Engine Cockpit

Provides a flicker-free, thread-safe, Rich-powered terminal dashboard
serving as the live visual showcase cockpit for the EMMA evolutionary
metacognitive solver. Designed for maximum impact during hackathon
live demonstrations.

Layout Grid:
  ┌──────────────────────────── HEADER ────────────────────────────────┐
  │  LEFT COLUMN               │  RIGHT COLUMN                         │
  │  ┌─ Context Compression ─┐ │  ┌─ Token Utilization ──────────────┐ │
  │  └───────────────────────┘ │  └──────────────────────────────────┘ │
  │  ┌─ Mutant Grading Table─┐ │  ┌─ Causal Convergence ─────────────┐ │
  │  │                       │ │  └──────────────────────────────────┘ │
  │  └───────────────────────┘ │  ┌─ Devotion Crystal ───────────────┐ │
  │                            │  └──────────────────────────────────┘ │
  ├──────────────────────────── LOGS ──────────────────────────────────┤
  └────────────────────────────────────────────────────────────────────┘

Dependencies: rich>=13.0
Python 3.9+. Thread-safe via threading.Lock.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, List, Optional

from rich.columns  import Columns
from rich.console  import Console
from rich.layout   import Layout
from rich.live     import Live
from rich.panel    import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table    import Table
from rich.text     import Text
from rich.align    import Align
from rich.rule     import Rule
from rich.style    import Style
from rich.padding  import Padding


# ---------------------------------------------------------------------------
# Colour palette  (cyberpunk neon)
# ---------------------------------------------------------------------------

_C_TEAL       = "bright_cyan"
_C_GOLD       = "yellow"
_C_GREEN      = "bright_green"
_C_RED        = "bright_red"
_C_MAGENTA    = "bright_magenta"
_C_BLUE       = "bright_blue"
_C_WHITE      = "bright_white"
_C_GREY       = "grey70"
_C_DIM        = "grey42"
_C_BG_DARK    = "on grey7"

_BORDER_TEAL  = "bright_cyan"
_BORDER_GOLD  = "yellow"
_BORDER_GREEN = "bright_green"
_BORDER_RED   = "bright_red"
_BORDER_MAG   = "bright_magenta"
_BORDER_BLUE  = "bright_blue"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class MutantResult:
    """Scoring record for a single candidate mutant."""
    label:         str           # "Mutant A" / "Mutant B" / "Mutant C"
    syntax_valid:  bool
    lines:         Optional[int]   = None
    latency_s:     Optional[float] = None
    base_score:    float           = 0.0
    length_penalty: float          = 0.0
    latency_penalty: float         = 0.0
    total_score:   float           = 0.0
    is_winner:     bool            = False
    rejected:      bool            = False


@dataclass
class TurnMetrics:
    """All metrics captured for a single solver turn."""
    turn_number:     int                  = 0
    raw_tokens:      int                  = 0
    rotated_tokens:  int                  = 0
    mutants:         List[MutantResult]   = field(default_factory=list)
    test_exit_code:  Optional[int]        = None
    test_elapsed_s:  float                = 0.0
    winner_label:    Optional[str]        = None


@dataclass
class DashboardState:
    """
    Central thread-safe state container for the EMMA dashboard.

    All public update methods acquire ``_lock`` before modifying any field,
    preventing data races under concurrent FastAPI/async worker threads.
    """

    # Session metadata
    session_id:       str   = "—"
    task:             str   = "Awaiting task..."
    max_turns:        int   = 15

    # Current turn
    current_turn:     int   = 0
    current_status:   str   = "INITIALISING"   # RUNNING / SUCCESS / ROLLED_BACK / FAILED

    # Context compression
    raw_tokens:       int   = 0
    rotated_tokens:   int   = 0

    # Token utilization
    token_peak:       int   = 0
    token_budget:     int   = 100_000

    # Mutant grading
    mutants:          List[MutantResult] = field(default_factory=list)

    # Causal convergence
    residuals:        List[float] = field(default_factory=list)
    loop_stable:      bool        = True

    # Devotion Crystal
    devotion_score:   float  = 0.0
    is_hard_frozen:   bool   = False
    devotion_computed: bool  = False

    # Spore
    spore_file:       Optional[str] = None

    # Log ring buffer — max 50 entries
    log_buffer:       Deque[str] = field(
        default_factory=lambda: deque(maxlen=50)
    )

    # Internal mutex
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
        compare=False,
    )

    # ── Thread-safe update methods ─────────────────────────────────────────

    def set_session(self, session_id: str, task: str, max_turns: int = 15) -> None:
        with self._lock:
            self.session_id  = session_id[:16] + "..." if len(session_id) > 16 else session_id
            self.task        = task[:72] + "..." if len(task) > 72 else task
            self.max_turns   = max_turns
            self.current_status = "RUNNING"
        self.log(f"💎 Session registered: {session_id[:8]}...")

    def set_turn(self, turn: int) -> None:
        with self._lock:
            self.current_turn = turn
        self.log(f"⚡ Turn {turn}/{self.max_turns} initiated")

    def set_context_compression(self, raw: int, rotated: int) -> None:
        with self._lock:
            self.raw_tokens     = raw
            self.rotated_tokens = rotated
        pct = round((1 - rotated / raw) * 100, 1) if raw > 0 else 0.0
        self.log(f"📐 Context rotated: {raw} → {rotated} tokens (−{pct}%)")

    def set_token_peak(self, peak: int) -> None:
        with self._lock:
            self.token_peak = max(self.token_peak, peak)

    def set_mutants(self, mutants: List[MutantResult]) -> None:
        with self._lock:
            self.mutants = list(mutants)
        for m in mutants:
            if m.is_winner:
                self.log(f"🏆 Winner: {m.label} (score={m.total_score:.2f}) — committing...")
            elif not m.syntax_valid:
                self.log(f"✗ {m.label}: SyntaxError — REJECTED (score=-100.00)")

    def add_residual(self, residual: float) -> None:
        with self._lock:
            self.residuals.append(residual)
            # Check last 3
            recent = self.residuals[-3:]
            self.loop_stable = not (
                len(recent) >= 3 and all(r >= 0.95 for r in recent)
            )

    def set_devotion(self, score: float, frozen: bool) -> None:
        with self._lock:
            self.devotion_score    = score
            self.is_hard_frozen    = frozen
            self.devotion_computed = True
            self.current_status    = "SUCCESS"
        if frozen:
            self.log(f"💎 CRYSTALLISED — D={score:.6f} ≥ Θ=0.85")
        else:
            self.log(f"✓ Devotion D={score:.6f} (not crystallised)")

    def set_status(self, status: str) -> None:
        with self._lock:
            self.current_status = status

    def set_spore(self, spore_file: str) -> None:
        with self._lock:
            self.spore_file = spore_file
        self.log(f"📦 Spore archived: {spore_file}")

    def log(self, message: str) -> None:
        """Append a timestamped log line to the ring buffer."""
        ts  = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{_C_DIM}]{ts}[/{_C_DIM}]  {message}"
        with self._lock:
            self.log_buffer.append(line)

    def snapshot(self) -> "DashboardState":
        """
        Return a shallow copy of all public fields under lock.
        Used by the render thread to read a consistent state snapshot.
        """
        with self._lock:
            snap                   = DashboardState.__new__(DashboardState)
            snap._lock             = threading.Lock()   # fresh lock for snapshot
            snap.session_id        = self.session_id
            snap.task              = self.task
            snap.max_turns         = self.max_turns
            snap.current_turn      = self.current_turn
            snap.current_status    = self.current_status
            snap.raw_tokens        = self.raw_tokens
            snap.rotated_tokens    = self.rotated_tokens
            snap.token_peak        = self.token_peak
            snap.token_budget      = self.token_budget
            snap.mutants           = list(self.mutants)
            snap.residuals         = list(self.residuals)
            snap.loop_stable       = self.loop_stable
            snap.devotion_score    = self.devotion_score
            snap.is_hard_frozen    = self.is_hard_frozen
            snap.devotion_computed = self.devotion_computed
            snap.spore_file        = self.spore_file
            snap.log_buffer        = deque(self.log_buffer, maxlen=50)
            return snap


# =============================================================================
# Panel Builders
# =============================================================================

def _build_header(s: DashboardState) -> Panel:
    """Top banner — session ID, task, turn counter, global status."""
    status_map = {
        "INITIALISING": (f"[{_C_GOLD}]◌ INITIALISING[/{_C_GOLD}]",   _BORDER_GOLD),
        "RUNNING":      (f"[{_C_TEAL}]⚡ RUNNING[/{_C_TEAL}]",        _BORDER_TEAL),
        "SUCCESS":      (f"[{_C_GREEN}]✅ SUCCESS[/{_C_GREEN}]",       _BORDER_GREEN),
        "ROLLED_BACK":  (f"[{_C_RED}]🚨 ROLLED BACK[/{_C_RED}]",      _BORDER_RED),
        "FAILED":       (f"[{_C_RED}]❌ FAILED[/{_C_RED}]",           _BORDER_RED),
    }
    status_text, border = status_map.get(
        s.current_status,
        (f"[{_C_GREY}]{s.current_status}[/{_C_GREY}]", _BORDER_TEAL),
    )

    turn_str = (
        f"[{_C_WHITE}]Turn[/{_C_WHITE}] "
        f"[{_C_GOLD}]{s.current_turn}[/{_C_GOLD}]"
        f"[{_C_DIM}]/[/{_C_DIM}]"
        f"[{_C_GREY}]{s.max_turns}[/{_C_GREY}]"
    )
    session_str = f"[{_C_DIM}]Session:[/{_C_DIM}] [{_C_TEAL}]{s.session_id}[/{_C_TEAL}]"
    task_str    = f"[{_C_DIM}]Task:[/{_C_DIM}] [{_C_WHITE}]{s.task}[/{_C_WHITE}]"

    title_line = Text.assemble(
        ("⚡ EMMA COGNITIVE ENGINE  ·  ", Style(color="bright_cyan", bold=True)),
        ("NEXUS AI RESEARCH LAB  ·  ",    Style(color="yellow",       bold=True)),
        ("EMMA SOLVER v3.0",              Style(color="bright_white", bold=True)),
    )

    body = Text()
    body.append_text(title_line)
    body.append("\n")
    body.append(f"  {session_str}   {turn_str}   Status: {status_text}   {task_str}",
                style="default")

    return Panel(
        Align.center(body),
        border_style=border,
        padding=(0, 1),
    )


def _build_context_panel(s: DashboardState) -> Panel:
    """JIT context compression metrics."""
    raw     = s.raw_tokens
    rotated = s.rotated_tokens
    pct     = (1.0 - rotated / raw) * 100.0 if raw > 0 else 0.0
    ok      = raw > 0 and rotated > 0

    body = Text()
    body.append("  Raw File:        ", style=_C_DIM)
    body.append(f"{raw:>7,} tokens\n", style=_C_WHITE)

    body.append("  Rotated Context: ", style=_C_DIM)
    body.append(f"{rotated:>7,} tokens\n", style=_C_TEAL if ok else _C_DIM)

    body.append("  Compression:     ", style=_C_DIM)
    if ok:
        pct_style = _C_GREEN if pct >= 70 else _C_GOLD
        body.append(f"{pct:>6.1f}%", style=pct_style)
        body.append("   ✓", style=_C_GREEN)
    else:
        body.append("   —",  style=_C_DIM)
        body.append("  waiting...", style=_C_DIM)

    return Panel(
        body,
        title=f"[{_C_TEAL}]📐 CONTEXT COMPRESSION[/{_C_TEAL}]",
        border_style=_BORDER_TEAL,
        padding=(0, 1),
    )


def _build_token_panel(s: DashboardState) -> Panel:
    """Token utilization progress bar."""
    peak   = s.token_peak
    budget = s.token_budget
    ratio  = min(peak / budget, 1.0) if budget > 0 else 0.0
    pct    = ratio * 100.0

    bar_width = 34
    filled    = int(bar_width * ratio)
    empty     = bar_width - filled

    if pct < 50:
        bar_colour = _C_GREEN
    elif pct < 80:
        bar_colour = _C_GOLD
    else:
        bar_colour = _C_RED

    bar = Text()
    bar.append("  Peak:  ", style=_C_DIM)
    bar.append(f"{peak:>8,}", style=_C_WHITE)
    bar.append(f" / {budget:,}\n", style=_C_DIM)
    bar.append("  ")
    bar.append("█" * filled, style=bar_colour)
    bar.append("░" * empty,  style=_C_DIM)
    bar.append(f"  {pct:5.1f}%\n", style=bar_colour)

    budget_status = (
        f"[{_C_GREEN}]Budget OK[/{_C_GREEN}]"   if pct < 80
        else f"[{_C_GOLD}]Budget HIGH[/{_C_GOLD}]" if pct < 95
        else f"[{_C_RED}]Budget CRITICAL[/{_C_RED}]"
    )
    bar.append(f"  {budget_status}", style="default")

    return Panel(
        bar,
        title=f"[{_C_GOLD}]⚡ TOKEN UTILIZATION[/{_C_GOLD}]",
        border_style=_BORDER_GOLD,
        padding=(0, 1),
    )


def _build_mutant_table(s: DashboardState) -> Panel:
    """Color-coded mutant fitness grading table."""
    table = Table(
        show_header   = True,
        header_style  = f"bold {_C_TEAL}",
        border_style  = _C_DIM,
        row_styles    = ["", "dim"],
        box           = None,
        padding       = (0, 1),
        expand        = True,
    )
    table.add_column("MUTANT",      style=f"bold {_C_WHITE}",  min_width=10)
    table.add_column("SYNTAX",      justify="center",           min_width=9)
    table.add_column("LINES",       justify="right",            min_width=7)
    table.add_column("LATENCY",     justify="right",            min_width=8)
    table.add_column("SCORE",       justify="right",            min_width=10)

    if not s.mutants:
        table.add_row(
            "[dim]—[/dim]", "[dim]—[/dim]", "[dim]—[/dim]",
            "[dim]—[/dim]", "[dim]awaiting...[/dim]",
        )
    else:
        for m in s.mutants:
            # Syntax indicator
            if m.syntax_valid:
                syntax_cell = f"[{_C_GREEN}]VALID ✓[/{_C_GREEN}]"
            else:
                syntax_cell = f"[{_C_RED}]FAIL  ✗[/{_C_RED}]"

            lines_cell   = f"{m.lines} ln"     if m.syntax_valid and m.lines   else "—"
            latency_cell = f"{m.latency_s:.2f}s" if m.syntax_valid and m.latency_s else "—"

            # Score cell
            if m.is_winner:
                score_cell = (
                    f"[bold {_C_GOLD}]{m.total_score:>8.2f}[/bold {_C_GOLD}]"
                    f" [bold {_C_GREEN}]WINNER[/bold {_C_GREEN}]"
                )
                row_style = f"bold"
            elif not m.syntax_valid or m.rejected:
                score_cell = f"[{_C_RED}]{m.total_score:>8.2f}  REJECT[/{_C_RED}]"
                row_style  = "dim"
            else:
                score_cell = f"[{_C_GREY}]{m.total_score:>8.2f}[/{_C_GREY}]"
                row_style  = ""

            table.add_row(
                m.label,
                syntax_cell,
                lines_cell,
                latency_cell,
                score_cell,
                style=row_style,
            )

    return Panel(
        table,
        title=f"[{_C_MAGENTA}]🛡️ MUTANT GRADING TABLE[/{_C_MAGENTA}]",
        border_style=_BORDER_MAG,
        padding=(0, 0),
    )


def _build_convergence_panel(s: DashboardState) -> Panel:
    """Causal Convergence Monitor — residual history and loop status."""
    body = Text()

    if not s.residuals:
        body.append("  No turns recorded yet.\n", style=_C_DIM)
    else:
        display = s.residuals[-8:]   # Show last 8 residuals max
        for i, r in enumerate(display):
            idx = len(s.residuals) - len(display) + i + 1

            if i > 0:
                delta = r - display[i - 1]
                arrow = f"[{_C_GREEN}]↓[/{_C_GREEN}]" if delta < 0 else f"[{_C_RED}]↑[/{_C_RED}]"
            else:
                arrow = f"[{_C_DIM}] [/{_C_DIM}]"

            stall = r >= 0.95
            r_style  = _C_RED if stall else (_C_GOLD if r >= 0.80 else _C_GREEN)
            flag     = f" [bold {_C_RED}]⚠ STALL[/bold {_C_RED}]" if stall else ""

            body.append(f"  Turn {idx:>2}  R_k = ", style=_C_DIM)
            body.append(f"{r:.4f}", style=r_style)
            body.append(f"  {arrow}{flag}\n", style="default")

    body.append("\n  Loop Status:  ", style=_C_DIM)
    if s.loop_stable:
        body.append("CONVERGING  🟢", style=f"bold {_C_GREEN}")
    else:
        body.append("PARADOX DETECTED  🔴", style=f"bold {_C_RED}")

    return Panel(
        body,
        title=f"[{_C_BLUE}]🔬 CAUSAL CONVERGENCE MONITOR[/{_C_BLUE}]",
        border_style=_BORDER_BLUE,
        padding=(0, 1),
    )


def _build_devotion_panel(s: DashboardState) -> Panel:
    """Devotion Crystal — score, threshold, freeze status, spore."""
    body = Text()

    if s.devotion_computed:
        d_pct   = s.devotion_score / 1.0 * 100
        d_style = _C_GREEN if s.devotion_score >= 0.85 else (_C_GOLD if s.devotion_score >= 0.60 else _C_RED)

        body.append("  Score D:    ", style=_C_DIM)
        body.append(f"{s.devotion_score:.6f}", style=f"bold {d_style}")
        body.append("\n")

        body.append("  Threshold:  ", style=_C_DIM)
        body.append("0.85  (Θ_crystal)\n", style=_C_WHITE)

        body.append("  Status:     ", style=_C_DIM)
        if s.is_hard_frozen:
            body.append("💎 CRYSTALLISED  ✓\n", style=f"bold {_C_GREEN}")
        else:
            body.append("NOT FROZEN\n", style=_C_GOLD)

        body.append("  Frozen:     ", style=_C_DIM)
        body.append(
            "YES  🟢" if s.is_hard_frozen else "NO   🔴",
            style=_C_GREEN if s.is_hard_frozen else _C_RED,
        )
    else:
        body.append("  Score D:    ", style=_C_DIM)
        body.append("computing...\n", style=_C_DIM)
        body.append("  Threshold:  ", style=_C_DIM)
        body.append("0.85\n", style=_C_GREY)
        body.append("  Status:     ", style=_C_DIM)
        body.append("IN PROGRESS\n", style=_C_GOLD)
        body.append("  Frozen:     ", style=_C_DIM)
        body.append("—", style=_C_DIM)

    if s.spore_file:
        body.append("\n\n  📦 Spore:   ", style=_C_DIM)
        body.append(s.spore_file, style=_C_TEAL)

    return Panel(
        body,
        title=f"[{_C_GREEN}]💎 DEVOTION CRYSTAL[/{_C_GREEN}]",
        border_style=_BORDER_GREEN,
        padding=(0, 1),
    )


def _build_log_panel(s: DashboardState, max_lines: int = 8) -> Panel:
    """Live solver log — ring buffer with timestamps."""
    body = Text()

    entries = list(s.log_buffer)
    display = entries[-max_lines:]

    for line in display:
        body.append(line + "\n", style="default")

    # Pad remaining lines to keep panel height stable
    while len(display) < max_lines:
        body.append("\n")
        display.append("")

    return Panel(
        body,
        title=f"[{_C_WHITE}]📡 LIVE SOLVER LOG[/{_C_WHITE}]",
        border_style=_C_DIM,
        padding=(0, 1),
    )


# =============================================================================
# Layout Assembly
# =============================================================================

def _create_layout() -> Layout:
    """
    Construct the fixed-structure dashboard grid.

    ┌─── header (3 rows) ─────────────────────────────────────────────┐
    │ left_col (ratio=1)      │ right_col (ratio=1)                    │
    │   context                 token_util                             │
    │   mutants                 convergence                            │
    │                           devotion                               │
    ├─── logs (10 rows) ──────────────────────────────────────────────┤
    """
    root = Layout()
    root.split_column(
        Layout(name="header",  size=4),
        Layout(name="body",    ratio=1),
        Layout(name="logs",    size=12),
    )
    root["body"].split_row(
        Layout(name="left_col",  ratio=1),
        Layout(name="right_col", ratio=1),
    )
    root["left_col"].split_column(
        Layout(name="context",  size=7),
        Layout(name="mutants",  ratio=1),
    )
    root["right_col"].split_column(
        Layout(name="token_util",  size=6),
        Layout(name="convergence", ratio=1),
        Layout(name="devotion",    size=9),
    )
    return root


def _render_layout(layout: Layout, s: DashboardState) -> Layout:
    """
    Populate every named layout slot with its current rendered panel.
    Called on every Live refresh cycle from the render thread.
    """
    layout["header"    ].update(_build_header(s))
    layout["context"   ].update(_build_context_panel(s))
    layout["mutants"   ].update(_build_mutant_table(s))
    layout["token_util"].update(_build_token_panel(s))
    layout["convergence"].update(_build_convergence_panel(s))
    layout["devotion"  ].update(_build_devotion_panel(s))
    layout["logs"      ].update(_build_log_panel(s))
    return layout


# =============================================================================
# Public Dashboard Class
# =============================================================================

class EMMADashboard:
    """
    Live terminal dashboard for the EMMA Cognitive Engine.

    Usage (as context manager):
    ---------------------------
    ::

        state = DashboardState()
        with EMMADashboard(state) as dash:
            state.set_session(session_id, task)
            state.set_turn(1)
            state.log("Solver started")
            # ... solver loop ...
            state.set_devotion(0.924, True)

    Usage (manual start/stop):
    --------------------------
    ::

        dash = EMMADashboard(state)
        dash.start()
        # ... do work ...
        dash.stop()

    Thread Safety:
    --------------
    ``DashboardState`` is internally protected by a ``threading.Lock``.
    All ``state.set_*()`` and ``state.log()`` calls are safe to invoke
    from any thread, including ``asyncio.to_thread`` worker threads.
    """

    def __init__(
        self,
        state:         DashboardState,
        refresh_rate:  float = 0.25,   # seconds between redraws
        console:       Optional[Console] = None,
    ) -> None:
        self._state        = state
        self._refresh_rate = refresh_rate
        self._console      = console or Console()
        self._layout       = _create_layout()
        self._live:        Optional[Live] = None
        self._render_thread: Optional[threading.Thread] = None
        self._stop_event   = threading.Event()

    # ── Context manager ────────────────────────────────────────────────────

    def __enter__(self) -> "EMMADashboard":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the Live dashboard and the background render thread."""
        self._stop_event.clear()
        self._live = Live(
            self._layout,
            console      = self._console,
            refresh_per_second = int(1 / self._refresh_rate),
            screen       = False,
            transient    = False,
        )
        self._live.start(refresh=True)
        self._render_thread = threading.Thread(
            target   = self._render_loop,
            daemon   = True,
            name     = "EMMADashboardRender",
        )
        self._render_thread.start()

    def stop(self) -> None:
        """Halt the render loop and stop the Live display cleanly."""
        self._stop_event.set()
        if self._render_thread:
            self._render_thread.join(timeout=2.0)
        if self._live:
            # Final render before stopping
            snap = self._state.snapshot()
            _render_layout(self._layout, snap)
            self._live.refresh()
            self._live.stop()

    # ── Background render loop ─────────────────────────────────────────────

    def _render_loop(self) -> None:
        """
        Background daemon thread that re-renders the layout from a
        consistent state snapshot every ``_refresh_rate`` seconds.

        Uses ``snapshot()`` to take a lock-guarded copy of DashboardState,
        preventing partial reads while the solver loop modifies state.
        """
        while not self._stop_event.is_set():
            try:
                snap = self._state.snapshot()
                _render_layout(self._layout, snap)
                if self._live:
                    self._live.refresh()
            except Exception:
                pass   # Never crash the render thread; silently skip bad frames
            time.sleep(self._refresh_rate)

    # ── Convenience proxy methods ──────────────────────────────────────────

    def log(self, message: str) -> None:
        """Proxy to ``DashboardState.log()``."""
        self._state.log(message)

    @property
    def state(self) -> DashboardState:
        """Direct access to the shared DashboardState."""
        return self._state


# =============================================================================
# Standalone Demo — run as __main__ for visual testing
# =============================================================================

if __name__ == "__main__":
    import asyncio
    import random

    async def _demo() -> None:
        """
        Simulate a 3-turn EMMA solver session for dashboard visual testing.
        Run: python backend/app/utils/terminal_dashboard.py
        """
        state = DashboardState()

        with EMMADashboard(state, refresh_rate=0.2) as dash:
            await asyncio.sleep(0.5)
            state.set_session(
                "99368448-47b9-4101-9162-416256ad4c11",
                "OAuth 2.0 token exchange integration",
                max_turns=15,
            )
            await asyncio.sleep(0.8)

            for turn in range(1, 4):
                state.set_turn(turn)
                await asyncio.sleep(0.4)

                # Context compression
                raw     = random.randint(2800, 3800)
                rotated = int(raw * random.uniform(0.12, 0.22))
                state.set_context_compression(raw, rotated)
                await asyncio.sleep(0.6)

                # Simulate mutant grading
                mut_a = MutantResult(
                    label="Mutant A", syntax_valid=True,
                    lines=random.randint(10, 16),
                    latency_s=round(random.uniform(1.5, 2.2), 2),
                    total_score=round(random.uniform(44, 49), 2),
                    is_winner=True,
                )
                mut_b = MutantResult(
                    label="Mutant B", syntax_valid=False,
                    total_score=-100.0, rejected=True,
                )
                mut_c = MutantResult(
                    label="Mutant C", syntax_valid=True,
                    lines=random.randint(32, 50),
                    latency_s=round(random.uniform(2.0, 2.8), 2),
                    total_score=round(random.uniform(38, 44), 2),
                )
                state.set_mutants([mut_a, mut_b, mut_c])
                state.set_token_peak(random.randint(5000, 12000))
                await asyncio.sleep(0.5)

                residual = round(random.uniform(0.60, 0.88), 4)
                state.add_residual(residual)
                state.log(f"🧪 Test command executed — turn {turn} result pending...")
                await asyncio.sleep(0.8)

            # Success
            state.log("✅ All tests PASSED!")
            state.set_devotion(0.9251, True)
            state.set_spore("spore_20260530T203000Z.zip")
            await asyncio.sleep(3.0)

    asyncio.run(_demo())
