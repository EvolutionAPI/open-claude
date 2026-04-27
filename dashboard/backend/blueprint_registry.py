from __future__ import annotations

from importlib import import_module


BLUEPRINT_MODULES = [
    "routes.overview",
    "routes.workspace",
    "routes.agents",
    "routes.routines",
    "routes.skills",
    "routes.templates_routes",
    "routes.memory",
    "routes.costs",
    "routes.config",
    "routes.integrations",
    "routes.scheduler",
    "routes.services",
    "routes.auth_routes",
    "routes.systems",
    "routes.docs",
    "routes.mempalace",
    "routes.tasks",
    "routes.triggers",
    "routes.backups",
    "routes.providers",
    "routes.settings",
    "routes.shares",
    "routes.heartbeats",
    "routes.goals",
    "routes.tickets",
    "routes.platform",
    "routes.health",
    "routes.knowledge",
    "routes.knowledge_public",
    "routes.knowledge_proxy",
    "routes.knowledge_v1",
    "routes.databases",
]

SOCIAL_BLUEPRINT_MODULES = [
    "auth.youtube",
    "auth.instagram",
    "auth.linkedin",
    "auth.twitter",
    "auth.tiktok",
    "auth.twitch",
]


def _register_modules(app, module_names):
    for module_name in module_names:
        module = import_module(module_name)
        blueprint = getattr(module, "bp", None)
        if blueprint is None:
            raise RuntimeError(f"Blueprint module {module_name} does not expose bp")
        app.register_blueprint(blueprint)


def register_blueprints(app) -> None:
    _register_modules(app, BLUEPRINT_MODULES)
    _register_modules(app, SOCIAL_BLUEPRINT_MODULES)
