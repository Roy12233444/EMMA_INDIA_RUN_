# backend/app/tests/test_manifold.py

"""
Integration Test Suite for the ANJANEYA Memory Protocol (AMP)
============================================================
Verifies:
1. SQLite Session Pool CRUD, Devotion Scores, and Hard-Freeze invariants.
2. LanceDB Semantic Manifold Event Ingestions and dynamic search modes (ANIMA/MADHYA/MAHIMA).
3. Chiranjeevi Spore Backup and self-healing Restore pipelines.
4. Skill Registry semantic indexing, AST checks, and retrieval.
5. All FastAPI REST endpoint routing under isolated database environments.
"""

import os
# Programmatic bypass for TensorFlow Keras 3 compatibility gate
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TRANSFORMERS_NO_TF"] = "1"

import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app

# Database module overrides for strict test isolation
import app.database.session as session_mod
import app.database.manifold as manifold_mod
import app.routers.manifold as router_mod

# Static UUID for reliable testing (strict UUID v4 format compliance required)
MOCK_UUID = "99368448-47b9-4101-9162-416256ad4c11"
ALT_UUID  = "12345678-1234-4321-abcd-1234567890ab"
SKILL_UUID = "abcdefab-abcd-4fab-a555-abcdefabcdef"


@pytest.fixture(scope="module", autouse=True)
def setup_temp_databases() -> Generator[None, None, None]:
    """
    Set up a completely temporary isolated environment for SQLite and LanceDB
    so that unit tests do not corrupt active production database data.
    """
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)

    # Backup original production database paths
    orig_session_db = session_mod.SESSION_DB
    orig_manifold_db = manifold_mod.MANIFOLD_DB
    orig_spore_dir = manifold_mod.SPORE_DIR

    # Override paths with temp directories
    session_mod.SESSION_DB = temp_path / "session_test.db"
    manifold_mod.MANIFOLD_DB = temp_path / "manifold_test.db"
    manifold_mod.SPORE_DIR = temp_path / "spores_test"

    # Also override router module paths to match the temporary environment perfectly
    router_mod.SESSION_DB = session_mod.SESSION_DB
    router_mod.MANIFOLD_DB = manifold_mod.MANIFOLD_DB
    router_mod.SPORE_DIR = manifold_mod.SPORE_DIR

    # Create temporary folders
    manifold_mod.MANIFOLD_DB.parent.mkdir(parents=True, exist_ok=True)
    manifold_mod.SPORE_DIR.mkdir(parents=True, exist_ok=True)

    # Force connection release and run dynamic schema bootstrap
    session_mod.close_thread_local_conn()
    session_mod.setup_sqlite_schema()

    yield

    # Teardown: close database threads and clean up the temporary workspace files
    session_mod.close_thread_local_conn()
    try:
        temp_dir.cleanup()
    except OSError:
        pass

    # Restore original production database paths
    session_mod.SESSION_DB = orig_session_db
    manifold_mod.MANIFOLD_DB = orig_manifold_db
    manifold_mod.SPORE_DIR = orig_spore_dir
    router_mod.SESSION_DB = orig_session_db
    router_mod.MANIFOLD_DB = orig_manifold_db
    router_mod.SPORE_DIR = orig_spore_dir


@pytest.fixture
def client() -> TestClient:
    """Fixture yielding a clean FastAPI TestClient."""
    return TestClient(app)


# =============================================================================
# 1. SQLite Session Pool Integration Tests
# =============================================================================

def test_sqlite_session_crud():
    """Verify session creation, fetching, and updating lifecycle."""
    session_mod.create_session(MOCK_UUID, "Test sovereign executor compilation")
    
    # Verify retrieval
    session = session_mod.get_session(MOCK_UUID)
    assert session is not None
    assert session["session_id"] == MOCK_UUID
    assert session["status"] == "running"
    assert session["turn_count"] == 0
    assert session["is_hard_frozen"] == 0

    # Retrieve all sessions
    all_sessions = session_mod.list_all_sessions()
    assert len(all_sessions) >= 1
    assert any(s["session_id"] == MOCK_UUID for s in all_sessions)


def test_devotion_score_math():
    """Verify calculation bounds of the Devotion scoring engine D = α·T_eff + β·U_eff."""
    # Test optimal fast run with few turns and low tokens
    D_opt, is_frozen_opt = session_mod.calculate_devotion_score(turn_count=2, token_peak=8000)
    assert D_opt >= 0.85
    assert is_frozen_opt is True

    # Test heavy slow run exceeding ceilings
    D_slow, is_frozen_slow = session_mod.calculate_devotion_score(turn_count=15, token_peak=100_000)
    assert D_slow == 0.0
    assert is_frozen_slow is False


