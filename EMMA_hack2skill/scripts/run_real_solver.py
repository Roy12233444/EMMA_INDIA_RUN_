# scripts/run_real_solver.py
"""
run_real_solver.py
==================
EMMA Production Central Executive Solver — Live Action CLI Runner
EMM-05-A1  ·  Nexus AI Research Lab

The top-level CLI showrunner of the EMMA Cognitive Engine.

Responsibilities:
  1. Collect developer configuration via a Rich interactive prompt shell.
  2. Register the solver session in the SQLite AMP database.
  3. Instantiate and launch the EMMADashboard live terminal cockpit.
  4. Execute the async Orchestrator solver loop with full callback hooks.
  5. Surface SUCCESS / ROLLED_BACK / FAILED final states on the dashboard.
  6. Compile a Chiranjeevi Spore archive on successful completion.
  7. Handle all exit paths (clean, interrupt, causal paradox) gracefully.
"""

import os
import sys
import uuid
import asyncio
import time
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt  import Prompt
from rich.panel   import Panel
from rich.text    import Text
from rich.style   import Style
from rich.rule    import Rule

# ── Windows terminal UTF-8 safeguard ───────────────────────────────────────
# Prevents emoji / unicode characters from crashing cmd.exe / PowerShell
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass   # Python < 3.7 — no reconfigure; best effort

# ── Ensure backend/ is on the import path ──────────────────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent
_BACKEND_DIR = (_SCRIPT_DIR / ".." / "backend").resolve()
sys.path.insert(0, str(_BACKEND_DIR))

# ── Application imports (after path fix) ───────────────────────────────────
try:
    from app.core.orchestrator import Orchestrator, CausalInstabilityException
except ImportError as _e:
    Console().print(
        f"[bold red]IMPORT ERROR[/bold red]: Cannot locate EMMA backend modules.\n"
        f"  Ensure you are running from the project root and that "
        f"backend/ is correctly structured.\n  Detail: {_e}"
    )
    sys.exit(1)

try:
    from app.utils.terminal_dashboard import DashboardState, EMMADashboard, MutantResult
except ImportError as _e:
    Console().print(
        f"[bold red]IMPORT ERROR[/bold red]: terminal_dashboard module missing.\n"
        f"  Detail: {_e}"
    )
    sys.exit(1)

try:
    from app.database.session import create_session, update_session_status
    _AMP_AVAILABLE = True
except ImportError:
    _AMP_AVAILABLE = False

try:
    from app.database.manifold import create_spore, record_event
    _MANIFOLD_AVAILABLE = True
except ImportError:
    _MANIFOLD_AVAILABLE = False

# Global Rich console (used outside dashboard context)
_con = Console()


# =============================================================================
# Interactive Configuration Shell
# =============================================================================

_BANNER = """
[bold bright_cyan]
╔══════════════════════════════════════════════════════════════════════════════╗
║   ⚡  EMMA COGNITIVE ENGINE  ·  NEXUS AI RESEARCH LAB  ·  SOLVER v3.0       ║
║   🔱  ANJANEYA Memory Protocol  ·  SUDARSHANA Safety Layer Active            ║
╚══════════════════════════════════════════════════════════════════════════════╝
[/bold bright_cyan]"""

_SECTION = "[bold bright_cyan]◈[/bold bright_cyan]"


