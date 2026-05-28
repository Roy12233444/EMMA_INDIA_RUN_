# scripts/run_tests.py

"""
Zero-Dependency Test Runner for EMMA Cognitive Core
==================================================
Runs the unit tests located in backend/app/tests/test_advanced_core.py
using Python's native asyncio and standard library, ensuring zero external
dependencies are needed.
"""

import sys
import os
import asyncio
import traceback

# Add backend directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.tests.test_advanced_core import (
    test_ast_context_rotator,
    test_page_curve_evaporator,
    test_causal_convergence_monitor,
    test_code_generator_sandbox_security,
    test_code_generator_atomic_commit,
    test_xml_extractor,
    test_draft_coordinator_fallback,
    test_parallel_concurrency,
    test_critic_ast_comparison,
    test_critic_surgical_splicing,
    test_critic_stai_score,
    test_critic_error_monitor
)
from app.tests.test_token_prune import (
    test_token_counting_accuracy,
    test_threshold_evaluation,
    test_entropy_scoring_dte_is,
    test_log_compaction_fidelity,
    test_traceback_regex_edge_cases,
    test_esv_schema_adaptive_keys
)

async def run_all_tests():
    print("================================================================================")
    print(" [TEST RUNNER] INITIATING EMMA COGNITIVE CORE SUITE")
    print("================================================================================")
    
    tests = [
        ("test_ast_context_rotator", test_ast_context_rotator),
        ("test_page_curve_evaporator", test_page_curve_evaporator),
        ("test_causal_convergence_monitor", test_causal_convergence_monitor),
        ("test_code_generator_sandbox_security", test_code_generator_sandbox_security),
        ("test_code_generator_atomic_commit", test_code_generator_atomic_commit),
        ("test_xml_extractor", test_xml_extractor),
        ("test_draft_coordinator_fallback", test_draft_coordinator_fallback),
        ("test_parallel_concurrency", test_parallel_concurrency),
        ("test_critic_ast_comparison", test_critic_ast_comparison),
        ("test_critic_surgical_splicing", test_critic_surgical_splicing),
        ("test_critic_stai_score", test_critic_stai_score),
        ("test_critic_error_monitor", test_critic_error_monitor),
        ("test_token_counting_accuracy", test_token_counting_accuracy),
        ("test_threshold_evaluation", test_threshold_evaluation),
        ("test_entropy_scoring_dte_is", test_entropy_scoring_dte_is),
        ("test_log_compaction_fidelity", test_log_compaction_fidelity),
        ("test_traceback_regex_edge_cases", test_traceback_regex_edge_cases),
        ("test_esv_schema_adaptive_keys", test_esv_schema_adaptive_keys),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"[RUNNING] {name}...", end="", flush=True)
        try:
            if asyncio.iscoroutinefunction(test_fn):
                await test_fn()
            else:
                test_fn()
            print("\r[PASS]    " + name)
            passed += 1
        except Exception as e:
            print("\r[FAIL]    " + name)
            print("-" * 80)
            traceback.print_exc()
            print("-" * 80)
            failed += 1
            
    print("================================================================================")
    print(f" [TEST RUNNER] COMPLETE: {passed} passed, {failed} failed.")
    print("================================================================================")
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
