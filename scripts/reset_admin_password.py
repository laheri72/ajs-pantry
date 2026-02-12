import sys
from pathlib import Path
import argparse

from werkzeug.security import generate_password_hash


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    parser = argparse.ArgumentParser(description="Reset the single admin user's password.")
    parser.add_argument("--username", default="Administrator", help="Admin username (default: Administrator)")
    parser.add_argument("--password", required=True, help="New password to set")
    parser.add_argument(
        "--force-change",
        action="store_true",
        help="Require password change on next login (sets is_first_login=True).",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    from app import app, db  # noqa: WPS433
    from models import User  # noqa: WPS433

    with app.app_context():
        admin = User.query.filter_by(username=args.username, role="admin").first()
        if not admin:
            raise SystemExit(f"Admin user not found: username={args.username!r}")

        admin.password_hash = generate_password_hash(args.password)
        admin.is_first_login = bool(args.force_change)

        db.session.commit()

        print("OK: admin password updated")
        print(f"username: {admin.username}")
        print(f"force_change_next_login: {bool(args.force_change)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
