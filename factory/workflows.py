"""Deterministic Temporal workflow. All IO belongs to activities, not this module."""
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class GenerateProductWorkflow:
    def __init__(self):
        self.decision: dict | None = None

    @workflow.signal
    def decide(self, value: dict) -> None:
        if self.decision is None:
            self.decision = value

    @workflow.run
    async def run(self, run_id: str) -> dict:
        try:
            if not workflow.patched("rnd-workbench-v2"):
                return await self._legacy(run_id)
            context = await workflow.execute_activity(
                "rnd.context", run_id, start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            plan_result = await workflow.execute_activity(
                "rnd.plan", {"run_id": run_id, "context": context.get("context", "")},
                start_to_close_timeout=timedelta(minutes=8), retry_policy=RetryPolicy(maximum_attempts=1),
            )
            await workflow.execute_activity(
                "rnd.analysis_pack", run_id, start_to_close_timeout=timedelta(minutes=6),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            await workflow.wait_condition(lambda: self.decision is not None, timeout=timedelta(days=7))
            if self.decision["spec_digest"] != plan_result["digest"]:
                raise ValueError("Approval digest mismatch")
            if not self.decision["approve"]:
                await workflow.execute_activity(
                    "rnd.terminal", {"run_id": run_id, "status": "REJECTED"},
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return {"status": "REJECTED"}
            verify_minutes = 14 if workflow.patched("rnd-fullstack-acceptance-v1") else 8
            for name, minutes, attempts in [
                ("rnd.generate", 8, 2), ("rnd.verify", verify_minutes, 1), ("rnd.package", 4, 2), ("rnd.coder", 6, 1),
            ]:
                await workflow.execute_activity(
                    name, run_id, start_to_close_timeout=timedelta(minutes=minutes),
                    retry_policy=RetryPolicy(maximum_attempts=attempts),
                )
            await workflow.execute_activity(
                "rnd.ready", run_id, start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            return {"status": "READY", "scope": "scaffold_with_toolchain"}
        except Exception as exc:
            await workflow.execute_activity(
                "rnd.terminal", {"run_id": run_id, "status": "FAILED", "error": str(exc)},
                start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise

    async def _legacy(self, run_id: str) -> dict:
        """Replay the pre-workbench command sequence without introducing new activities."""
        plan = await workflow.execute_activity(
            "rnd.plan", run_id, start_to_close_timeout=timedelta(minutes=4),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        await workflow.wait_condition(lambda: self.decision is not None, timeout=timedelta(days=7))
        if self.decision["spec_digest"] != plan["digest"]:
            raise ValueError("Approval digest mismatch")
        if not self.decision["approve"]:
            await workflow.execute_activity("rnd.terminal", {"run_id": run_id, "status": "REJECTED"},
                                            start_to_close_timeout=timedelta(seconds=30))
            return {"status": "REJECTED"}
        for name, minutes, attempts in [("rnd.generate", 8, 2), ("rnd.verify", 6, 1), ("rnd.package", 4, 2)]:
            await workflow.execute_activity(name, run_id, start_to_close_timeout=timedelta(minutes=minutes),
                                            retry_policy=RetryPolicy(maximum_attempts=attempts))
        return {"status": "READY", "scope": "scaffold_only"}