def test_session_hard_freeze_gating():
    """Verify that hard-frozen sessions cannot be modified or updated."""
    # Update a session with success and optimal parameters to trigger a hard freeze
    result = session_mod.update_session_status(
        session_id=MOCK_UUID,
        status="success",
        token_peak=2000,
        turns=2
    )
    assert result is not None
    devotion_score, is_frozen = result
    assert devotion_score >= 0.85
    assert is_frozen is True

    # Attempt to update the hard-frozen session status
    # Immutability trigger protect_frozen_sessions should block this UPDATE
    session_mod.update_session_status(
        session_id=MOCK_UUID,
        status="failed",
        token_peak=99000
    )
    
    # Retrieve session and assert it remained untouched
    session_after = session_mod.get_session(MOCK_UUID)
    assert session_after["status"] == "success"
    assert session_after["is_hard_frozen"] == 1
    assert session_after["devotion_score"] == devotion_score

    # Deletion of frozen session must raise PermissionError
    with pytest.raises(PermissionError):
        session_mod.delete_session(MOCK_UUID)


# =============================================================================
# 2. LanceDB Semantic Manifold Integration Tests
# =============================================================================

def test_lancedb_event_ingestion_and_search():
    """Verify structured event recording and scaling ANIMA/MADHYA/MAHIMA searches."""
    # Create session for ingestion test
    session_mod.create_session(ALT_UUID, "Ingestion and search diagnostic testing")
    
    # Record trace traceback event
    manifold_mod.record_event(
        session_id=ALT_UUID,
        turn_id=1,
        content_type="traceback",
        payload="OAuth 2.0 connection refused: credentials validation failed"
    )

    # Record code patch event
    manifold_mod.record_event(
        session_id=ALT_UUID,
        turn_id=2,
        content_type="code_patch",
        payload="def repair(): return 'auth_patched'"
    )

    # Perform semantic searches
    # 1. ANIMA Mode (Compressed top-1 search)
    anima = manifold_mod.search_manifold("credentials validation failed", scaling_mode="ANIMA")
    assert anima["scaling_mode"] == "ANIMA"
    assert len(anima["results"]) >= 1
    assert "OAuth" in anima["results"][0]["payload"]

    # 2. MADHYA Mode (Intermediate top-3 with session details)
    madhya = manifold_mod.search_manifold("OAuth", scaling_mode="MADHYA")
    assert madhya["scaling_mode"] == "MADHYA"
    assert len(madhya["results"]) >= 1

    # 3. MAHIMA Mode (Full graph top-5 depth search)
    mahima = manifold_mod.search_manifold("credentials", scaling_mode="MAHIMA")
    assert mahima["scaling_mode"] == "MAHIMA"
    assert len(mahima["results"]) >= 1


# =============================================================================
# 3. FastAPI REST Endpoint Tests (TestClient)
# =============================================================================

