"""add_audio_prompt_assets

Revision ID: dded5e12729d
Revises: 98418e82939c
Create Date: 2026-05-13 22:14:51.974068

This migration creates the audio_prompt_assets and job_prompt_generation_runs tables
for the pre-generated TTS and filler audio system.

Requirements: 1.1, 1.2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dded5e12729d'
down_revision: Union[str, None] = '98418e82939c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create audio_prompt_assets table
    op.create_table(
        'audio_prompt_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_key', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='sarvam'),
        sa.Column('speaker', sa.String(length=50), nullable=False, server_default='priya'),
        sa.Column('language_code', sa.String(length=10), nullable=False, server_default='en-IN'),
        sa.Column('sample_rate', sa.Integer(), nullable=False, server_default='8000'),
        sa.Column('codec', sa.String(length=20), nullable=False, server_default='linear16'),
        sa.Column('pace', sa.Float(), nullable=False, server_default='1.2'),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('last_generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['interview_questions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_key', 'version', name='uq_template_key_version')
    )
    
    # Create indexes for audio_prompt_assets
    op.create_index('ix_audio_prompt_assets_template_key', 'audio_prompt_assets', ['template_key'])
    op.create_index('ix_audio_prompt_assets_category', 'audio_prompt_assets', ['category'])
    op.create_index('ix_audio_prompt_assets_file_hash', 'audio_prompt_assets', ['file_hash'])
    op.create_index('ix_audio_prompt_assets_status', 'audio_prompt_assets', ['status'])
    op.create_index('idx_job_question', 'audio_prompt_assets', ['job_id', 'question_id'])
    
    # Create job_prompt_generation_runs table
    op.create_table(
        'job_prompt_generation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_summary', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for job_prompt_generation_runs
    op.create_index('ix_job_prompt_generation_runs_job_id', 'job_prompt_generation_runs', ['job_id'])
    op.create_index('ix_job_prompt_generation_runs_status', 'job_prompt_generation_runs', ['status'])


def downgrade() -> None:
    # Drop job_prompt_generation_runs table and indexes
    op.drop_index('ix_job_prompt_generation_runs_status', table_name='job_prompt_generation_runs')
    op.drop_index('ix_job_prompt_generation_runs_job_id', table_name='job_prompt_generation_runs')
    op.drop_table('job_prompt_generation_runs')
    
    # Drop audio_prompt_assets table and indexes
    op.drop_index('idx_job_question', table_name='audio_prompt_assets')
    op.drop_index('ix_audio_prompt_assets_status', table_name='audio_prompt_assets')
    op.drop_index('ix_audio_prompt_assets_file_hash', table_name='audio_prompt_assets')
    op.drop_index('ix_audio_prompt_assets_category', table_name='audio_prompt_assets')
    op.drop_index('ix_audio_prompt_assets_template_key', table_name='audio_prompt_assets')
    op.drop_table('audio_prompt_assets')