def _prompt_config() -> dict:
    """
    Display the premium interactive configuration shell and collect all
    solver parameters from the developer via Rich prompts.

    Returns a fully-populated configuration dict.
    """
    parser = argparse.ArgumentParser(description="EMMA Live Solver Config")
    parser.add_argument("--task", default=None)
    parser.add_argument("--target-file", default=None)
    parser.add_argument("--test-command", default=None)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--loop-threshold", type=int, default=None)
    parser.add_argument("--force-system", action="store_true", default=None)
    parser.add_argument("--non-interactive", "-y", action="store_true", default=False)
    
    args, unknown = parser.parse_known_args()
    
    # If non-interactive or any command-line option is provided, bypass prompt
    if args.non_interactive or any(v is not None for v in [args.task, args.target_file, args.test_command, args.max_turns, args.loop_threshold, args.force_system]):
        task = args.task or "Add a descriptive module docstring to backend/app/utils/mock_target.py"
        target_file = args.target_file or "backend/app/utils/mock_target.py"
        test_cmd = args.test_command or "python scripts/run_tests.py"
        max_turns = args.max_turns if args.max_turns is not None else 15
        loop_threshold = args.loop_threshold if args.loop_threshold is not None else 3
        force_sys = bool(args.force_system)
        
        return {
            "task":           task.strip(),
            "target_file":    target_file.strip(),
            "test_command":   test_cmd.strip(),
            "max_turns":      max(1, max_turns),
            "loop_threshold": max(1, loop_threshold),
            "force_system":   force_sys,
            "session_id":     str(uuid.uuid4()),
            "workspace_root": str(Path.cwd()),
        }

    _con.print(_BANNER)
    _con.print(Rule(style="bright_cyan"))
    _con.print(f"  {_SECTION} [bold white]CONFIGURE LIVE SOLVER SESSION[/bold white]\n")

    task = Prompt.ask(
        f"  [cyan]Task Description[/cyan]",
        default="Add a descriptive module docstring to backend/app/utils/mock_target.py",
        console=_con,
    )

    target_file = Prompt.ask(
        f"  [cyan]Target File[/cyan] (relative to workspace root)",
        default="backend/app/utils/mock_target.py",
        console=_con,
    )

    test_cmd = Prompt.ask(
        f"  [cyan]Verification Command[/cyan]",
        default="python scripts/run_tests.py",
        console=_con,
    )

    max_turns_str = Prompt.ask(
        f"  [cyan]Max Solver Turns[/cyan]",
        default="15",
        console=_con,
    )

    threshold_str = Prompt.ask(
        f"  [cyan]Causal Loop Threshold[/cyan] (turns before Git rollback)",
        default="3",
        console=_con,
    )

    force_sys_str = Prompt.ask(
        f"  [cyan]Force System Override[/cyan] (allow writes to core dirs)",
        choices=["y", "n"],
        default="n",
        console=_con,
    )

    _con.print()
    _con.print(Rule(style="bright_cyan"))

    try:
        max_turns = int(max_turns_str)
    except ValueError:
        max_turns = 15

    try:
        loop_threshold = int(threshold_str)
    except ValueError:
        loop_threshold = 3

    return {
        "task":           task.strip(),
        "target_file":    target_file.strip(),
        "test_command":   test_cmd.strip(),
        "max_turns":      max(1, max_turns),
        "loop_threshold": max(1, loop_threshold),
        "force_system":   force_sys_str.lower() == "y",
        "session_id":     str(uuid.uuid4()),
        "workspace_root": str(Path.cwd()),
    }


# =============================================================================
# Orchestrator ↔ Dashboard Bridge Callbacks
# =============================================================================

def _make_callbacks(state: DashboardState) -> dict:
    """
    Build a dictionary of callback functions that the Orchestrator can call
    to update the dashboard state in real time.

    These callbacks are injected into the Orchestrator's kwargs so it can
    surface live metrics without importing the dashboard module directly.
    """

    def on_turn_start(turn: int) -> None:
        state.set_turn(turn)

    def on_context_compressed(raw: int, rotated: int) -> None:
        state.set_context_compression(raw, rotated)

    def on_token_peak(peak: int) -> None:
        state.set_token_peak(peak)

    def on_mutants_graded(graded: list) -> None:
        """
        Receive a list of graded mutant dicts from CodeGenerator and
        convert them to MutantResult objects for the dashboard table.
        """
        results = []
        for g in graded:
            results.append(MutantResult(
                label          = g.get("label", "—"),
                syntax_valid   = g.get("syntax_valid", False),
                lines          = g.get("lines"),
                latency_s      = g.get("latency"),
                base_score     = g.get("base_score", 0.0),
                length_penalty = g.get("length_penalty", 0.0),
                latency_penalty= g.get("latency_penalty", 0.0),
                total_score    = g.get("total_score", 0.0),
                is_winner      = g.get("is_winner", False),
                rejected       = g.get("rejected", False),
            ))
        state.set_mutants(results)

    def on_residual(r: float) -> None:
        state.add_residual(r)

    def on_log(msg: str) -> None:
        state.log(msg)

    return {
        "on_turn_start":       on_turn_start,
        "on_context_compressed": on_context_compressed,
        "on_token_peak":       on_token_peak,
        "on_mutants_graded":   on_mutants_graded,
        "on_residual":         on_residual,
        "on_log":              on_log,
    }


