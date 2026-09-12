import os
import sys
import json
import tempfile
import stat
import subprocess
import concurrent.futures
from agy_tools.logger import RunLogger, sanitize_data, sanitize_string, get_logger
from agy_tools.utils import safe_jail_path, emit_progress, emit_result, set_checkpoint_hook, set_result_hook

def test_sanitization():
    print("[TEST] Testing secret sanitization...")
    # 1. Bearer token
    assert "Bearer [REDACTED_TOKEN]" in sanitize_string("Authorization: Bearer my_secret_token_12345")
    
    # 2. Database URIs
    pg_uri = "postgres://dbuser:mypassword123@db.example.com:5432/proddb"
    sanitized_pg = sanitize_string(pg_uri)
    assert "mypassword123" not in sanitized_pg
    assert "[REDACTED_PASSWORD]" in sanitized_pg
    
    redis_uri = "redis://:super_redis_pwd@127.0.0.1:6379/0"
    sanitized_redis = sanitize_string(redis_uri)
    assert "super_redis_pwd" not in sanitized_redis
    assert "[REDACTED_PASSWORD]" in sanitized_redis

    # 3. CLI flags in strings
    cli_str = "cmd --password my_secret -p my_pwd --token abc12345"
    sanitized_cli = sanitize_string(cli_str)
    assert "my_secret" not in sanitized_cli
    assert "my_pwd" not in sanitized_cli

    # 4. CLI flags in lists
    cli_list = ["--password", "secret_arg", "-p", "pwd_arg", "--user", "admin"]
    sanitized_list = sanitize_data(cli_list)
    assert "secret_arg" not in sanitized_list
    assert "pwd_arg" not in sanitized_list
    assert sanitized_list[4:] == ["--user", "admin"]

    # 5. Dicts recursive
    payload = {
        "api_key": "AIzaSySecretApiKey12345678901234567",
        "nested": {
            "token": "ghp_123456789012345678901234567890123456",
            "safe": "visible"
        }
    }
    sanitized_dict = sanitize_data(payload)
    assert sanitized_dict["api_key"] == "[REDACTED_PASSWORD]"
    assert sanitized_dict["nested"]["token"] == "[REDACTED_PASSWORD]"
    assert sanitized_dict["nested"]["safe"] == "visible"
    print("  ✓ Secret sanitization tests passed.")

def test_permissions_and_rotation():
    print("[TEST] Testing permissions, locking, and rotation...")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_log = os.path.join(tmpdir, "test_runs.jsonl")
        logger = RunLogger(log_path=test_log)
        logger.max_bytes = 500  # Small size to trigger rotation quickly

        logger.start_run("sys test", session_id="test-perm", caller_cwd="/tmp")
        logger.end_run(status="SUCCESS")

        assert os.path.exists(test_log)
        # Check permissions
        mode = os.stat(test_log).st_mode
        assert mode & 0o777 == 0o600, f"Expected 0o600, got {oct(mode & 0o777)}"

        # Trigger rotation by writing multiple runs
        for i in range(10):
            logger.start_run(f"sys test {i}", args=["long_argument_padding_to_fill_bytes" * 5])
            logger.end_run(status="SUCCESS")

        assert os.path.exists(f"{test_log}.1"), "Rotated log file .1 should exist"
    print("  ✓ Permissions and rotation tests passed.")

