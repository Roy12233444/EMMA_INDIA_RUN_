@echo off
set EMMA_SIMULATION_MODE=1
C:\Users\soura\anaconda3\python.exe %~dp0scripts\run_real_solver.py --non-interactive %*
