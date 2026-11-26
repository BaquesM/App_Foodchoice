"""rename default test accounts to Curie, Einstein, Newton

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

RENAMES = [
    # (old_username, old_display, old_email, new_username, new_display, new_email)
    ("marion", "Marion", "marion@test.fr", "curie", "Curie", "curie@test.fr"),
    ("lisa", "Lisa", "lisa@test.fr", "einstein", "Einstein", "einstein@test.fr"),
    ("odile", "Odile", "odile@test.fr", "newton", "Newton", "newton@test.fr"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for old_user, old_name, old_email, new_user, new_name, new_email in RENAMES:
        row = bind.execute(
            sa.text(
                "SELECT id FROM user_accounts "
                "WHERE username = :old_user AND email = :old_email"
            ),
            {"old_user": old_user, "old_email": old_email},
        ).fetchone()
        if not row:
            continue
        account_id = row[0]

        bind.execute(
            sa.text(
                "UPDATE user_accounts "
                "SET username = :new_user, display_name = :new_name, email = :new_email "
                "WHERE id = :account_id"
            ),
            {
                "new_user": new_user,
                "new_name": new_name,
                "new_email": new_email,
                "account_id": account_id,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE household_profiles "
                "SET name = :new_name "
                "WHERE account_id = :account_id AND name = :old_name"
            ),
            {
                "new_name": new_name,
                "account_id": account_id,
                "old_name": old_name,
            },
        )
        if old_user == "odile":
            bind.execute(
                sa.text(
                    "UPDATE recipes SET title = :new_title "
                    "WHERE account_id = :account_id AND title = :old_title"
                ),
                {
                    "new_title": "Ratatouille de Newton",
                    "account_id": account_id,
                    "old_title": "Ratatouille d'Odile",
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    for old_user, old_name, old_email, new_user, new_name, new_email in RENAMES:
        row = bind.execute(
            sa.text(
                "SELECT id FROM user_accounts "
                "WHERE username = :new_user AND email = :new_email"
            ),
            {"new_user": new_user, "new_email": new_email},
        ).fetchone()
        if not row:
            continue
        account_id = row[0]

        bind.execute(
            sa.text(
                "UPDATE user_accounts "
                "SET username = :old_user, display_name = :old_name, email = :old_email "
                "WHERE id = :account_id"
            ),
            {
                "old_user": old_user,
                "old_name": old_name,
                "old_email": old_email,
                "account_id": account_id,
            },
        )
        bind.execute(
            sa.text(
                "UPDATE household_profiles "
                "SET name = :old_name "
                "WHERE account_id = :account_id AND name = :new_name"
            ),
            {
                "old_name": old_name,
                "account_id": account_id,
                "new_name": new_name,
            },
        )
        if old_user == "odile":
            bind.execute(
                sa.text(
                    "UPDATE recipes SET title = :old_title "
                    "WHERE account_id = :account_id AND title = :new_title"
                ),
                {
                    "old_title": "Ratatouille d'Odile",
                    "account_id": account_id,
                    "new_title": "Ratatouille de Newton",
                },
            )