def test_concurrency():
    print("[TEST] Testing advisory flock concurrency...")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_log = os.path.join(tmpdir, "concurrent_runs.jsonl")

        def worker(idx):
            l = RunLogger(log_path=test_log)
            for j in range(20):
                l.start_run(f"worker_{idx}_cmd_{j}", session_id=f"sess_{idx}")
                l.checkpoint(f"step_{j}")
                l.end_run(status="SUCCESS")
            return idx

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(worker, range(5)))

        assert len(results) == 5
        # Verify that all 100 entries are written and every line is valid JSON
        lines = []
        with open(test_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    lines.append(rec)

        assert len(lines) == 100, f"Expected 100 records, got {len(lines)}"
    print("  ✓ Concurrency with advisory flock tests passed.")

def test_get_last_run_and_logs():
    print("[TEST] Testing get_last_run and get_logs query logic...")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_log = os.path.join(tmpdir, "query_runs.jsonl")
        logger = RunLogger(log_path=test_log)

        logger.start_run("sys status", session_id="sess-A")
        logger.end_run("SUCCESS")

        logger.start_run("code blueprint", session_id="sess-B")
        logger.end_run("ERROR", error_detail="Mock blueprint error")

        logger.start_run("sys last-run", session_id="sess-meta")
        logger.end_run("SUCCESS")

        # skip_meta=True should return 'code blueprint'
        last_run = logger.get_last_run(skip_meta=True)
        assert last_run["command"] == "code blueprint"
        assert last_run["status"] == "ERROR"
        assert last_run["session_id"] == "sess-B"

        # skip_meta=False should return 'sys last-run'
        meta_run = logger.get_last_run(skip_meta=False)
        assert meta_run["command"] == "sys last-run"

        # get_logs with filters
        all_logs = logger.get_logs(limit=10)
        assert len(all_logs) == 3

        error_logs = logger.get_logs(errors_only=True)
        assert len(error_logs) == 1
        assert error_logs[0]["command"] == "code blueprint"

        sess_a_logs = logger.get_logs(session_id="sess-A")
        assert len(sess_a_logs) == 1
        assert sess_a_logs[0]["session_id"] == "sess-A"
    print("  ✓ get_last_run and get_logs tests passed.")

def test_hooks():
    print("[TEST] Testing utils hooks integration...")
    captured_checkpoints = []
    captured_results = []

    set_checkpoint_hook(lambda step, pct=None, detail=None: captured_checkpoints.append((step, pct, detail)))
    set_result_hook(lambda data, success, error: captured_results.append((success, error)))

    emit_progress("TestingStep", 50, "Halfway done")
    emit_result({"k": "v"}, success=True)

    assert len(captured_checkpoints) >= 1
    assert captured_checkpoints[0][0] == "TestingStep"
    assert captured_checkpoints[0][1] == 50

    assert len(captured_results) >= 1
    assert captured_results[0][0] is True
    print("  ✓ Utils hooks integration tests passed.")

def test_scan_nestjs_endpoints_multiline():
    print("[TEST] Testing NestJS multi-line endpoints handler detection (BUG-001)...")
    from agy_tools.modules.code_tool import scan_nestjs_endpoints
    with tempfile.TemporaryDirectory() as tmpdir:
        controller_content = """
import { Controller, Get, Post, Body, HttpCode, HttpStatus } from '@nestjs/common';

@Controller('api/test')
export class TestController {
  @Post('create')
  @HttpCode(HttpStatus.OK)
  async createItem(
    @Body()
    body: {
      title: string;
      description?: string;
    },
  ) {
    if (!body) return null;
    return body;
  }
}
"""
        ctrl_path = os.path.join(tmpdir, "test.controller.ts")
        with open(ctrl_path, "w", encoding="utf-8") as f:
            f.write(controller_content)

        endpoints = scan_nestjs_endpoints(tmpdir)
        assert len(endpoints) == 1
        assert endpoints[0]["method"] == "POST"
        assert endpoints[0]["path"] == "/api/test/create"
        assert endpoints[0]["handler"] == "createItem", f"Expected createItem, got {endpoints[0]['handler']}"
    print("  ✓ NestJS multi-line endpoints test passed.")

def main():
    test_sanitization()
    test_permissions_and_rotation()
    test_concurrency()
    test_get_last_run_and_logs()
    test_hooks()
    test_scan_nestjs_endpoints_multiline()
    print("🎉 ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()

