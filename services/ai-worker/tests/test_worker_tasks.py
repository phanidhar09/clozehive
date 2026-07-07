"""Tests for ARQ task functions: status transitions, retry semantics, metrics.

The contract under test (see worker.py docstring): every job moves
accepted → processing → completed | failed in the ai_requests table, and a
failure is only recorded once ARQ has exhausted its retries.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import app.worker as worker

REQ_ID = str(uuid4())


class TestAnalyzeImageTask:
    async def test_success_marks_processing_then_completes(
        self, fake_db, fake_agent, recorded_metrics
    ):
        fake_agent.analyze_image.return_value = {"category": "tops"}

        result = await worker.analyze_image_task({"job_try": 1}, REQ_ID, "/tmp/img.jpg")

        assert result == {"analysis": {"category": "tops"}}
        fake_db.mark_processing.assert_awaited_once()
        fake_db.complete_request.assert_awaited_once()
        fake_db.fail_request.assert_not_awaited()
        assert recorded_metrics == [("analyze_image", "completed", 1.5)]

    async def test_failure_before_last_try_reraises_without_recording(
        self, fake_db, fake_agent, recorded_metrics
    ):
        fake_agent.analyze_image.side_effect = RuntimeError("agent down")

        with pytest.raises(RuntimeError):
            await worker.analyze_image_task({"job_try": 1}, REQ_ID, "/tmp/img.jpg")

        # Not the final attempt: ARQ will retry, so no terminal failure yet.
        fake_db.fail_request.assert_not_awaited()
        assert recorded_metrics == []

    async def test_failure_on_last_try_records_failed(
        self, fake_db, fake_agent, recorded_metrics
    ):
        fake_agent.analyze_image.side_effect = RuntimeError("agent down")

        with pytest.raises(RuntimeError):
            await worker.analyze_image_task(
                {"job_try": worker.settings.max_attempts}, REQ_ID, "/tmp/img.jpg"
            )

        fake_db.fail_request.assert_awaited_once()
        assert fake_db.fail_request.await_args.args[1] == "agent down"
        assert recorded_metrics == [("analyze_image", "failed", 1.5)]


class TestGenerateOutfitTask:
    async def test_success_persists_agent_result(self, fake_db, fake_agent, recorded_metrics):
        fake_agent.generate_outfit.return_value = {"outfit": ["shirt", "jeans"]}

        result = await worker.generate_outfit_task({"job_try": 1}, REQ_ID, {"occasion": "casual"})

        assert result == {"outfit": ["shirt", "jeans"]}
        fake_agent.generate_outfit.assert_awaited_once_with({"occasion": "casual"})
        fake_db.complete_request.assert_awaited_once()
        assert recorded_metrics == [("generate_outfit", "completed", 1.5)]

    async def test_failure_on_last_try_records_failed(self, fake_db, fake_agent, recorded_metrics):
        fake_agent.generate_outfit.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await worker.generate_outfit_task(
                {"job_try": worker.settings.max_attempts}, REQ_ID, {}
            )

        fake_db.fail_request.assert_awaited_once()
        assert recorded_metrics == [("generate_outfit", "failed", 1.5)]


class TestFailOnLastTry:
    async def test_missing_job_try_defaults_to_first_attempt(self, fake_db):
        await worker._fail_on_last_try({}, uuid4(), RuntimeError("x"))
        # job_try defaults to 1 < max_attempts (5): no terminal failure recorded.
        fake_db.fail_request.assert_not_awaited()

    async def test_at_max_attempts_records_failure(self, fake_db):
        rid = uuid4()
        await worker._fail_on_last_try(
            {"job_try": worker.settings.max_attempts}, rid, RuntimeError("x")
        )
        fake_db.fail_request.assert_awaited_once()
        assert fake_db.fail_request.await_args.args[0] == rid


class TestWorkerSettings:
    def test_all_tasks_registered(self):
        names = {f.__name__ for f in worker.WorkerSettings.functions}
        assert names == {
            "analyze_image_task",
            "generate_outfit_task",
        }

    def test_max_tries_matches_settings(self):
        assert worker.WorkerSettings.max_tries == worker.settings.max_attempts
