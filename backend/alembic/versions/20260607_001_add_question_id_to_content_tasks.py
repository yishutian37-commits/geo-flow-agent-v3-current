"""add question_id to content_tasks

Revision ID: 20260607_001
Revises:
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa


revision = "20260607_001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _foreign_key_exists(inspector, table_name: str, constrained_column: str, referred_table: str) -> bool:
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get("referred_table") != referred_table:
            continue
        if constrained_column in foreign_key.get("constrained_columns", []):
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "content_tasks"):
        return

    if not _column_exists(inspector, "content_tasks", "question_id"):
        with op.batch_alter_table("content_tasks") as batch_op:
            batch_op.add_column(sa.Column("question_id", sa.String(length=36), nullable=True))

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "questions") and not _foreign_key_exists(
        inspector,
        "content_tasks",
        "question_id",
        "questions",
    ):
        with op.batch_alter_table("content_tasks") as batch_op:
            batch_op.create_foreign_key(
                "fk_content_tasks_question_id_questions",
                "questions",
                ["question_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "content_tasks"):
        return

    if _foreign_key_exists(inspector, "content_tasks", "question_id", "questions"):
        with op.batch_alter_table("content_tasks") as batch_op:
            batch_op.drop_constraint("fk_content_tasks_question_id_questions", type_="foreignkey")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "content_tasks", "question_id"):
        with op.batch_alter_table("content_tasks") as batch_op:
            batch_op.drop_column("question_id")
