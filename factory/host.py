"""Actual FastapiAdmin host integration, not a replacement backend masquerading as the template."""
from fastapi import Security
from .api import create_router
from .config import get_settings
from .database import Database


def create_app():
    # scripts/bootstrap.py assembles an unmodified pinned upstream plus additive Vue/entrypoint overlays.
    from app import create_app as create_upstream_app
    from app.core.dependencies import AuthPermission
    from app.common.response import SuccessResponse
    from app.core.router_class import OperationLogRoute, _write_operation_log_async
    from app.utils.ip_local_util import get_client_ip
    from app.config.setting import settings as host_settings
    from .privacy import metadata_only_route, secure_host_logging
    settings = get_settings()
    settings.ensure_paths()
    db = Database(settings.database_url)
    app = create_upstream_app()
    secure_host_logging()
    audit_route = metadata_only_route(OperationLogRoute, _write_operation_log_async, get_client_ip, host_settings.OPERATION_RECORD_METHOD)

    async def actor(auth=Security(AuthPermission(["module_factory:workbench:query"]))) -> str:
        return str(auth.user.id)

    app.include_router(create_router(db, settings, actor, route_class=audit_route, response_factory=SuccessResponse))
    return app
