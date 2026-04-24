import argparse

from app.db.schema_management import (
    describe_database_schema_strategy,
    ensure_database_schema,
    run_alembic_upgrade,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="企业级 RAG 数据库管理入口")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade_parser = subparsers.add_parser("upgrade", help="执行 Alembic upgrade")
    upgrade_parser.add_argument("revision", nargs="?", default="head")

    subparsers.add_parser(
        "bootstrap",
        help="按当前 database_schema_strategy 执行 schema 初始化",
    )
    subparsers.add_parser(
        "describe",
        help="输出当前数据库 schema 策略",
    )

    args = parser.parse_args()
    if args.command == "upgrade":
        run_alembic_upgrade(args.revision)
        return
    if args.command == "bootstrap":
        ensure_database_schema()
        return

    strategy, label = describe_database_schema_strategy()
    print(f"{strategy}\t{label}")


if __name__ == "__main__":
    main()
