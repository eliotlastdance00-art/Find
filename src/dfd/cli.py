"""Command line entry point: ``dfd serve``, ``dfd create-user``, ``dfd models``."""

from __future__ import annotations

import argparse
import getpass
import json

from dfd.config import Settings
from dfd.domain.errors import DomainError


def _serve(args: argparse.Namespace) -> None:
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "dfd.presentation.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips=args.forwarded_allow_ips,
        log_config=None,
    )


def _create_user(args: argparse.Namespace) -> None:
    from dfd.container import build_container  # noqa: PLC0415
    from dfd.domain.entities import Role  # noqa: PLC0415

    container = build_container(Settings())
    password = args.password or getpass.getpass("Password: ")
    role = Role.ADMIN if args.admin else Role.USER
    user = container.auth.create_user(args.username, password, role)
    print(f"created {user.role.value} '{user.username}' (id {user.id})")
    container.engine.dispose()


def _models(_args: argparse.Namespace) -> None:
    from dfd.infrastructure.ml.registry import ModelRegistry  # noqa: PLC0415

    settings = Settings()
    print(json.dumps(ModelRegistry(settings.weights_dir).status(), indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dfd", description="Deepfake detection system")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web application")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--forwarded-allow-ips", default="127.0.0.1")
    serve.set_defaults(handler=_serve)

    user = commands.add_parser("create-user", help="create an account")
    user.add_argument("username")
    user.add_argument("--password")
    user.add_argument("--admin", action="store_true")
    user.set_defaults(handler=_create_user)

    models = commands.add_parser("models", help="show installed models")
    models.set_defaults(handler=_models)

    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except DomainError as error:
        parser.exit(1, f"error: {error.code}\n")


if __name__ == "__main__":
    main()
