"""add player_injury_reports and player_news

Revision ID: b2d4f6a8c1e3
Revises: 7f7dc8d19890
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2d4f6a8c1e3'
down_revision = '7f7dc8d19890'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_injury_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('season', sa.String(length=4), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('report_status', sa.String(length=40), nullable=True),
        sa.Column('report_primary_injury', sa.String(length=80), nullable=True),
        sa.Column('report_secondary_injury', sa.String(length=80), nullable=True),
        sa.Column('practice_status', sa.String(length=80), nullable=True),
        sa.Column('practice_primary_injury', sa.String(length=80), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['players.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'source', 'season', 'week', name='uq_player_injury_report'),
    )
    with op.batch_alter_table('player_injury_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_player_injury_reports_player_id'), ['player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_injury_reports_source'), ['source'], unique=False)
        batch_op.create_index('ix_player_injury_report_latest', ['player_id', 'source', 'season', 'week'], unique=False)

    op.create_table(
        'player_news',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('headline', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=600), nullable=False),
        sa.Column('image_url', sa.String(length=600), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['players.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'url', 'player_id', name='uq_player_news_source_url_player'),
    )
    with op.batch_alter_table('player_news', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_player_news_player_id'), ['player_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_news_source'), ['source'], unique=False)
        batch_op.create_index('ix_player_news_player_published', ['player_id', 'published_at'], unique=False)


def downgrade():
    with op.batch_alter_table('player_news', schema=None) as batch_op:
        batch_op.drop_index('ix_player_news_player_published')
        batch_op.drop_index(batch_op.f('ix_player_news_source'))
        batch_op.drop_index(batch_op.f('ix_player_news_player_id'))
    op.drop_table('player_news')

    with op.batch_alter_table('player_injury_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_player_injury_report_latest')
        batch_op.drop_index(batch_op.f('ix_player_injury_reports_source'))
        batch_op.drop_index(batch_op.f('ix_player_injury_reports_player_id'))
    op.drop_table('player_injury_reports')