def test_api_session_lifecycle(client: TestClient):
    """Test full session creation, retrieval, and status update REST pathways."""
    test_uuid = "11111111-2222-4333-a444-555555555555"
    
    # 1. Create session via POST /manifold/session
    resp = client.post(
        "/manifold/session",
        json={"session_id": test_uuid, "task_description": "API Integration Session Verification"}
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["status"] == "success"

    # 2. Attempt duplicate creation (idempotency check)
    dup = client.post(
        "/manifold/session",
        json={"session_id": test_uuid, "task_description": "API Integration Session Verification"}
    )
    assert dup.status_code == status.HTTP_201_CREATED
    assert dup.json()["status"] in ("exists", "success")

    # 3. Validation failure check
    fail = client.post(
        "/manifold/session",
        json={"session_id": "invalid-uuid-format", "task_description": "short"}
    )
    assert fail.status_code == 422
    assert fail.json()["error"] == "VALIDATION_ERROR"

    # 4. Fetch session via GET /manifold/session/{id}
    fetch = client.get(f"/manifold/session/{test_uuid}")
    assert fetch.status_code == status.HTTP_200_OK
    assert fetch.json()["session"]["task_description"] == "API Integration Session Verification"

    # 5. List all sessions via GET /manifold/sessions
    ls = client.get("/manifold/sessions")
    assert ls.status_code == status.HTTP_200_OK
    assert ls.json()["count"] >= 2

    # 6. Update session state to running
    update = client.patch(
        f"/manifold/session/{test_uuid}",
        json={"status": "running", "token_peak": 4000}
    )
    assert update.status_code == status.HTTP_200_OK
    assert update.json()["devotion_score"] is None

    # 7. Update to success and crystallize (triggers freeze)
    success = client.patch(
        f"/manifold/session/{test_uuid}",
        json={"status": "success", "token_peak": 1000, "turns": 2}
    )
    assert success.status_code == status.HTTP_200_OK
    body = success.json()
    assert body["is_hard_frozen"] is True
    assert body["devotion_score"] >= 0.85

    # 8. Mutating a frozen session via PATCH returns 403
    blocked = client.patch(
        f"/manifold/session/{test_uuid}",
        json={"status": "failed", "token_peak": 9999, "turns": 10}
    )
    assert blocked.status_code == status.HTTP_403_FORBIDDEN
    assert blocked.json()["detail"]["error"] == "SESSION_HARD_FROZEN"


def test_api_event_record_and_drift_search(client: TestClient):
    """Test trace logging and semantic search with Sankat Mochan auto-escalation."""
    test_uuid = "22222222-3333-4444-a555-666666666666"
    client.post(
        "/manifold/session",
        json={"session_id": test_uuid, "task_description": "API Ingestion Integration Test"}
    )

    # Ingest event
    record = client.post(
        "/manifold/record",
        json={
            "session_id": test_uuid,
            "turn_id": 1,
            "content_type": "traceback",
            "payload": "sqlite3.OperationalError: database is locked"
        }
    )
    assert record.status_code == status.HTTP_201_CREATED
    assert record.json()["status"] == "success"

    # Search with auto-escalation check (Sankat Mochan)
    # Cosine distance to a very distinct string should be low, but let's query it
    search = client.post(
        "/manifold/search",
        json={"query": "database is locked", "scaling_mode": "ANIMA"}
    )
    assert search.status_code == status.HTTP_200_OK
    data = search.json()
    assert len(data["results"]) >= 1
    # Check if results show our ingested text
    assert "locked" in data["results"][0]["payload"]


def test_api_skill_registry(client: TestClient):
    """Test diagnostic skill registration, AST syntax validation, and semantic search."""
    # 1. Register a valid python skill
    skill_data = {
        "skill_id": SKILL_UUID,
        "name": "sqlite_lock_breaker",
        "description": "Examine database connections and execute WAL TRUNCATE checkpoint to resolve sqlite database locks.",
        "script": "def run(ctx):\n    import sqlite3\n    print('Breaking lock')\n    return {'success': True}\n",
        "language": "python",
        "author_agent": "Atri-Agent-Alpha",
        "version": "1.0.0",
        "input_schema": {"timeout": "int"},
        "output_schema": {"success": "bool"}
    }
    reg = client.post("/manifold/skills", json=skill_data)
    assert reg.status_code == status.HTTP_201_CREATED
    assert reg.json()["status"] == "success"

    # 2. Attempt duplicate registration (Conflict)
    dup = client.post("/manifold/skills", json=skill_data)
    assert dup.status_code == status.HTTP_409_CONFLICT
    assert dup.json()["detail"]["error"] == "SKILL_ALREADY_EXISTS"

    # 3. Broken Python script registration (SyntaxError validation)
    broken_skill = skill_data.copy()
    broken_skill["skill_id"] = "00000000-0000-0000-0000-000000000000"
    broken_skill["script"] = "def broken(\n    return 42"
    fail = client.post("/manifold/skills", json=broken_skill)
    assert fail.status_code == 422
    assert "SyntaxError" in fail.json()["context"]["errors"][0]["message"]

    # 4. Search and retrieve skill semantically
    search = client.post(
        "/manifold/skills/search",
        json={"query": "fix SQLite locks and resolve operational lockouts", "verified_only": False}
    )
    assert search.status_code == status.HTTP_200_OK
    retrieved = search.json()
    assert retrieved["skill_id"] == SKILL_UUID
    assert retrieved["name"] == "sqlite_lock_breaker"
    assert "sqlite" in retrieved["script"]


# =============================================================================
# 4. Chiranjeevi Spore Persistence Integration Tests
# =============================================================================

def test_api_chiranjeevi_spore_and_restore(client: TestClient):
    """Verify compile-time Chiranjeevi backups and successful database self-healing."""
    # Trigger spore creation
    spore = client.post("/manifold/spore")
    assert spore.status_code == status.HTTP_200_OK
    assert spore.json()["status"] == "success"
    spore_file = spore.json()["spore_file"]
    assert "spore_" in spore_file

    # Verify spore actually exists on disk
    spore_path = Path(manifold_mod.SPORE_DIR) / spore_file
    assert spore_path.exists()

    # Trigger recovery restoration
    restore = client.post("/manifold/restore")
    assert restore.status_code == status.HTTP_200_OK
    assert restore.json()["status"] == "success"


def test_api_subsystem_health(client: TestClient):
    """Test structured diagnostics and sub-systems integrity snapshots."""
    health = client.get("/manifold/health")
    assert health.status_code == status.HTTP_200_OK
    data = health.json()
    assert data["status"] == "healthy"
    assert data["session_db_integrity"] is True
    assert data["manifold_db_exists"] is True
    assert data["spore_count"] >= 1
