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
            plan = await workflow.execute_activity('rnd.plan',run_id, start_to_close_timeout=timedelta(minutes=4),
                retry_policy=RetryPolicy(maximum_attempts=1))
            await workflow.wait_condition(lambda:self.decision is not None, timeout=timedelta(days=7))
            if self.decision['spec_digest'] != plan['digest']:
                raise ValueError('Approval digest mismatch')
            if not self.decision['approve']:
                await workflow.execute_activity('rnd.terminal', {'run_id':run_id,'status':'REJECTED'},
                    start_to_close_timeout=timedelta(seconds=30))
                return {'status':'REJECTED'}
            for name, minutes, attempts in [('rnd.generate',8,2),('rnd.verify',6,1),('rnd.package',4,2)]:
                await workflow.execute_activity(name,run_id,start_to_close_timeout=timedelta(minutes=minutes),
                    retry_policy=RetryPolicy(maximum_attempts=attempts))
            return {'status':'READY','scope':'scaffold_only'}
        except Exception as exc:
            await workflow.execute_activity('rnd.terminal', {'run_id':run_id,'status':'FAILED','error':str(exc)},
                start_to_close_timeout=timedelta(seconds=30),retry_policy=RetryPolicy(maximum_attempts=3))
            raise
