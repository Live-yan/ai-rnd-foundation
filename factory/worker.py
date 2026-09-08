import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from .activities import Activities
from .config import get_settings
from .database import Database
from .dispatcher import dispatch_forever
from .workflows import GenerateProductWorkflow


async def main():
    settings = get_settings(); settings.ensure_paths()
    db = Database(settings.database_url)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    activities = Activities(db,settings)
    worker = Worker(client, task_queue=settings.task_queue, workflows=[GenerateProductWorkflow],
        activities=[activities.plan_activity,activities.generate_activity,activities.verify_activity,
                    activities.package_activity,activities.terminal], max_concurrent_activities=2,
        max_concurrent_workflow_tasks=4)
    async with worker:
        await dispatch_forever(db,client,settings.task_queue)


if __name__ == '__main__':
    asyncio.run(main())
