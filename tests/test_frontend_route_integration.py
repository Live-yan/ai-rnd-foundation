from __future__ import annotations

from pathlib import Path

import pytest

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


def test_factory_route_uses_catalog_and_child_page(tmp_path: Path) -> None:
    target, source = _fake_target(tmp_path)

    add_frontend_route(
        target,
        "factory",
        "FactoryConsole",
        source,
        title="AI 软件开发平台",
        page_title="开发工作台",
    )

    menu = (target / "frontend/web/src/router/MenuProcessor.ts").read_text(encoding="utf-8")
    assert "AI-RND-FRONTEND-ROUTE:factory:v3" in menu
    assert 'path: "/factory"' in menu
    assert 'path: "workspace"' in menu
    assert 'name: "rnd-factory-workspace"' in menu
    assert 'component: "factory/FactoryConsole"' in menu
    assert 'title: "AI 软件开发平台"' in menu
    assert 'title: "开发工作台"' in menu
    assert "alwaysShow: true" in menu
    assert "hidden: false" in menu
    assert "isHide: false" in menu
    assert 'redirect: "/factory"' not in menu

    # Regression: a top-level leaf is handled by FastapiAdmin's handleFirstLevelLeaf,
    # whose generated parent redirects to its own full path. Keep the component on
    # the child so /factory is a catalog route and RouteTransformer chooses its child.
    parent_section = menu.split("children: [", 1)[0]
    assert 'component: "factory/FactoryConsole"' not in parent_section
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
    assert menu.count("AI-RND-FRONTEND-ROUTE:factory:v3") == 1
    assert menu.count('path: "/factory"') == 1
    assert menu.count('path: "workspace"') == 1


def test_route_injection_rejects_nested_page_segment(tmp_path: Path) -> None:
    target, source = _fake_target(tmp_path)
    with pytest.raises(ValueError, match="one non-empty path segment"):
        add_frontend_route(
            target,
            "factory",
            "FactoryConsole",
            source,
            title="AI 软件开发平台",
            page_segment="bad/nested",
        )


def test_platform_build_explicitly_enables_mixed_access_mode() -> None:
    bootstrap = (ROOT / "scripts/bootstrap.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "VITE_ACCESS_MODE=mixed" in bootstrap
    assert "AI-RND-FRONTEND-ROUTE:factory:v3" in dockerfile
    assert 'path: "workspace"' in dockerfile
    assert "AI-RND-EXTENSION:" not in bootstrap


def test_generated_product_uses_same_safe_menu_permission_pipeline() -> None:
    generator = (ROOT / "factory/generator.py").read_text(encoding="utf-8")
    delivery = (ROOT / "overlays/product/Dockerfile.delivery").read_text(encoding="utf-8")

    assert "add_frontend_route" in generator
    assert "add_route(stage" not in generator
    assert "VITE_ACCESS_MODE=mixed" in delivery
    assert "AI-RND-FRONTEND-ROUTE:business:v3" in delivery
    assert 'path: "workspace"' in delivery
