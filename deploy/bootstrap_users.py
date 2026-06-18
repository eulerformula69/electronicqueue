"""Create the initial queue accounts without changing existing passwords."""

import os
import sys
from pathlib import Path

import bcrypt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import Admin, SessionLocal


def create_account(login: str, password: str, status: str) -> bool:
    with SessionLocal() as db:
        if db.query(Admin).filter(Admin.login == login).first():
            return False

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        db.add(Admin(login=login, password=password_hash, status=status))
        db.commit()
        return True


def main() -> None:
    accounts = (
        ("admin", os.environ["QUEUE_ADMIN_PASSWORD"], "admin"),
        ("terminal", os.environ["QUEUE_TERMINAL_PASSWORD"], "terminal"),
    )
    for login, password, status in accounts:
        result = "создана" if create_account(login, password, status) else "уже существует"
        print(f"Учётная запись {login}: {result}")


if __name__ == "__main__":
    main()