# =============================================================================
# AMP Session Integration
# =============================================================================

def _register_amp_session(session_id: str, task: str) -> bool:
    """
    Register the solver session in the SQLite AMP database.

    Returns True on success, False if the AMP module is unavailable.
    Errors are logged but never crash the solver startup.
    """
    if not _AMP_AVAILABLE:
        return False
    try:
        create_session(session_id, task)
        return True
    except Exception as exc:
        _con.print(f"  [yellow]⚠ AMP session registration failed: {exc}[/yellow]")
        return False


def _finalise_amp_session(
    session_id:   str,
    status:       str,
    turns_elapsed: int,
    token_peak:   int,
) -> tuple:
    """
    Update the AMP session status and compute the Devotion Score.

    Returns (devotion_score, is_frozen) on success, (None, None) on error.
    """
    if not _AMP_AVAILABLE:
        return (None, None)
    try:
        result = update_session_status(
            session_id = session_id,
            status     = status,
            token_peak = token_peak,
            turns      = turns_elapsed if status == "success" else None,
        )
        return result if result else (None, None)
    except Exception as exc:
        _con.print(f"  [yellow]⚠ AMP session finalisation failed: {exc}[/yellow]")
        return (None, None)


def _trigger_spore(state: DashboardState) -> None:
    """Compile a Chiranjeevi Spore archive after a successful solve."""
    if not _MANIFOLD_AVAILABLE:
        return
    try:
        spore_path = create_spore()
        state.set_spore(spore_path.name)
    except Exception as exc:
        state.log(f"⚠ Spore creation failed: {exc}")


# =============================================================================
# Post-Solve Summary Panel
# =============================================================================

