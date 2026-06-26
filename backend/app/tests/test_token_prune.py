# backend/app/tests/test_token_prune.py
"""
Unit Tests for Context Compaction & Token Pruner Subsystem
==========================================================
Verifies:
1. Token Counting Accuracy (Exact tiktoken vs Calibrated CJK Fallbacks)
2. Graduated Capacity Tiers (evaluate_threshold)
3. Dynamic Token-Entropy Importance Scorer (DTE-IS)
4. Context Compaction Fidelity (compact_history)
5. Robust Regex Traceback Extractors (_extract_error_signature)
6. Adaptive ESV Schema Dynamic Keys (_assemble_esv)
"""

import sys
import json
from unittest.mock import patch
from app.utils.token_prune import ContextVectorPruner, ContextOverflowError

# ---------------------------------------------------------------------------
# 1. Test: Token Counting Accuracy (Exact vs. Fallbacks)
# ---------------------------------------------------------------------------
def test_token_counting_accuracy():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    sample_text = "def hello_world(name: str) -> None:\n    print(f'Hello, {name}!')"
    
    # Check tiktoken exact count (if tiktoken is installed/available)
    try:
        import tiktoken
        has_tiktoken = True
    except ImportError:
        has_tiktoken = False
        
    if has_tiktoken:
        exact_count = pruner.count_tokens(sample_text)
        assert exact_count > 0
        
    # Simulate fallback tier 1 (tiktoken missing)
    with patch.dict(sys.modules, {'tiktoken': None}):
        pruner_no_tiktoken = ContextVectorPruner(max_tokens=8000)
        fallback_count = pruner_no_tiktoken.count_tokens(sample_text)
        
        assert fallback_count > 0
        if has_tiktoken:
            # Fallback estimation should be close (within ±15%) of exact count
            exact_count = pruner.count_tokens(sample_text)
            diff_ratio = abs(fallback_count - exact_count) / exact_count
            assert diff_ratio <= 0.15

    # Test CJK character estimator
    cjk_text = "你好世界，这是一个十分复杂的上下文压缩算法测试。"
    cjk_count = pruner.count_tokens(cjk_text)
    assert cjk_count > 0

    # Test Fallback Tier 2 (force unicodedata import error or exception)
    with patch.dict(sys.modules, {'tiktoken': None}):
        with patch('unicodedata.east_asian_width', side_effect=RuntimeError("Mock Exception")):
            pruner_fail = ContextVectorPruner(max_tokens=8000)
            word_count_estimate = pruner_fail.count_tokens("hello world this is a test")
            assert word_count_estimate == int(6 * 1.35)

# ---------------------------------------------------------------------------
# 2. Test: Graduated Tiers (evaluate_threshold)
# ---------------------------------------------------------------------------
def test_threshold_evaluation():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    # GREEN tier (under 4400 tokens)
    tier, tokens = pruner.evaluate_threshold("Short sample history turn.")
    assert tier == "GREEN"
    assert tokens > 0
    
    # Mock count_tokens to test Amber, Red, Critical, and Overflow states
    with patch.object(pruner, 'count_tokens') as mock_count:
        # AMBER tier (55% - 70%) -> 4400 - 5599
        mock_count.return_value = 5000
        tier, tokens = pruner.evaluate_threshold("mocked")
        assert tier == "AMBER"
        assert tokens == 5000
        
        # RED tier (70% - 85%) -> 5600 - 6799
        mock_count.return_value = 6000
        tier, tokens = pruner.evaluate_threshold("mocked")
        assert tier == "RED"
        assert tokens == 6000
        
        # CRITICAL tier (85% - 95%) -> 6800 - 7599
        mock_count.return_value = 7200
        tier, tokens = pruner.evaluate_threshold("mocked")
        assert tier == "CRITICAL"
        assert tokens == 7200
        
        # OVERFLOW tier (> 95%) -> >= 7600
        mock_count.return_value = 7800
        tier, tokens = pruner.evaluate_threshold("mocked")
        assert tier == "OVERFLOW"
        assert tokens == 7800

