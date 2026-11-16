"""value_snapshots: drop redundant indexes, keep ix_value_snapshots_config

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c1e3
Create Date: 2026-11-16 00:00:00.000000

"""
from alembic import op


revision = 'c3e5a7b9d1f2'
down_revision = 'b2d4f6a8c1e3'
branch_labels = None
depends_on = None

_DROPPED = {
    'ix_value_snapshots_player_id': '(player_id)',
    'ix_value_snapshots_source_key': '(source_key)',
    'ix_value_snapshots_pick_key': '(pick_key)',
    'ix_value_snapshots_latest': '(player_id, source_key, league_format, metric_key, as_of)',
}
_CONFIG_COLS = '(player_id, source_key, league_format, config_key, metric_key, as_of)'


def _postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade():
    if _postgres():
        with op.get_context().autocommit_block():
            for name in (*_DROPPED, 'ix_value_snapshots_config_key'):
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
            op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_value_snapshots_config '
                       f'ON value_snapshots {_CONFIG_COLS}')
    else:
        for name in (*_DROPPED, 'ix_value_snapshots_config_key'):
            op.execute(f'DROP INDEX IF EXISTS {name}')
        op.execute(f'CREATE INDEX IF NOT EXISTS ix_value_snapshots_config ON value_snapshots {_CONFIG_COLS}')


def downgrade():
    concurrently = ' CONCURRENTLY' if _postgres() else ''
    stmts = [f'CREATE INDEX{concurrently} IF NOT EXISTS {name} ON value_snapshots {cols}'
             for name, cols in _DROPPED.items()]
    if _postgres():
        with op.get_context().autocommit_block():
            for s in stmts:
                op.execute(s)
    else:
        for s in stmts:
            op.execute(s)
