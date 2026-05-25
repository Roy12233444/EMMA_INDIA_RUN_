"""
inference_router.py
===================
EMMA — Inference Router

Thin routing adapter between CodeGenerator and DraftCoordinator.
Decouples the high-level code generator from the low-level inference
implementation details.
"""

import os
from typing import List, Optional
from app.config import settings
from app.core.executor import DraftCoordinator


class InferenceRouter:
    """
    Thin routing adapter between CodeGenerator and DraftCoordinator.
    Callers never import DraftCoordinator directly.
    """

    def __init__(self, coordinator: Optional[DraftCoordinator] = None) -> None:
        self._coordinator = coordinator or DraftCoordinator(
            llm_url    = settings.LOCAL_LLM_URL,
            model      = settings.LOCAL_LLM_MODEL,
            timeout    = 10.0,
            max_tokens = 1024,
        )

    async def request_mutants(
        self,
        file_path:        str,
        task:             str,
        num_mutants:      int = 3,
        target_signature: str = "",
    ) -> List[str]:
        """Route a mutant generation request to the DraftCoordinator."""
        # Read the file context safely to provide rich instructions to the LLM
        file_context = ""
        if file_path:
            # Try to resolve relative to the standard workspace
            base_dir = r"E:\EMMA_INDIA_RUN\EMMA_hack2skill"
            resolved_path = os.path.join(base_dir, file_path) if not os.path.isabs(file_path) else file_path
            
            try:
                if os.path.exists(resolved_path):
                    with open(resolved_path, "r", encoding="utf-8") as fh:
                        file_context = fh.read()
            except Exception:
                pass

        # Call DraftCoordinator
        return await self._coordinator.generate_drafts(
            task             = task,
            target_signature = target_signature,
            file_context     = file_context,
        )