# ---------------------------------------------------------------------------
# 3. Test: Entropy Scoring DTE-IS (score_entropy)
# ---------------------------------------------------------------------------
def test_entropy_scoring_dte_is():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    # Turn history:
    # Turns 1 and 2: Identical repeated NameError (penalized as low entropy noise)
    # Turn 3: Successful AST splice event report (marked high entropy)
    turn_logs = [
        {"role": "user", "content": "Fix the undefined variable error in critic.py", "turn_id": "1"},
        {
            "role": "assistant",
            "content": "Traceback (most recent call last):\n  File \"app/core/critic.py\", line 15, in check\n    print(undef_val)\nNameError: name 'undef_val' is not defined",
            "turn_id": "2"
        },
        {
            "role": "assistant",
            "content": "Traceback (most recent call last):\n  File \"app/core/critic.py\", line 15, in check\n    print(undef_val)\nNameError: name 'undef_val' is not defined",
            "turn_id": "3"
        },
        {
            "role": "assistant",
            "content": 'Action: splice_node successful. "commit_path": "backend/app/core/critic.py". Output verification: "verdict": "PASS", "stai": 1.0, "looping_detected": false',
            "turn_id": "4"
        }
    ]
    
    entropy_map = pruner.score_entropy(turn_logs)
    
    assert "turn_1" in entropy_map
    assert "turn_2" in entropy_map
    assert "turn_3" in entropy_map
    assert "turn_4" in entropy_map
    
    t3_entropy = entropy_map["turn_3"]["entropy"]
    t4_entropy = entropy_map["turn_4"]["entropy"]
    
    # Assert Turn 4 (AST splice & verification PASS) scores higher than Turn 3 (repeated exception)
    assert t4_entropy > t3_entropy
    assert "splice_success" in entropy_map["turn_4"]["structural_events"]
    assert entropy_map["turn_4"]["pin_priority"] in ("CRITICAL", "HIGH")

# ---------------------------------------------------------------------------
# 4. Test: Context Compaction Fidelity (compact_history)
# ---------------------------------------------------------------------------
async def test_log_compaction_fidelity():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    # Mock heavy traceback logs
    heavy_traceback = "Traceback (most recent call last):\n" + "\n".join([f"  File \"src/module_{i}.py\", line {i}, in run\n    y = {i}" for i in range(60)]) + "\nAssertionError: structural mismatch detected"
    
    turn_logs = [
        {"role": "user", "content": "Optimize the AST comparators.", "turn_id": 1},
        {"role": "assistant", "content": heavy_traceback, "turn_id": 2}
    ]
    
    pre_compact_str = json.dumps(turn_logs, ensure_ascii=False)
    pre_compact_tokens = pruner.count_tokens(pre_compact_str)
    
    # Mock evaluate_threshold to force a RED compact tier
    with patch.object(pruner, 'evaluate_threshold') as mock_eval:
        mock_eval.return_value = ("RED", pre_compact_tokens)
        
        compacted = await pruner.compact_history(turn_logs)
        
        # Turn 0 must contain the dynamic Adaptive ESV system card
        assert compacted[0]["role"] == "system"
        assert "[A-ESV COMPACTION RECORD]" in compacted[0]["content"]
        
        # Verify compaction compression yields a smaller footprint
        post_compact_str = json.dumps(compacted, ensure_ascii=False)
        post_compact_tokens = pruner.count_tokens(post_compact_str)
        
        assert post_compact_tokens < pre_compact_tokens

