"""CLI commands for Bloaty McBloatface."""

import argparse
import getpass
import sys

import bcrypt
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User


def create_admin(email: str, password: str | None = None) -> None:
    """Create an admin user."""
    db: Session = SessionLocal()

    try:
        # Check if email already exists
        existing = db.query(User).filter(User.email == email.lower()).first()
        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        # Get password if not provided
        if not password:
            password = getpass.getpass("Password: ")
            password_confirm = getpass.getpass("Confirm password: ")
            if password != password_confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)

        if len(password) < 8:
            print("Error: Password must be at least 8 characters.")
            sys.exit(1)

        # Create admin user
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        user = User(email=email.lower(), password_hash=password_hash, is_admin=True)
        db.add(user)
        db.commit()

        print(f"Admin user created successfully: {email}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Bloaty McBloatface CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-admin command
    create_admin_parser = subparsers.add_parser(
        "create-admin", help="Create an admin user"
    )
    create_admin_parser.add_argument(
        "--email", required=True, help="Admin email address"
    )
    create_admin_parser.add_argument(
        "--password", help="Admin password (will prompt if not provided)"
    )

    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin(args.email, args.password)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
