# backend/app/tests/test_advanced_core.py

"""
Unit Tests for the EMMA Cognitive Core
======================================
Verifies:
1. ASTContextRotator (JIT context rotation)
2. PageCurveEvaporator (Log compaction)
3. CausalConvergenceMonitor (Loop stability detection)
4. CodeGenerator (Sandboxing, security auditing, atomic commits)
"""

import os
import tempfile
from pathlib import Path
from app.core.context_scheduler import ASTContextRotator, PageCurveEvaporator
from app.core.orchestrator import CausalConvergenceMonitor
from app.core.code_generator import CodeGenerator

# ---------------------------------------------------------------------------
# Test: ASTContextRotator
# ---------------------------------------------------------------------------
def test_ast_context_rotator():
    mock_code = """class TestClass:
    def method_one(self):
        print("One")
        return 1

    def method_two(self, x, y):
        print("Two")
        return x + y
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(mock_code)
        temp_path = f.name
        
    try:
        rotator = ASTContextRotator(temp_path)
        # Rotate focusing only on 'method_two'
        rotated = rotator.get_rotated_context("method_two")
        
        # Assert 'method_one' is stubbed out
        assert "def method_one(self):" in rotated
        assert "        ..." in rotated
        # Assert 'method_two' is fully intact
        assert "print(\"Two\")" in rotated
        assert "return x + y" in rotated
        assert "TRANSIENT_CONTEXT" in rotated
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Test: PageCurveEvaporator
# ---------------------------------------------------------------------------
def test_page_curve_evaporator():
    evaporator = PageCurveEvaporator(max_lines=3)
    raw_log = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nERROR: process finished with code 1"
    
    evaporated = evaporator.evaporate_log(raw_log)
    
    # Assert it has been condensed and includes critical info
    assert "Log Evaporated" in evaporated
    assert "Total Lines=6" in evaporated
    assert "Status=1" in evaporated
    assert "ERROR: process finished with code 1" in evaporated


# ---------------------------------------------------------------------------
# Test: CausalConvergenceMonitor
# ---------------------------------------------------------------------------
def test_causal_convergence_monitor():
    monitor = CausalConvergenceMonitor(loop_threshold=3)
    
    error_1 = "npm ERR! ERESOLVE unable to resolve dependency tree: websockets@2.0.1"
    error_2 = "npm ERR! ERESOLVE unable to resolve dependency tree: websockets@2.0.1"
    error_3 = "npm ERR! ERESOLVE unable to resolve dependency tree: websockets@2.0.1"
    
    # Turn 1 and 2 should remain stable
    assert monitor.evaluate_step(error_1) is True
    assert monitor.evaluate_step(error_2) is True
    
    # Turn 3 with same error should detect instability
    assert monitor.evaluate_step(error_3) is False


# ---------------------------------------------------------------------------
# Test: CodeGenerator Sandbox & Security
# ---------------------------------------------------------------------------
async def test_code_generator_sandbox_security():
    with tempfile.TemporaryDirectory() as tmp_dir:
        generator = CodeGenerator(workspace_path=tmp_dir)
        
        # Test clean valid code running in sandbox
        clean_code = "def test():\n    return 42\n"
        success, stdout, stderr, latency = generator.run_sandbox(clean_code)
        assert success is True
        
        # Test code with syntax error
        broken_code = "def test()\n    return 42\n"
        report = generator._evaluate_mutant("C", broken_code)
        assert report.syntax_valid is False
        assert report.score == -100.0
        
        # Test code with forbidden import (os)
        malicious_code = "import os\nos.system('echo hack')"
        report = generator._evaluate_mutant("B", malicious_code)
        assert report.security_clean is False
        assert "Blocked import" in report.rejection_reason
        assert report.score == -100.0


# ---------------------------------------------------------------------------
# Test: CodeGenerator Atomic Commit
# ---------------------------------------------------------------------------
async def test_code_generator_atomic_commit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        generator = CodeGenerator(workspace_path=tmp_dir)
        target = Path(tmp_dir) / "app" / "core" / "executor.py"
        
        valid_code = "def solution(data):\n    return data\n"
        
        # Verify that atomic commit works and file is created
        success, commit_path, error = generator._atomic_commit(target, valid_code)
        assert success is True
        assert target.exists()
        assert target.read_text(encoding="utf-8") == valid_code


# ---------------------------------------------------------------------------
# Test: XML Extraction Gate
# ---------------------------------------------------------------------------
def test_xml_extractor():
    from app.core.executor import DraftCoordinator
    coordinator = DraftCoordinator()
    
    # 1. Clean XML
    assert coordinator._extract_code_proposal("<CODE_PROPOSAL>def f(): pass</CODE_PROPOSAL>") == "def f(): pass"
    
    # 2. Strips markdown fences
    assert coordinator._extract_code_proposal("<CODE_PROPOSAL>```python\ndef f(): pass\n```</CODE_PROPOSAL>") == "def f(): pass"
    
    # 3. Ignores preamble
    assert coordinator._extract_code_proposal("Here is the code:\n<CODE_PROPOSAL>def f(): pass</CODE_PROPOSAL>") == "def f(): pass"
    
    # 4. Ignores postamble
    assert coordinator._extract_code_proposal("<CODE_PROPOSAL>def f(): pass</CODE_PROPOSAL>\nThis does X.") == "def f(): pass"
    
    # 5. Lowercase tags
    assert coordinator._extract_code_proposal("<code_proposal>def f(): pass</code_proposal>") == "def f(): pass"
    
    # 6. No tags
    assert coordinator._extract_code_proposal("def f(): pass") is None
    
    # 7. Empty body
    assert coordinator._extract_code_proposal("<CODE_PROPOSAL>   </CODE_PROPOSAL>") is None
    
    # 8. Syntax error
    assert coordinator._extract_code_proposal("<CODE_PROPOSAL>def f( pass</CODE_PROPOSAL>") is None


# ---------------------------------------------------------------------------
# Test: DraftCoordinator Offline Fallback
# ---------------------------------------------------------------------------
import io
import json
from unittest.mock import MagicMock, patch

@patch("urllib.request.urlopen")
async def test_draft_coordinator_fallback(mock_urlopen):
    from app.core.executor import DraftCoordinator
    import urllib.error

    # Mock full failure (Ollama offline)
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
    coordinator = DraftCoordinator()
    
    # Capture print output to verify fallback logging
    import sys
    from io import StringIO
    stdout_buf = StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        mutants = await coordinator.generate_drafts(task="reverse list", target_signature="def solution(data) -> list:")
    finally:
        sys.stdout = old_stdout
    
    # Fallback mutants should be substituted
    assert len(mutants) == 3
    assert "FALLBACK: Mutant A" in stdout_buf.getvalue()
    assert "def solution(*args, **kwargs):" in mutants[0]
    assert "Deliberate SyntaxError" in mutants[2] # Deliberate C failure

    # Mock partial failure (Slot A & B succeed, Slot C fails with exception)
    mock_urlopen.side_effect = None
    
    def mock_urlopen_partial(request, timeout=None):
        body_data = json.loads(request.data.decode("utf-8"))
        system_prompt = body_data["messages"][0]["content"]
        
        # Mutant C has "radical" inside its system prompt
        if "radical" in system_prompt:
            raise urllib.error.HTTPError("http://localhost", 500, "Internal Server Error", {}, None)
        
        # Mutant A and B succeed
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = json.dumps({
            "choices": [{
                "message": {
                    "content": "<CODE_PROPOSAL>def solution(data):\n    return data</CODE_PROPOSAL>"
                }
            }]
        }).encode("utf-8")
        return resp

    mock_urlopen.side_effect = mock_urlopen_partial
    
    stdout_buf = StringIO()
    sys.stdout = stdout_buf
    try:
        mutants_partial = await coordinator.generate_drafts(task="sum numbers", target_signature="def solution(data):")
    finally:
        sys.stdout = old_stdout
    assert len(mutants_partial) == 3
    assert mutants_partial[0] == "def solution(data):\n    return data"
    assert mutants_partial[1] == "def solution(data):\n    return data"
    # Mutant C fell back to mock simulator C
    assert "def solution(*args, **kwargs):" in mutants_partial[2]
    assert "Deliberate SyntaxError" in mutants_partial[2]
    assert "FALLBACK: Mutant C" in stdout_buf.getvalue()


# ---------------------------------------------------------------------------
# Test: Parallel Concurrency
# ---------------------------------------------------------------------------
@patch("asyncio.to_thread")
async def test_parallel_concurrency(mock_to_thread):
    from app.core.executor import DraftCoordinator
    coordinator = DraftCoordinator()
    
    # We will mock the returns of to_thread to be empty strings
    mock_to_thread.return_value = "<CODE_PROPOSAL>def f(): pass</CODE_PROPOSAL>"
    
    mutants = await coordinator.generate_drafts(task="test concurrency")
    
    # Verify that asyncio.to_thread was spawned 3 times
    assert mock_to_thread.call_count == 3


# ---------------------------------------------------------------------------
# Test: CodeCritic
# ---------------------------------------------------------------------------
def test_critic_ast_comparison():
    from app.core.critic import CodeCritic
    critic = CodeCritic()
    
    orig = "def f(x):\n    return x + 1\n\nclass Data:\n    pass\n"
    # spacing/comment updates should not trigger modification
    mutant_comments = "def f(x):\n    # spacer\n    return x + 1\n\nclass Data:\n    pass\n"
    
    diff = critic.compare_ast(orig, mutant_comments)
    assert len(diff["added"]) == 0
    assert len(diff["deleted"]) == 0
    assert len(diff["modified"]) == 0

    # structural change in function logic
    mutant_struct = "def f(x):\n    return x + 2\n\nclass Data:\n    pass\n"
    diff_struct = critic.compare_ast(orig, mutant_struct)
    assert "def:f" in diff_struct["modified"]

    # added function
    mutant_added = orig + "\ndef new_func():\n    pass\n"
    diff_added = critic.compare_ast(orig, mutant_added)
    assert "def:new_func" in diff_added["added"]

    # deleted class
    mutant_deleted = "def f(x):\n    return x + 1\n"
    diff_deleted = critic.compare_ast(orig, mutant_deleted)
    assert "class:Data" in diff_deleted["deleted"]


def test_critic_surgical_splicing():
    from app.core.critic import CodeCritic
    critic = CodeCritic()
    
    orig = "def one():\n    return 1\n\ndef two():\n    return 2\n\ndef three():\n    return 3\n"
    mutant = "def one():\n    return 1\n\ndef two():\n    # modified\n    return 22\n\ndef three():\n    return 3\n"
    
    # splice target node 'def:two'
    spliced = critic.splice_node(orig, mutant, "def:two")
    
    expected = "def one():\n    return 1\n\ndef two():\n    # modified\n    return 22\n\ndef three():\n    return 3\n"
    assert spliced.strip() == expected.strip()


def test_critic_stai_score():
    from app.core.critic import CodeCritic
    critic = CodeCritic()
    
    orig = "def one():\n    return 1\n\ndef two():\n    return 2\n\ndef three():\n    return 3\n\ndef four():\n    return 4\n"
    # modify one out of four -> standard STAI triggers because total_original >= 3
    mutant = "def one():\n    return 1\n\ndef two():\n    return 22\n\ndef three():\n    return 3\n\ndef four():\n    return 4\n"
    
    spliced = critic.splice_node(orig, mutant, "def:two")
    report = critic.calculate_stai(orig, spliced)
    
    assert report["variant"] == "STAI"
    assert report["total_original_nodes"] == 4
    assert report["identical_nodes"] == 3
    assert report["stai"] == 0.75
    assert report["drift_detected"] is True
    assert report["verdict"] == "FAIL — structural drift exceeds tolerance"  # 0.75 < 0.85

    # edge case: STAI-DW (Deep-Walk) triggers because total_original < 3
    orig_small = "def only_one():\n    return 1\n"
    mutant_small = "def only_one():\n    return 11\n"
    spliced_small = critic.splice_node(orig_small, mutant_small, "def:only_one")
    report_small = critic.calculate_stai(orig_small, spliced_small)
    assert report_small["variant"] == "STAI-DW"
    assert report_small["stai"] < 1.0


def test_critic_error_monitor():
    from app.core.critic import CodeCritic
    critic = CodeCritic()
    
    # loop detected
    errors = [
        "TypeError: unsupported operand type(s)",
        "TypeError: unsupported operand type(s)",
        "TypeError: unsupported operand type(s)"
    ]
    report = critic.analyze_errors(errors, threshold=3)
    assert report["looping_detected"] is True
    assert report["frequent_error"] == "TypeError"
    assert "[CRITIQUE]" in report["critique"]

    # safe mixed errors (no loop)
    mixed = [
        "TypeError: unsupported operand type(s)",
        "IndexError: list index out of range",
        "TypeError: unsupported operand type(s)"
    ]
    report_mixed = critic.analyze_errors(mixed, threshold=3)
    assert report_mixed["looping_detected"] is False
    assert report_mixed["frequent_error"] is None


