"""Transactional outbox: close the PostgreSQL commit / Temporal start gap.
Only a single local dispatcher is needed for v0.1; SKIP LOCKED also prevents duplicate claims.
"""
import asyncio
from sqlalchemy import select
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.common import WorkflowIDReusePolicy
from .database import Database, Outbox, Run
from .security import redact


async def dispatch_once(db: Database, client: Client, task_queue: str) -> bool:
    # Hold only one small outbox transaction across a bounded RPC. No model or generation IO here.
    with db.session() as session:
        event = session.scalar(select(Outbox).where(Outbox.sent.is_(False)).order_by(Outbox.attempts, Outbox.id)
                               .with_for_update(skip_locked=True).limit(1))
        if event is None:
            return False
        run = session.get(Run,event.run_id)
        event.attempts += 1
        try:
            if event.kind == 'start':
                try:
                    await asyncio.wait_for(client.start_workflow('GenerateProductWorkflow', run.id,
                        id='rnd-' + run.id, task_queue=task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE), timeout=15)
                except WorkflowAlreadyStartedError:
                    pass  # Retry after a lost acknowledgement, not a duplicate execution.
            elif run.status in {'READY','FAILED','REJECTED','CANCELLED'}:
                event.sent = True
                event.error = 'Skipped signal for terminal run'
                return True
            else:
                await asyncio.wait_for(client.get_workflow_handle('rnd-' + run.id).signal('decide',run.decision), timeout=15)
            event.sent = True; event.error = None
        except Exception as exc:
            event.error = redact(str(exc))
            # Not marked sent: dispatcher will retry after a delay. Inspect rnd_outbox.error.
        return True


async def dispatch_forever(db: Database, client: Client, task_queue: str):
    while True:
        try:
            had_item = await dispatch_once(db,client,task_queue)
            await asyncio.sleep(2 if had_item else 1)
        except Exception:
            await asyncio.sleep(5)
