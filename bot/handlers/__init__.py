from aiogram import Router

from .commands import router as commands_router
from .download import router as download_router
from .errors import router as errors_router
from .admin import router as admin_router


def setup_routers() -> Router:
    """
    Register all sub-routers in priority order.
    - errors_router  : must be first to catch everything
    - admin_router   : before commands so admin commands are recognised
    - commands_router: /start /help /history /stats
    - download_router: catch-all for Instagram links (last!)
    """
    root = Router()
    root.include_router(errors_router)
    root.include_router(admin_router)
    root.include_router(commands_router)
    root.include_router(download_router)
    return root


__all__ = ["setup_routers"]
