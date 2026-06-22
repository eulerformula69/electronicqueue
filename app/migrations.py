from sqlalchemy import text


def init_ticket_numbering(engine):
    ddl = """
    CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1;

    CREATE TABLE IF NOT EXISTS ticket_counter_state (
        id int PRIMARY KEY DEFAULT 1,
        current_day date NOT NULL,
        CONSTRAINT single_row CHECK (id = 1)
    );

    INSERT INTO ticket_counter_state (id, current_day)
    VALUES (1, CURRENT_DATE)
    ON CONFLICT (id) DO NOTHING;

    CREATE OR REPLACE FUNCTION public.ticket_number_trigger()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
        v_old_day date;
    BEGIN
        SELECT current_day INTO v_old_day
        FROM ticket_counter_state
        WHERE id = 1
        FOR UPDATE;

        IF v_old_day < CURRENT_DATE THEN
            PERFORM setval('ticket_number_seq', 1, false);
            UPDATE ticket_counter_state
            SET current_day = CURRENT_DATE
            WHERE id = 1;
        END IF;

        IF NEW.number IS NULL THEN
            NEW.number := nextval('ticket_number_seq')::text;
        END IF;

        RETURN NEW;
    END;
    $$;

    DROP TRIGGER IF EXISTS ticket_number_before_insert ON tickets;

    CREATE TRIGGER ticket_number_before_insert
    BEFORE INSERT ON tickets
    FOR EACH ROW
    EXECUTE FUNCTION public.ticket_number_trigger();
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_choice_schema(engine):
    """Add operator-choice columns to databases created by older releases."""
    ddl = """
    ALTER TABLE services
        ADD COLUMN IF NOT EXISTS operator_choice_enabled integer NOT NULL DEFAULT 0;

    UPDATE services
    SET operator_choice_enabled = 0
    WHERE operator_choice_enabled IS NULL;

    ALTER TABLE services
        ALTER COLUMN operator_choice_enabled SET DEFAULT 0,
        ALTER COLUMN operator_choice_enabled SET NOT NULL;

    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS target_window_id integer REFERENCES windows(id);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_service_order_schema(engine):
    """Add a stable display order and preserve the existing ID-based order."""
    ddl = """
    ALTER TABLE services
        ADD COLUMN IF NOT EXISTS display_order integer;

    WITH ordered_services AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY id) - 1 AS new_order
        FROM services
    )
    UPDATE services
    SET display_order = ordered_services.new_order
    FROM ordered_services
    WHERE services.id = ordered_services.id
      AND services.display_order IS NULL;

    ALTER TABLE services
        ALTER COLUMN display_order SET DEFAULT 0,
        ALTER COLUMN display_order SET NOT NULL;

    CREATE INDEX IF NOT EXISTS ix_services_display_order
        ON services (display_order, id);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_stages_schema(engine):
    """Add ticket-chain metadata and backfill tickets from older releases."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS completion_reason varchar(16),
        ADD COLUMN IF NOT EXISTS root_ticket_id integer;

    UPDATE tickets
    SET completion_reason = CASE
        WHEN status = 'finished' THEN 'completed'
        WHEN status = 'cancelled' THEN 'cancelled'
        ELSE NULL
    END
    WHERE completion_reason IS NULL;

    UPDATE tickets SET root_ticket_id = id WHERE root_ticket_id IS NULL;

    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_tickets_root_ticket_id'
              AND conrelid = 'tickets'::regclass
        ) THEN
            ALTER TABLE tickets
                ADD CONSTRAINT fk_tickets_root_ticket_id
                FOREIGN KEY (root_ticket_id) REFERENCES tickets(id);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_tickets_completion_reason'
              AND conrelid = 'tickets'::regclass
        ) THEN
            ALTER TABLE tickets
                ADD CONSTRAINT ck_tickets_completion_reason
                CHECK (
                    completion_reason IS NULL OR completion_reason IN
                    ('completed', 'redirected', 'cancelled')
                );
        END IF;
    END
    $$;

    CREATE INDEX IF NOT EXISTS ix_tickets_root_ticket_id
        ON tickets (root_ticket_id);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_status_periods_schema(engine):
    """Create operator status history and migrate older column types."""
    ddl = """
    CREATE TABLE IF NOT EXISTS operator_status_periods (
        id bigserial PRIMARY KEY,
        operator_id integer NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
        window_id integer REFERENCES windows(id) ON DELETE SET NULL,
        status varchar(16) NOT NULL,
        started_at timestamp without time zone NOT NULL
            DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk'),
        ended_at timestamp without time zone,
        CONSTRAINT ck_operator_status_periods_status
            CHECK (status IN ('online', 'break', 'offline')),
        CONSTRAINT ck_operator_status_periods_dates
            CHECK (ended_at IS NULL OR ended_at >= started_at)
    );

    CREATE UNIQUE INDEX IF NOT EXISTS uq_operator_current_status
        ON operator_status_periods (operator_id)
        WHERE ended_at IS NULL;

    CREATE INDEX IF NOT EXISTS ix_operator_status_period
        ON operator_status_periods (operator_id, started_at);

    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'operator_status_periods'
              AND column_name = 'started_at'
              AND data_type = 'timestamp with time zone'
        ) THEN
            ALTER TABLE operator_status_periods
                ALTER COLUMN started_at DROP DEFAULT,
                ALTER COLUMN started_at TYPE timestamp without time zone
                    USING started_at AT TIME ZONE 'Asia/Irkutsk',
                ALTER COLUMN ended_at TYPE timestamp without time zone
                    USING ended_at AT TIME ZONE 'Asia/Irkutsk',
                ALTER COLUMN started_at SET DEFAULT
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk');
        END IF;
    END
    $$;

    ALTER TABLE operator_status_periods
        ALTER COLUMN started_at SET DEFAULT
            (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk');

    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_queue_mode_periods_schema(engine):
    """Create queue-mode history and seed its current period."""
    ddl = """
    CREATE TABLE IF NOT EXISTS queue_mode_periods (
        id bigserial PRIMARY KEY,
        queue_mode varchar(40) NOT NULL,
        started_at timestamp without time zone NOT NULL
            DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk'),
        ended_at timestamp without time zone,
        current_period_key integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_queue_mode_periods_mode CHECK (
            queue_mode IN ('priority_fifo', 'dynamic_operator_distribution')
        ),
        CONSTRAINT ck_queue_mode_periods_dates CHECK (
            ended_at IS NULL OR ended_at >= started_at
        )
    );

    CREATE UNIQUE INDEX IF NOT EXISTS uq_queue_mode_current_period
        ON queue_mode_periods (current_period_key)
        WHERE ended_at IS NULL;
    CREATE INDEX IF NOT EXISTS ix_queue_mode_periods_started_at
        ON queue_mode_periods (started_at);

    INSERT INTO queue_mode_periods (queue_mode)
    SELECT COALESCE(
        (SELECT queue_mode FROM system_settings WHERE id = 1),
        'priority_fifo'
    )
    WHERE NOT EXISTS (
        SELECT 1 FROM queue_mode_periods WHERE ended_at IS NULL
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))
