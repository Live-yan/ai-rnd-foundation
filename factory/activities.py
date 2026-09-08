from __future__ import annotations
import asyncio
from temporalio import activity
from .config import Settings
from .database import Database, Run, Event
from .generator import generate_product
from .packaging import package_product
from .planner import plan
from .schemas import ProjectSpec
from .security import run_path, redact
from .validation import verify_product


class Activities:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def get(self, run_id: str) -> dict:
        with self.db.session() as session:
            row = session.get(Run, run_id)
            if not row:
                raise ValueError('Unknown run')
            return {'request':row.request, 'spec':row.spec, 'digest':row.spec_digest,
                    'checks':row.checks, 'status':row.status}

    def status(self, run_id: str, value: str, message: str) -> None:
        with self.db.session() as session:
            row = session.get(Run, run_id)
            row.status = value
            session.add(Event(run_id=run_id, message=message))

    @activity.defn(name='rnd.plan')
    async def plan_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        if info['spec']:
            return {'digest':info['digest']}
        self.status(run_id, 'PLANNING', '开始 LangGraph 规格规划；最多两次结构化生成尝试。')
        req = info['request']
        requirement = '\n\n'.join(m['content'] for m in req['messages'])
        spec = await plan(requirement, req['provider'], req['use_serena'], self.settings)
        with self.db.session() as session:
            row = session.get(Run, run_id)
            row.spec = spec.model_dump(); row.spec_digest = spec.digest(); row.status = 'AWAITING_APPROVAL'
            session.add(Event(run_id=run_id, message='规格已保存。等待你确认数据结构和未实现项。'))
        return {'digest':spec.digest()}

    @activity.defn(name='rnd.generate')
    async def generate_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        self.status(run_id, 'GENERATING', '从固定 FastapiAdmin 模板生成业务扩展、迁移、Vue 页面与架构包。')
        product = run_path(self.settings.data_dir, run_id) / 'product'
        return await asyncio.to_thread(generate_product, ProjectSpec.model_validate(info['spec']),
                                       self.settings.upstream_dir, product,
                                       diagrams_required=self.settings.diagrams_required)

    @activity.defn(name='rnd.verify')
    async def verify_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        self.status(run_id, 'VERIFYING', '执行源代码、业务契约与 OpenSpec 检查；完整全栈部署另行验收。')
        report = await asyncio.to_thread(verify_product, run_path(self.settings.data_dir,run_id) / 'product',
                                         run_id, info['request'], self.settings)
        with self.db.session() as session:
            session.get(Run,run_id).checks = report
        return {'verified':'scaffold_only'}

    @activity.defn(name='rnd.package')
    async def package_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        if not info['checks']:
            raise ValueError('Cannot package an unverified product')
        self.status(run_id,'PACKAGING','正在排除密钥与缓存，并计算交付包文件哈希。')
        base = run_path(self.settings.data_dir,run_id)
        sha = await asyncio.to_thread(package_product,base / 'product',base / 'product.zip',info['checks'])
        with self.db.session() as session:
            row = session.get(Run,run_id)
            row.artifact = str((base / 'product.zip').relative_to(self.settings.data_dir.resolve()))
            row.artifact_sha256 = sha; row.status = 'READY'
            session.add(Event(run_id=run_id,message='源码骨架可下载。请按 quality.json 完成未执行的部署与业务验收。'))
        return {'sha256':sha}

    @activity.defn(name='rnd.terminal')
    async def terminal(self, value: dict) -> None:
        run_id = value['run_id']
        message = redact(value.get('error',''), [self.settings.model_api_key,self.settings.cube_api_key,
                         self.settings.coder_token,self.settings.serena_token])
        status = value['status']
        with self.db.session() as session:
            row = session.get(Run,run_id)
            if row.status == 'READY':
                return
            row.status = status; row.error = message or None
            session.add(Event(run_id=run_id,level='error' if status=='FAILED' else 'info',
                              message=f'任务结束：{status}。{message}'))
