# scripts/run_real_solver.py
"""
EMMA Production Central Executive Solver — Real Live Action Runner
==================================================================
Runs the actual, production Orchestrator on real filesystem files, 
calling real code generators, executing real shell verifications, 
calculating actual active token counts, and triggering live DTE-IS compactions!
"""

import sys
import os
import asyncio

# Add backend directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.orchestrator import Orchestrator, CausalInstabilityException

def get_input(prompt: str, default: str) -> str:
    user_val = input(f"{prompt} [{default}]: ").strip()
    return user_val if user_val else default

async def run_live_solver():
    print("================================================================================")
    print(" 🔮 EMMA PRODUCTION EXECUTIVE COGNITIVE SOLVER: LIVE ACTION RUNNER")
    print("================================================================================")
    print("[INFO] Working Directory:", os.getcwd())
    
    # Prompt the user for real-world execution settings
    task_desc = get_input(
        "Enter the REAL task for EMMA to solve", 
        "Add a descriptive module docstring to backend/app/utils/token_prune.py"
    )
    
    target_file = get_input(
        "Enter the relative path of the file to modify", 
        "backend/app/utils/token_prune.py"
    )
    
    test_cmd = get_input(
        "Enter the verification test command", 
        "py scripts/run_tests.py"
    )
    
    max_turns = int(get_input("Enter the maximum solver turns ceiling", "5"))
    loop_threshold = int(get_input("Enter loop threshold before Git Rollback", "3"))

    print("\n[SYSTEM] Initializing Production Orchestrator with safe Git checkout safeguards...")
    
    # Instantiate the REAL orchestrator
    orchestrator = Orchestrator(
        workspace_path=os.getcwd(),
        max_turns=max_turns,
        loop_threshold=loop_threshold,
        test_command=test_cmd
    )
    
    print("[SYSTEM] Starting active solver loop. Watching filesystem closely...\n")
    
    try:
        # Run the actual production solve loop!
        result = await orchestrator.solve(
            task_description=task_desc,
            target_file=target_file
        )
        
        print("\n================================================================================")
        print(" 🎉 SOLVER LOOP COMPLETED SUCCESSFULLY!")
        print("================================================================================")
        print(f"Status:        {result.get('status')}")
        print(f"Turns Elapsed: {result.get('turns_elapsed')}")
        print("--------------------------------------------------------------------------------")
        print("[ORCHESTRATOR] Compaction Monitor Summary:")
        print(result.get("monitor_summary", {}))
        print("================================================================================")
        
    except CausalInstabilityException as e:
        print("\n================================================================================")
        print(" 🚨 CAUSAL LOOP DETECTED / SOLVER HALTED SAFETY FAILSAFE")
        print("================================================================================")
        print(f"Message:      {str(e)}")
        print(f"Turn Halted:  {e.turn}")
        print(f"Last Error:   {e.last_error[:200]}...")
        print("--------------------------------------------------------------------------------")
        print("[ORCHESTRATOR] Git checkout rollback successfully restored workspace safety.")
        print("================================================================================")
        sys.exit(1)
        
    except Exception as e:
        print("\n[SYSTEM ERROR] Unexpected crash in orchestrator loop:", e)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(run_live_solver())
    except KeyboardInterrupt:
        print("\n[SYSTEM] Solver interrupted by user. Safe exit.")
        sys.exit(0)