# ---------------------------------------------------------------------------
# 5. Test: Exception Scraper Edge Cases (_extract_error_signature)
# ---------------------------------------------------------------------------
def test_traceback_regex_edge_cases():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    # Case 1: Standard single-exception traceback
    raw_tb = """
Traceback (most recent call last):
  File "backend/app/core/critic.py", line 88, in compare_ast
    tree = ast.parse(source)
SyntaxError: invalid syntax (critic.py, line 88)
"""
    sig = pruner._extract_error_signature(raw_tb)
    assert sig["exception_type"] == "SyntaxError"
    assert sig["exception_msg"] == "invalid syntax (critic.py, line 88)"
    assert sig["file_path"] == "backend/app/core/critic.py"
    assert sig["line_number"] == "88"
    assert sig["enclosing_scope"] == "compare_ast"
    assert sig["source_line"] == "tree = ast.parse(source)"
    
    # Case 2: Bare AssertionError with no detail message
    bare_tb = """
Traceback (most recent call last):
  File "app/tests/test_core.py", line 12, in test_run
    assert value is True
AssertionError
"""
    sig_bare = pruner._extract_error_signature(bare_tb)
    assert sig_bare["exception_type"] == "AssertionError"
    assert sig_bare["exception_msg"] is None
    assert sig_bare["file_path"] == "app/tests/test_core.py"
    
    # Case 3: Chained exceptions (captures final Exception)
    chained_tb = """
Traceback (most recent call last):
  File "server.py", line 5, in run
    connect_db()
ConnectionRefusedError: port 5432 closed

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "server.py", line 7, in run
    raise RuntimeError("Database bootstrap failed")
RuntimeError: Database bootstrap failed
"""
    sig_chained = pruner._extract_error_signature(chained_tb)
    assert sig_chained["exception_type"] == "RuntimeError"
    assert sig_chained["exception_msg"] == "Database bootstrap failed"
    assert sig_chained["file_path"] == "server.py"
    assert sig_chained["line_number"] == "7"

# ---------------------------------------------------------------------------
# 6. Test: Adaptive ESV Keys Validation (_assemble_esv)
# ---------------------------------------------------------------------------
def test_esv_schema_adaptive_keys():
    pruner = ContextVectorPruner(max_tokens=8000)
    
    meta = {"compaction_tier": "RED"}
    entropy_map = {"turn_1": {"entropy": 0.05, "pin_priority": "NOISE"}}
    
    # Scenario A: Compaction with no STAI or regressions observed
    esv_clean = pruner._assemble_esv(
        session_meta=meta,
        entropy_map=entropy_map,
        pinned=[],
        condensed=[],
        dropped=[1],
        stai_reports=[],
        error_regressions=[],
        last_committed_file=None,
        recovery_checkpoint=None
    )
    
    assert "last_stai_report" not in esv_clean
    assert "active_error_regression" not in esv_clean
    assert "dropped_turns" in esv_clean
    
    # Scenario B: STAI failures, regression looping, commits active
    esv_complex = pruner._assemble_esv(
        session_meta=meta,
        entropy_map=entropy_map,
        pinned=[],
        condensed=[],
        dropped=[1],
        stai_reports=[{"stai": 0.45, "verdict": "FAIL"}],
        error_regressions=[{"looping_detected": True, "frequent_error": "NameError", "recurrence_count": 3}],
        last_committed_file="backend/app/core/critic.py",
        recovery_checkpoint=4
    )
    
    assert "last_stai_report" in esv_complex
    assert esv_complex["last_stai_report"]["verdict"] == "FAIL"
    assert "active_error_regression" in esv_complex
    assert esv_complex["active_error_regression"]["looping_detected"] is True
    assert esv_complex["active_error_regression"]["frequent_error"] == "NameError"
    assert esv_complex["last_committed_file"] == "backend/app/core/critic.py"
    assert esv_complex["recovery_checkpoint"] == 4


# ---------------------------------------------------------------------------
# EMM-03-A2: 12 Mock & Resilience Unit Tests
# ---------------------------------------------------------------------------

