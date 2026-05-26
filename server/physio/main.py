from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

from aiohttp import web


SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

try:
    from env_loader import load_server_env

    load_server_env()
except Exception:
    pass

from physio.pages import check_page_html, dashboard_html
from physio.service import PhysioService, create_physio_service_from_env


def _disabled_status() -> dict[str, Any]:
    return {
        "ok": False,
        "enabled": False,
        "running": False,
        "error": "physio ring service is disabled or failed to initialize",
        "state": {},
        "collector": {"streams": {}, "warnings": ["Physio service is not available."]},
        "sample_storage": None,
        "sample_file": {},
        "formal_sample_count": 0,
    }


def _service(request: web.Request) -> Optional[PhysioService]:
    return request.app.get("physio_service")


async def root_handler(request: web.Request) -> web.Response:
    raise web.HTTPFound("/physio/check")


async def check_handler(request: web.Request) -> web.Response:
    return web.Response(text=check_page_html(), content_type="text/html")


async def dashboard_handler(request: web.Request) -> web.Response:
    return web.Response(text=dashboard_html(), content_type="text/html")


async def status_handler(request: web.Request) -> web.Response:
    service = _service(request)
    if service is None:
        return web.json_response(_disabled_status())
    try:
        return web.json_response(service.status_payload())
    except Exception as exc:
        return web.json_response(
            {
                "ok": False,
                "enabled": True,
                "running": False,
                "error": str(exc),
                "state": {},
                "collector": {"streams": {}, "warnings": [str(exc)]},
                "sample_storage": getattr(service, "sample_storage", None),
                "sample_file": {},
                "formal_sample_count": 0,
            },
            status=500,
        )


async def export_handler(request: web.Request) -> web.Response:
    service = _service(request)
    if service is None:
        return web.json_response({"ok": False, "msg": "physio ring service is not available"}, status=503)
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        result = service.export_data(
            subject_id=data.get("subject_id"),
            run_id=data.get("run_id"),
            trial_id=data.get("trial_id"),
        )
        return web.json_response({"ok": True, **result})
    except Exception as exc:
        return web.json_response({"ok": False, "msg": str(exc)}, status=500)


async def cleanup_app(app: web.Application) -> None:
    service = app.get("physio_service")
    if service is None:
        return
    service.stop()


def create_app(start_service: bool = True) -> web.Application:
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/physio/check", check_handler)
    app.router.add_get("/physio/dashboard", dashboard_handler)
    app.router.add_get("/api/physio/status", status_handler)
    app.router.add_post("/api/physio/export", export_handler)
    app.on_cleanup.append(cleanup_app)

    service = create_physio_service_from_env()
    if service is not None and start_service:
        try:
            service.start()
        except Exception as exc:
            service.error = str(exc)
            service.running = False
    app["physio_service"] = service
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone physio ring service")
    parser.add_argument("--host", default=os.environ.get("PHYSIO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PHYSIO_PORT", "8081")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app(start_service=True)
    service = app.get("physio_service")
    if service is None:
        print("Physio service disabled. Serving check page with disabled status.")
    else:
        print(f"Physio service running on http://{args.host}:{args.port}/physio/check")
        print(f"Vendor root: {service.vendor_root}")
        print(f"Database: {service.db_path}")
        print(f"Raw samples: {service.raw_dir}")
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