def _print_summary(
    cfg:           dict,
    result:        dict,
    devotion_score: object,
    is_frozen:     object,
    elapsed_wall:  float,
) -> None:
    """Render the final summary panel after the dashboard context closes."""
    status       = result.get("status", "UNKNOWN")
    turns        = result.get("turns_elapsed", "—")
    monitor      = result.get("monitor_summary", {})

    status_map = {
        "SUCCESS":      "[bold bright_green]✅  SUCCESS[/bold bright_green]",
        "MAX_TURNS_REACHED": "[bold yellow]⏱  MAX TURNS REACHED[/bold yellow]",
        "ROLLED_BACK":  "[bold bright_red]🚨  ROLLED BACK[/bold bright_red]",
        "FAILED":       "[bold bright_red]❌  FAILED[/bold bright_red]",
    }
    status_str = status_map.get(status, f"[white]{status}[/white]")

    lines = [
        f"  {status_str}",
        f"",
        f"  [dim]Session ID   :[/dim]  [bright_cyan]{cfg['session_id']}[/bright_cyan]",
        f"  [dim]Task         :[/dim]  [white]{cfg['task'][:72]}[/white]",
        f"  [dim]Target File  :[/dim]  [white]{cfg['target_file']}[/white]",
        f"  [dim]Turns Elapsed:[/dim]  [yellow]{turns}[/yellow] / {cfg['max_turns']}",
        f"  [dim]Wall Time    :[/dim]  [yellow]{elapsed_wall:.1f}s[/yellow]",
    ]

    if devotion_score is not None:
        d_style = "bright_green" if is_frozen else "yellow"
        frozen_tag = "  💎 [bold bright_green]CRYSTALLISED[/bold bright_green]" if is_frozen else ""
        lines += [
            f"",
            f"  [dim]Devotion D   :[/dim]  [{d_style}]{devotion_score:.6f}[/{d_style}]{frozen_tag}",
            f"  [dim]Threshold   :[/dim]  0.85  (Θ_crystal)",
        ]

    if monitor:
        paradox = monitor.get("paradox_detected", False)
        avg_r   = monitor.get("avg_residual", None)
        lines += [
            f"",
            f"  [dim]Causal Monitor:[/dim]  "
            f"{'[bright_red]PARADOX[/bright_red]' if paradox else '[bright_green]STABLE[/bright_green]'}",
        ]
        if avg_r is not None:
            lines.append(
                f"  [dim]Avg Residual :[/dim]  [white]{avg_r:.4f}[/white]"
            )

    body = "\n".join(lines)
    _con.print()
    _con.print(Panel(
        body,
        title="[bold bright_cyan]⚡ EMMA SOLVER — FINAL REPORT[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))
    _con.print()


# =============================================================================
# Main Async Solver Harness
# =============================================================================

async def run_live_solver() -> int:
    """
    Full lifecycle of a single EMMA solver session.

    Returns
    -------
    int
        Exit code: 0 = success / max-turns, 1 = rolled-back / failed.
    """
    cfg = _prompt_config()

    _con.print(
        f"\n  {_SECTION} [bold white]INITIALISING EMMA COGNITIVE ENGINE...[/bold white]\n"
    )

    # ── AMP Session Registration ──────────────────────────────────────────
    amp_ok = _register_amp_session(cfg["session_id"], cfg["task"])
    _con.print(
        f"  {'[green]✓[/green]' if amp_ok else '[yellow]⚠[/yellow]'} "
        f"AMP session {'registered' if amp_ok else 'skipped (module unavailable)'}"
    )

    # ── Dashboard State Initialisation ───────────────────────────────────
    state = DashboardState()
    cbs   = _make_callbacks(state)

    # ── Orchestrator Setup ────────────────────────────────────────────────
    try:
        orchestrator = Orchestrator(
            workspace_path = cfg["workspace_root"],
            max_turns      = cfg["max_turns"],
            loop_threshold = cfg["loop_threshold"],
            test_command   = cfg["test_command"],
        )
        _con.print(f"  [green]✓[/green] Orchestrator instantiated")
    except Exception as exc:
        _con.print(f"  [bold red]✗ Orchestrator instantiation failed: {exc}[/bold red]")
        return 1

    _con.print(
        f"\n  {_SECTION} [bold bright_cyan]LAUNCHING LIVE COCKPIT...[/bold bright_cyan]\n"
    )
    time.sleep(0.5)

    # ── Live Dashboard Context ────────────────────────────────────────────
    result         = {}
    devotion_score = None
    is_frozen      = None
    exit_code      = 0
    t_start        = time.perf_counter()

    with EMMADashboard(state, refresh_rate=0.25) as _dash:

        # Populate initial dashboard state
        state.set_session(cfg["session_id"], cfg["task"], cfg["max_turns"])
        state.log("⚡ EMMA Cognitive Engine initialised")
        state.log(f"🎯 Task: {cfg['task'][:60]}...")
        state.log(f"📁 Target: {cfg['target_file']}")
        state.log(f"🧪 Test: {cfg['test_command']}")
        state.log(f"💡 Max turns: {cfg['max_turns']}  |  Threshold: {cfg['loop_threshold']}")

        if amp_ok:
            state.log("💾 AMP session registered in SQLite manifold")

        state.log("─" * 52)

        # ── Steering callback ─────────────────────────────────────────────
        async def on_request_steering(prompt_msg: str) -> str:
            _dash.stop()
            console = Console()
            console.print()
            alert_body = Text()
            alert_body.append("⚡ [SARATHI] HUMAN-IN-THE-LOOP STEERING INTERRUPT ACTIVE\n", style="bold yellow")
            alert_body.append("Causal Convergence Monitor has flagged a stalled sequence.\n\n", style="yellow")
            alert_body.append(prompt_msg, style="bright_white")
            
            console.print(Panel(
                alert_body,
                title="[bold yellow]🔱 SARATHI STEERING CONTROLLER[/bold yellow]",
                border_style="yellow",
                padding=(1, 2)
            ))
            
            hint = Prompt.ask(
                "  [cyan]Steering Guidance [skip][/cyan]",
                default="",
                console=console
            )
            
            _dash.start()
            return hint.strip()

        # ── Solver Execution ──────────────────────────────────────────────
        try:
            result = await orchestrator.solve(
                task_description = cfg["task"],
                target_file      = cfg["target_file"],
                # Pass dashboard callbacks so the orchestrator can feed
                # live metrics into the UI panels in real time.
                on_turn_start          = cbs["on_turn_start"],
                on_context_compressed  = cbs["on_context_compressed"],
                on_token_peak          = cbs["on_token_peak"],
                on_mutants_graded      = cbs["on_mutants_graded"],
                on_residual            = cbs["on_residual"],
                on_log                 = cbs["on_log"],
                on_request_steering    = on_request_steering,
            )

            final_status   = result.get("status", "SUCCESS")
            turns_elapsed  = result.get("turns_elapsed", cfg["max_turns"])
            token_peak     = state.token_peak

            # ── Finalise AMP session ──────────────────────────────────────
            amp_status = "success" if final_status == "SUCCESS" else "failed"
            devotion_score, is_frozen = _finalise_amp_session(
                cfg["session_id"], amp_status, turns_elapsed, token_peak
            )

            if devotion_score is not None:
                state.set_devotion(devotion_score, bool(is_frozen))

            state.set_status(final_status)

            if final_status == "SUCCESS":
                state.log("✅ All tests PASSED — solver loop converged!")
                _trigger_spore(state)
            else:
                state.log(f"⏱ Solver reached max turns ({cfg['max_turns']})")

            exit_code = 0

        except CausalInstabilityException as exc:
            state.set_status("ROLLED_BACK")
            state.log(f"🚨 CAUSAL PARADOX at turn {exc.turn}")
            state.log("🔄 Git rollback executed — workspace restored")
            if exc.last_error:
                preview = exc.last_error[:120].replace("\n", " ")
                state.log(f"   Last error: {preview}...")

            _finalise_amp_session(cfg["session_id"], "rolled_back", exc.turn, state.token_peak)

            result    = {
                "status":          "ROLLED_BACK",
                "turns_elapsed":   exc.turn,
                "monitor_summary": {"paradox_detected": True, "residuals": exc.residuals},
            }
            exit_code = 1

        except KeyboardInterrupt:
            state.set_status("FAILED")
            state.log("[SYSTEM] Run aborted by operator (KeyboardInterrupt)")
            _finalise_amp_session(cfg["session_id"], "failed", state.current_turn, state.token_peak)
            result    = {"status": "FAILED", "turns_elapsed": state.current_turn}
            exit_code = 1

        except Exception as exc:
            import traceback
            state.set_status("FAILED")
            err_msg = f"❌ Unexpected error: {type(exc).__name__}: {str(exc)[:100]}"
            state.log(err_msg)
            # Print traceback to stderr for subprocess diagnostic logs
            sys.stderr.write(f"\n[CRITICAL RUNTIME ERROR] {err_msg}\n")
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            _finalise_amp_session(cfg["session_id"], "failed", state.current_turn, state.token_peak)
            result    = {"status": "FAILED", "turns_elapsed": state.current_turn}
            exit_code = 1

        # ── Final dashboard hold — let judge inspect the screen ───────────
        state.log("─" * 52)
        state.log("📊 Final state locked. Holding dashboard for 3s...")
        await asyncio.sleep(3.0)

    # Dashboard context closed — print final summary to clean terminal
    elapsed = time.perf_counter() - t_start
    _print_summary(cfg, result, devotion_score, is_frozen, elapsed)

    return exit_code


# =============================================================================
# Entry Point
# =============================================================================

def main() -> None:
    """Synchronous entry point — wraps the async harness."""
    try:
        code = asyncio.run(run_live_solver())
        sys.exit(code)
    except KeyboardInterrupt:
        _con.print("\n  [yellow][SYSTEM] Solver interrupted by operator. Safe exit.[/yellow]\n")
        sys.exit(0)
    except Exception as exc:
        _con.print(f"\n  [bold red][SYSTEM ERROR] Unhandled crash in CLI harness: {exc}[/bold red]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