def test_prompt_assembly_completeness():
    pruner = ContextVectorPruner(max_tokens=8000)
    turn_logs = [
        {"role": "assistant", "turn_id": 1, "content": "TypeError in run_sandbox " * 20, "pin_priority": "HIGH"},
        {"role": "assistant", "turn_id": 2, "content": "splice_node called. committed: true. " * 20, "pin_priority": "CRITICAL"},
    ]
    telemetry = {
        "completed_tasks":     ["Step 1: Create CodeGenerator"],
        "pending_tasks":       ["Step 2: Fix TypeError"],
        "touched_files":       ["backend/app/core/code_generator.py"],
        "last_committed_file": None,
    }
    report = {
        "looping_detected": False,
        "frequent_error": None,
        "recurrence_count": 0,
        "critique": ""
    }
    prompt = pruner._build_summarization_prompt(turn_logs, telemetry, report)
    assert "Step 1: Create CodeGenerator" in prompt
    assert "Step 2: Fix TypeError" in prompt
    assert "backend/app/core/code_generator.py" in prompt
    assert "PINNED" in prompt


def test_json_extraction_strategy_1_clean():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = '{"schema_version": "esv/v2", "global_objective": "Fix TypeError."}'
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is not None
    assert parsed["schema_version"] == "esv/v2"
    assert parsed["global_objective"] == "Fix TypeError."


def test_json_extraction_strategy_2_fenced():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = 'Here is the state vector as requested:\n```json\n{"schema_version": "esv/v2", "global_objective": "Fix TypeError."}\n```'
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is not None
    assert parsed["schema_version"] == "esv/v2"


def test_json_extraction_strategy_3_preamble_text():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = 'Sure! I have analyzed the log. Here is the compiled state vector:\n{"schema_version": "esv/v2", "global_objective": "Fix TypeError."}\nI hope this helps!'
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is not None
    assert parsed["schema_version"] == "esv/v2"


def test_json_extraction_strategy_4_trailing_comma():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = '{"schema_version": "esv/v2", "global_objective": "Fix the bug.",}'
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is not None
    assert parsed["schema_version"] == "esv/v2"
    assert parsed["global_objective"] == "Fix the bug."


def test_json_extraction_strategy_5_truncated():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = '{"schema_version": "esv/v2", "global_objective": "Fix the TypeError in run_sandbox by en'
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is not None
    assert parsed["schema_version"] == "esv/v2"
    assert parsed["global_objective"] == "Fix the TypeError in run_sandbox by en"


def test_json_extraction_all_strategies_fail():
    pruner = ContextVectorPruner(max_tokens=8000)
    raw = "This output contains no JSON at all. Just words."
    parsed = pruner._extract_and_validate_json(raw)
    assert parsed is None


async def test_offline_fallback_triggers_on_urlerror():
    import urllib.error
    import time
    pruner = ContextVectorPruner(max_tokens=8000)
    turn_logs = [{"role": "user", "content": "Initial context"}]
    telemetry = {"completed_tasks": [], "pending_tasks": []}
    
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        t_start = time.perf_counter()
        esv = await pruner.compile_state_vector(turn_logs, telemetry)
        elapsed = time.perf_counter() - t_start
        assert esv["$compiler"] == "python_fallback"
        assert "$fallback_reason" in esv
        assert "probe failed" in esv["$fallback_reason"] or "URLError" in esv["$fallback_reason"]
        assert elapsed < 0.050


async def test_offline_fallback_triggers_on_timeout():
    import time
    pruner = ContextVectorPruner(max_tokens=8000)
    turn_logs = [{"role": "user", "content": "Initial context"}]
    telemetry = {"completed_tasks": [], "pending_tasks": []}
    
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        t_start = time.perf_counter()
        esv = await pruner.compile_state_vector(turn_logs, telemetry)
        elapsed = time.perf_counter() - t_start
        assert esv["$compiler"] == "python_fallback"
        assert "$fallback_reason" in esv
        assert elapsed < 0.050


