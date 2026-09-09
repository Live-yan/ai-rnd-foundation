from __future__ import annotations

from pathlib import Path

from scripts.bootstrap import add_frontend_route

ROOT = Path(__file__).resolve().parents[1]


def _fake_target(tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / "FastapiAdmin"
    menu = target / "frontend/web/src/router/MenuProcessor.ts"
    menu.parent.mkdir(parents=True)
    menu.write_text(
        'import type { AppRouteRecord } from "@/types/router";\n'
        'export const builtinFrontendRoutes: AppRouteRecord[] = [];\n',
        encoding="utf-8",
    )
    source = tmp_path / "Console.vue"
    source.write_text("<template><div>console</div></template>\n", encoding="utf-8")
    return target, source


def test_factory_route_is_injected_into_mixed_menu_extension_point(tmp_path: Path) -> None:
    target, source = _fake_target(tmp_path)

    add_frontend_route(
        target,
        "factory",
        "FactoryConsole",
        source,
        title="AI 软件开发平台",
    )

    menu = (target / "frontend/web/src/router/MenuProcessor.ts").read_text(encoding="utf-8")
    assert "AI-RND-FRONTEND-ROUTE:factory:v2" in menu
    assert 'path: "/factory"' in menu
    assert 'component: "factory/FactoryConsole"' in menu
    assert 'title: "AI 软件开发平台"' in menu
    assert "hidden: false" in menu
    assert "isHide: false" in menu
    assert (target / "frontend/web/src/views/factory/FactoryConsole.vue").is_file()


def test_route_injection_is_idempotent(tmp_path: Path) -> None:
    target, source = _fake_target(tmp_path)
    for _ in range(2):
        add_frontend_route(
            target,
            "factory",
            "FactoryConsole",
            source,
            title="AI 软件开发平台",
        )

    menu = (target / "frontend/web/src/router/MenuProcessor.ts").read_text(encoding="utf-8")
    assert menu.count("AI-RND-FRONTEND-ROUTE:factory:v2") == 1
    assert menu.count('path: "/factory"') == 1


def test_platform_build_explicitly_enables_mixed_access_mode() -> None:
    bootstrap = (ROOT / "scripts/bootstrap.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "VITE_ACCESS_MODE=mixed" in bootstrap
    assert "AI-RND-FRONTEND-ROUTE:factory:v2" in dockerfile
    assert "router.addRoute" not in bootstrap


def test_generated_product_uses_same_menu_permission_pipeline() -> None:
    generator = (ROOT / "factory/generator.py").read_text(encoding="utf-8")
    delivery = (ROOT / "overlays/product/Dockerfile.delivery").read_text(encoding="utf-8")

    assert "add_frontend_route" in generator
    assert "add_route(stage" not in generator
    assert "VITE_ACCESS_MODE=mixed" in delivery
    assert "AI-RND-FRONTEND-ROUTE:business:v2" in delivery
