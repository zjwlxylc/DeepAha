"""Direct WMA intake staging, raw provenance and internal review only."""

from alembic import op

revision = "20260907_0035"
down_revision = "20260901_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE investigation_tasks (
            task_id UUID NOT NULL,
            source_id UUID NOT NULL,
            endpoint_id UUID NOT NULL,
            created_by UUID NOT NULL,
            request_key_hash VARCHAR(64) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            request JSONB NOT NULL,
            source_snapshot JSONB NOT NULL,
            contract JSONB NOT NULL,
            contract_hash VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            execution JSONB NOT NULL,
            runtime_id VARCHAR(256),
            remote_session_id VARCHAR(256),
            lease_owner UUID,
            deadline_at TIMESTAMP WITH TIME ZONE,
            lease_until TIMESTAMP WITH TIME ZONE,
            error_code VARCHAR(128),
            delivery_hash VARCHAR(64),
            delivery JSONB,
            result_objects JSONB NOT NULL,
            review JSONB,
            reviewer_id UUID,
            review_key_hash VARCHAR(64),
            review_hash VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT pk_investigation_tasks PRIMARY KEY (task_id),
            CONSTRAINT uq_investigation_tasks_created_by UNIQUE (created_by, request_key_hash),
            CONSTRAINT fk_investigation_tasks_endpoint_id_source_endpoints FOREIGN KEY(endpoint_id,
            source_id) REFERENCES source_endpoints (endpoint_id, source_id),
            CONSTRAINT ck_investigation_tasks_status_values CHECK (status in ('QUEUED', 'CREATING',
            'PREPARING', 'INVESTIGATING', 'COLLECTING', 'PENDING_REVIEW', 'APPROVED', 'REJECTED',
            'FAILED_PREPARATION', 'EXECUTION_UNCERTAIN', 'COLLECTION_RETRYABLE',
            'FAILED_VALIDATION', 'EXPIRED')),
            CONSTRAINT ck_investigation_tasks_delivery_required CHECK (status not in
            ('PENDING_REVIEW', 'APPROVED', 'REJECTED') or delivery_hash is not null),
            CONSTRAINT ck_investigation_tasks_reviewer_required CHECK (status not in ('APPROVED',
            'REJECTED') or reviewer_id is not null),
            CONSTRAINT fk_investigation_tasks_created_by_reviewer_accounts FOREIGN KEY(created_by)
            REFERENCES reviewer_accounts (reviewer_id),
            CONSTRAINT fk_investigation_tasks_reviewer_id_reviewer_accounts FOREIGN KEY(reviewer_id)
            REFERENCES reviewer_accounts (reviewer_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE investigation_materials (
            task_id UUID NOT NULL,
            material_id VARCHAR(256) NOT NULL,
            raw_artifact_id UUID NOT NULL,
            metadata_snapshot JSONB NOT NULL,
            CONSTRAINT pk_investigation_materials PRIMARY KEY (task_id, material_id),
            CONSTRAINT fk_investigation_materials_task_id_investigation_tasks FOREIGN KEY(task_id)
            REFERENCES investigation_tasks (task_id),
            CONSTRAINT fk_investigation_materials_raw_artifact_id_raw_artifacts FOREIGN
            KEY(raw_artifact_id) REFERENCES raw_artifacts (artifact_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE investigation_events (
            task_id UUID NOT NULL,
            sequence INTEGER NOT NULL,
            status VARCHAR(32) NOT NULL,
            error_code VARCHAR(128),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT pk_investigation_events PRIMARY KEY (task_id, sequence),
            CONSTRAINT fk_investigation_events_task_id_investigation_tasks FOREIGN KEY(task_id)
            REFERENCES investigation_tasks (task_id)
        )
        """
    )
    _create_immutability_guards()


def _create_immutability_guards() -> None:
    op.execute("""
        CREATE FUNCTION guard_investigation_task() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF ROW(OLD.task_id, OLD.source_id, OLD.endpoint_id, OLD.created_by,
                 OLD.request_key_hash, OLD.request_hash, OLD.request, OLD.source_snapshot,
                 OLD.contract, OLD.contract_hash, OLD.created_at) IS DISTINCT FROM
             ROW(NEW.task_id, NEW.source_id, NEW.endpoint_id, NEW.created_by,
                 NEW.request_key_hash, NEW.request_hash, NEW.request, NEW.source_snapshot,
                 NEW.contract, NEW.contract_hash, NEW.created_at) THEN
            RAISE EXCEPTION 'investigation request is immutable';
          END IF;
          IF OLD.result_objects <> '{}'::jsonb AND OLD.result_objects <> NEW.result_objects THEN
            RAISE EXCEPTION 'investigation manifest is immutable';
          END IF;
          IF OLD.runtime_id IS NOT NULL AND
             ROW(OLD.runtime_id, OLD.remote_session_id) IS DISTINCT FROM
             ROW(NEW.runtime_id, NEW.remote_session_id) THEN
            RAISE EXCEPTION 'investigation runtime binding is immutable';
          END IF;
          IF OLD.delivery_hash IS NOT NULL AND
             ROW(OLD.delivery_hash, OLD.delivery) IS DISTINCT FROM
             ROW(NEW.delivery_hash, NEW.delivery) THEN
            RAISE EXCEPTION 'investigation delivery is immutable';
          END IF;
          IF OLD.review IS NOT NULL AND
             ROW(OLD.review, OLD.reviewer_id, OLD.review_key_hash, OLD.review_hash, OLD.status)
             IS DISTINCT FROM
             ROW(NEW.review, NEW.reviewer_id, NEW.review_key_hash, NEW.review_hash, NEW.status) THEN
            RAISE EXCEPTION 'investigation review is immutable';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER investigation_task_immutable BEFORE UPDATE ON investigation_tasks
        FOR EACH ROW EXECUTE FUNCTION guard_investigation_task();
        CREATE FUNCTION guard_investigation_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'investigation evidence and events are append only';
        END $$;
        CREATE TRIGGER investigation_material_immutable BEFORE UPDATE OR DELETE
        ON investigation_materials FOR EACH ROW EXECUTE FUNCTION guard_investigation_append_only();
        CREATE TRIGGER investigation_event_immutable BEFORE UPDATE OR DELETE
        ON investigation_events FOR EACH ROW EXECUTE FUNCTION guard_investigation_append_only();
    """)


def downgrade() -> None:
    op.drop_table("investigation_events")
    op.drop_table("investigation_materials")
    op.drop_table("investigation_tasks")
    op.execute("DROP FUNCTION IF EXISTS guard_investigation_task()")
    op.execute("DROP FUNCTION IF EXISTS guard_investigation_append_only()")