async def test_health_probe_skips_inference_on_failure():
    pruner = ContextVectorPruner(max_tokens=8000)
    turn_logs = [{"role": "user", "content": "Initial context"}]
    telemetry = {"completed_tasks": [], "pending_tasks": []}
    
    with patch.object(pruner, "_probe_llm_health", return_value=False) as mock_probe:
        with patch.object(pruner, "_call_local_llm") as mock_llm:
            esv = await pruner.compile_state_vector(turn_logs, telemetry)
            mock_probe.assert_called_once()
            mock_llm.assert_not_called()
            assert esv["$compiler"] == "python_fallback"


def test_token_budget_convergence():
    pruner = ContextVectorPruner(max_tokens=8000, esv_token_cap=250)
    esv = {
        "schema_version": "esv/v2",
        "global_objective": "Solve a very complex and highly descriptive issue that needs absolute attention in multiple areas." * 5,
        "execution_state": {
            "current_phase": "exception_debugging",
            "touched_files": ["file1.py", "file2.py", "file3.py", "file4.py", "file5.py", "file6.py", "file7.py"]
        },
        "active_task_checklist": {
            "completed": ["Task 1 verified and done", "Task 2 verified and done", "Task 3 verified and done", "Task 4 verified and done"],
            "pending": ["Pending Task 1 details", "Pending Task 2 details"]
        },
        "last_known_error_regression": {
            "exception_class": "TypeError",
            "diagnosis_and_critique": "Make sure you review the sandbox args." * 10
        },
        "entropy_summary": {
            "total_turns_processed": 10,
            "critical_pins": 5,
            "noise_turns_dropped": 3
        }
    }
    
    truncated = pruner._enforce_token_budget(esv)
    assert pruner.count_tokens(json.dumps(truncated)) <= 250
    assert truncated["global_objective"] is not None


def test_causal_loop_alert_injection():
    pruner = ContextVectorPruner(max_tokens=8000)
    esv = {
        "last_known_error_regression": {
            "looping_detected": True,
            "exception_class": "TypeError",
            "recurrence_count": 4,
        }
    }
    report = {
        "critique": "[CRITIQUE] Sandbox exec failed."
    }
    alert = pruner._check_regression_loop(esv, report)
    assert alert is not None
    assert "[CAUSAL_LOOP_ALERT]" in alert
    assert "TypeError" in alert
    assert "Sandbox exec failed." in alert


def test_task_checklist_parity_enforcement():
    pruner = ContextVectorPruner(max_tokens=8000)
    esv = {
        "active_task_checklist": {
            "completed": ["Task 1"],
            "pending": ["Task 2"]
        }
    }
    telemetry = {
        "pending_tasks": ["Task 2", "Task 3"]
    }
    pruner._validate_esv_schema(esv, telemetry)
    assert "Task 3" in esv["active_task_checklist"]["pending"]


async def test_schema_version_tag_always_present():
    pruner = ContextVectorPruner(max_tokens=8000)
    turn_logs = [{"role": "user", "content": "Initial context"}]
    telemetry = {"completed_tasks": [], "pending_tasks": []}
    
    # Test fallback path
    with patch.object(pruner, "_probe_llm_health", return_value=False):
        esv_fb = await pruner.compile_state_vector(turn_logs, telemetry)
        assert esv_fb["schema_version"] == "esv/v2"
        
    # Test LLM compilation path
    with patch.object(pruner, "_probe_llm_health", return_value=True):
        mock_response = json.dumps({
            "schema_version": "esv/v2",
            "global_objective": "Verify systems.",
            "execution_state": {"current_phase": "planning"},
            "active_task_checklist": {"completed": [], "pending": []},
            "last_known_error_regression": {},
            "entropy_summary": {}
        })
        with patch.object(pruner, "_call_local_llm", return_value=mock_response):
            esv_llm = await pruner.compile_state_vector(turn_logs, telemetry)
            assert esv_llm["schema_version"] == "esv/v2"
