#!/usr/bin/env python3
"""Manage queue administrator and terminal accounts."""

import argparse
import getpass
import os
import sys
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker


ENV_FILE = Path(__file__).resolve().with_name("main.env")
Base = declarative_base()


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    status = Column(String, nullable=False)


def load_database_url() -> str:
    if not ENV_FILE.is_file():
        raise RuntimeError(f"Не найден файл настроек: {ENV_FILE}")

    load_dotenv(ENV_FILE, override=True)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(f"В {ENV_FILE} отсутствует DATABASE_URL")
    return database_url


def prompt_password() -> str:
    password = getpass.getpass("Новый пароль: ")
    if len(password) < 8:
        raise ValueError("Пароль должен содержать не менее 8 символов")
    if password != getpass.getpass("Повторите пароль: "):
        raise ValueError("Пароли не совпадают")
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Управление администраторами и терминалами электронной очереди."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add_parser = commands.add_parser("add", help="создать учётную запись")
    add_parser.add_argument("login", help="логин")
    add_parser.add_argument("status", choices=("admin", "terminal"), help="роль")

    delete_parser = commands.add_parser("delete", help="удалить учётную запись")
    delete_parser.add_argument("login", help="логин")

    commands.add_parser("show", help="показать учётные записи")

    change_parser = commands.add_parser("change", help="изменить учётную запись")
    change_parser.add_argument("login", help="логин")
    change_parser.add_argument(
        "--password", action="store_true", help="запросить и изменить пароль"
    )
    change_parser.add_argument("--status", choices=("admin", "terminal"), help="новая роль")
    return parser


def run_command(args: argparse.Namespace) -> None:
    engine = create_engine(load_database_url())
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        if args.command == "add":
            password = prompt_password()
            db.add(
                Admin(
                    login=args.login,
                    password=hash_password(password),
                    status=args.status,
                )
            )
            db.commit()
            print(f"Учётная запись '{args.login}' создана.")

        elif args.command == "delete":
            account = db.query(Admin).filter(Admin.login == args.login).first()
            if not account:
                raise ValueError(f"Учётная запись '{args.login}' не найдена")
            db.delete(account)
            db.commit()
            print(f"Учётная запись '{args.login}' удалена.")

        elif args.command == "show":
            accounts = db.query(Admin).order_by(Admin.login).all()
            if not accounts:
                print("Учётных записей нет.")
                return
            print(f"{'ЛОГИН':<24} РОЛЬ")
            print("-" * 40)
            for account in accounts:
                print(f"{account.login:<24} {account.status}")

        elif args.command == "change":
            if not args.password and not args.status:
                raise ValueError("Укажите --password и/или --status")
            account = db.query(Admin).filter(Admin.login == args.login).first()
            if not account:
                raise ValueError(f"Учётная запись '{args.login}' не найдена")
            if args.password:
                account.password = hash_password(prompt_password())
            if args.status:
                account.status = args.status
            db.commit()
            print(f"Учётная запись '{args.login}' обновлена.")


def main() -> int:
    try:
        run_command(build_parser().parse_args())
        return 0
    except IntegrityError:
        print("Ошибка: такой логин уже существует.", file=sys.stderr)
    except (RuntimeError, ValueError, SQLAlchemyError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
