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
        ADD COLUMN IF NOT EXISTS operator_choice_enabled integer NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS operator_choice_allow_break integer NOT NULL DEFAULT 1,
        ADD COLUMN IF NOT EXISTS operator_choice_allow_offline integer NOT NULL DEFAULT 0;

    UPDATE services
    SET operator_choice_enabled = 0
    WHERE operator_choice_enabled IS NULL;

    ALTER TABLE services
        ALTER COLUMN operator_choice_enabled SET DEFAULT 0,
        ALTER COLUMN operator_choice_enabled SET NOT NULL,
        ALTER COLUMN operator_choice_allow_break SET DEFAULT 1,
        ALTER COLUMN operator_choice_allow_break SET NOT NULL,
        ALTER COLUMN operator_choice_allow_offline SET DEFAULT 0,
        ALTER COLUMN operator_choice_allow_offline SET NOT NULL;

    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS redirect_allow_break varchar DEFAULT 'true',
        ADD COLUMN IF NOT EXISTS redirect_allow_offline varchar DEFAULT 'false';

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


def migrate_service_archive_schema(engine):
    """Add soft-delete support for services while keeping ticket history intact."""
    ddl = """
    ALTER TABLE services
        ADD COLUMN IF NOT EXISTS is_archived integer NOT NULL DEFAULT 0;

    UPDATE services
    SET is_archived = 0
    WHERE is_archived IS NULL;

    ALTER TABLE services
        ALTER COLUMN is_archived SET DEFAULT 0,
        ALTER COLUMN is_archived SET NOT NULL;

    CREATE INDEX IF NOT EXISTS ix_services_is_archived_display_order
        ON services (is_archived, display_order, id);
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


def migrate_ticket_operator_schema(engine):
    """Store the operator who called/served each ticket."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS operator_id integer;

    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            JOIN pg_attribute
              ON pg_attribute.attrelid = pg_constraint.conrelid
             AND pg_attribute.attnum = ANY(pg_constraint.conkey)
            WHERE pg_constraint.conrelid = 'tickets'::regclass
              AND pg_constraint.contype = 'f'
              AND pg_constraint.confrelid = 'operators'::regclass
              AND pg_attribute.attname = 'operator_id'
        ) THEN
            ALTER TABLE tickets
                ADD CONSTRAINT fk_tickets_operator_id
                FOREIGN KEY (operator_id) REFERENCES operators(id)
                ON DELETE SET NULL;
        END IF;
    END
    $$;

    WITH matched_periods AS (
        SELECT DISTINCT ON (t.id)
            t.id AS ticket_id,
            osp.operator_id
        FROM tickets t
        JOIN operator_status_periods osp
          ON osp.window_id = t.window_id
         AND COALESCE(t.called_at, t.finished_at, t.created_at) >= osp.started_at
         AND (
             osp.ended_at IS NULL
             OR COALESCE(t.called_at, t.finished_at, t.created_at) < osp.ended_at
         )
        WHERE t.operator_id IS NULL
          AND t.window_id IS NOT NULL
          AND (t.called_at IS NOT NULL OR t.finished_at IS NOT NULL)
        ORDER BY t.id, osp.started_at DESC
    )
    UPDATE tickets t
    SET operator_id = matched_periods.operator_id
    FROM matched_periods
    WHERE t.id = matched_periods.ticket_id
      AND t.operator_id IS NULL;

    UPDATE tickets t
    SET operator_id = o.id
    FROM operators o
    WHERE t.operator_id IS NULL
      AND t.window_id = o.window_id
      AND (t.called_at IS NOT NULL OR t.finished_at IS NOT NULL);

    CREATE INDEX IF NOT EXISTS ix_tickets_operator_id
        ON tickets (operator_id);
    CREATE INDEX IF NOT EXISTS ix_tickets_operator_finished_at
        ON tickets (operator_id, finished_at);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_queue_entered_at_schema(engine):
    """Track the time a ticket should be considered available in queue order."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS queue_entered_at timestamp without time zone
        DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk');

    UPDATE tickets
    SET queue_entered_at = created_at
    WHERE queue_entered_at IS NULL;

    ALTER TABLE tickets
        ALTER COLUMN queue_entered_at SET DEFAULT
            (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk');

    CREATE INDEX IF NOT EXISTS ix_tickets_status_queue_entered_at
        ON tickets (status, queue_entered_at);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_return_count_schema(engine):
    """Track how many times a ticket was returned to the queue."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS returned_to_queue_count integer NOT NULL DEFAULT 0;

    UPDATE tickets
    SET returned_to_queue_count = 0
    WHERE returned_to_queue_count IS NULL;

    ALTER TABLE tickets
        ALTER COLUMN returned_to_queue_count SET DEFAULT 0,
        ALTER COLUMN returned_to_queue_count SET NOT NULL;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_defer_schema(engine):
    """Add fields used by operator-owned deferred tickets and cancellations."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS defer_reason varchar(64),
        ADD COLUMN IF NOT EXISTS deferred_at timestamp without time zone,
        ADD COLUMN IF NOT EXISTS cancel_reason varchar(64);

    ALTER TABLE tickets
        ALTER COLUMN defer_reason TYPE varchar(255),
        ALTER COLUMN cancel_reason TYPE varchar(255);

    CREATE INDEX IF NOT EXISTS ix_tickets_operator_deferred_at
        ON tickets (operator_id, deferred_at);
    CREATE INDEX IF NOT EXISTS ix_tickets_window_status_deferred_at
        ON tickets (window_id, status, deferred_at);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_recall_schema(engine):
    """Persist the latest repeat-call time for server-authoritative cooldowns."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS last_recalled_at timestamp;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_service_started_schema(engine):
    """Add the factual start time for the called -> serving transition."""
    ddl = """
    ALTER TABLE tickets
        ADD COLUMN IF NOT EXISTS service_started_at timestamp without time zone;

    CREATE INDEX IF NOT EXISTS ix_tickets_status_service_started_at
        ON tickets (status, service_started_at);
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


def migrate_ticket_notice_settings_schema(engine):
    """Add configurable terminal notice settings to existing installations."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS ticket_print_scale_percent integer DEFAULT 94,
        ADD COLUMN IF NOT EXISTS ticket_notice_duration_printed_seconds integer DEFAULT 7,
        ADD COLUMN IF NOT EXISTS ticket_notice_duration_unprinted_seconds integer DEFAULT 45,
        ADD COLUMN IF NOT EXISTS ticket_notice_printed_text varchar(500) DEFAULT 'Ваш номер: <number>',
        ADD COLUMN IF NOT EXISTS ticket_notice_unprinted_text varchar(500) DEFAULT E'Пожалуйста, запомните свой номер:\\n<number>';

    UPDATE system_settings
    SET ticket_print_scale_percent = COALESCE(ticket_print_scale_percent, 94),
        ticket_notice_duration_printed_seconds = COALESCE(ticket_notice_duration_printed_seconds, 7),
        ticket_notice_duration_unprinted_seconds = COALESCE(ticket_notice_duration_unprinted_seconds, 45),
        ticket_notice_printed_text = COALESCE(ticket_notice_printed_text, 'Ваш номер: <number>'),
        ticket_notice_unprinted_text = COALESCE(ticket_notice_unprinted_text, E'Пожалуйста, запомните свой номер:\\n<number>');
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_board_ticker_settings_schema(engine):
    """Add configurable ticker text and presets for queue boards."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS board_ticker_text varchar(500) DEFAULT '',
        ADD COLUMN IF NOT EXISTS board_ticker_messages varchar(4000) DEFAULT '';

    UPDATE system_settings
    SET board_ticker_text = ''
    WHERE board_ticker_text IS NULL;

    UPDATE system_settings
    SET board_ticker_messages = json_build_array(
        json_build_object('text', board_ticker_text, 'enabled', true)
    )::text
    WHERE (board_ticker_messages IS NULL OR board_ticker_messages = '')
      AND board_ticker_text <> '';

    UPDATE system_settings
    SET board_ticker_messages = ''
    WHERE board_ticker_messages IS NULL;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_reason_settings_schema(engine):
    """Add configurable cancel/defer reasons to system settings."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS cancel_reason_options varchar(4000) DEFAULT '',
        ADD COLUMN IF NOT EXISTS defer_reason_options varchar(4000) DEFAULT '';

    UPDATE system_settings
    SET cancel_reason_options = ''
    WHERE cancel_reason_options IS NULL;

    UPDATE system_settings
    SET defer_reason_options = ''
    WHERE defer_reason_options IS NULL;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_auto_call_settings_schema(engine):
    """Add global auto-call settings controlled from admin settings."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS auto_call_enabled varchar DEFAULT 'false',
        ADD COLUMN IF NOT EXISTS auto_call_delay_seconds integer DEFAULT 60;

    UPDATE system_settings
    SET auto_call_enabled = COALESCE(auto_call_enabled, 'false'),
        auto_call_delay_seconds = COALESCE(auto_call_delay_seconds, 60);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_auto_call_schema(engine):
    """Add per-operator auto-call override."""
    ddl = """
    ALTER TABLE operators
        ADD COLUMN IF NOT EXISTS auto_call_mode varchar DEFAULT 'default';

    UPDATE operators
    SET auto_call_mode = 'default'
    WHERE auto_call_mode IS NULL
       OR auto_call_mode NOT IN ('default', 'enabled', 'disabled');
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_auto_dispatch_schema(engine):
    """Persist recoverable server-side auto-dispatch deadlines."""
    ddl = """
    ALTER TABLE operators
        ADD COLUMN IF NOT EXISTS next_auto_call_at timestamp without time zone;

    CREATE INDEX IF NOT EXISTS ix_operators_next_auto_call_at
        ON operators (next_auto_call_at)
        WHERE next_auto_call_at IS NOT NULL;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_called_ticket_min_wait_schema(engine):
    """Add the minimum wait before a called ticket can be finished."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS called_ticket_min_wait_seconds integer DEFAULT 180;

    UPDATE system_settings
    SET called_ticket_min_wait_seconds = COALESCE(called_ticket_min_wait_seconds, 180);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_max_ticket_redirects_schema(engine):
    """Add the configurable ticket redirect limit."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS max_ticket_redirects integer DEFAULT 3;

    UPDATE system_settings
    SET max_ticket_redirects = COALESCE(max_ticket_redirects, 3);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_auto_call_balance_and_board_cancel_schema(engine):
    """Add low-load auto-call balancing and board cancellation settings."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS auto_call_balance_enabled varchar DEFAULT 'true',
        ADD COLUMN IF NOT EXISTS auto_call_balance_queue_threshold integer DEFAULT 3,
        ADD COLUMN IF NOT EXISTS auto_call_balance_min_free_operators integer DEFAULT 2,
        ADD COLUMN IF NOT EXISTS cancelled_ticket_board_display_seconds integer DEFAULT 60,
        ADD COLUMN IF NOT EXISTS cancelled_ticket_board_message_template varchar(500)
            DEFAULT '⚠ Талон <number>: вызов отменён оператором окна <window>. Вернулись? Сообщите номер оператору.';

    UPDATE system_settings
    SET cancelled_ticket_board_message_template =
        '⚠ Талон <number>: вызов отменён оператором окна <window>. Вернулись? Сообщите номер оператору.'
    WHERE cancelled_ticket_board_message_template IS NULL
       OR cancelled_ticket_board_message_template =
        '⚠ Талон <number>: вызов отменён — клиент не подошёл. Вернулись? Сообщите номер оператору.';
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_service_terminal_visibility_schema(engine):
    """Add service terminal visibility flag."""
    ddl = """
    ALTER TABLE services
        ADD COLUMN IF NOT EXISTS visible_on_terminal integer NOT NULL DEFAULT 1;

    UPDATE services
    SET visible_on_terminal = 1
    WHERE visible_on_terminal IS NULL;

    ALTER TABLE services
        ALTER COLUMN visible_on_terminal SET DEFAULT 1,
        ALTER COLUMN visible_on_terminal SET NOT NULL;
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_service_groups_schema(engine):
    """Add service groups used for display only."""
    ddl = """
    CREATE TABLE IF NOT EXISTS service_groups (
        id serial PRIMARY KEY,
        name varchar NOT NULL,
        display_order integer NOT NULL DEFAULT 0
    );

    ALTER TABLE services
        ADD COLUMN IF NOT EXISTS service_group_id integer;

    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_services_service_group_id'
              AND conrelid = 'services'::regclass
        ) THEN
            ALTER TABLE services
                ADD CONSTRAINT fk_services_service_group_id
                FOREIGN KEY (service_group_id) REFERENCES service_groups(id)
                ON DELETE SET NULL;
        END IF;
    END
    $$;

    CREATE INDEX IF NOT EXISTS ix_service_groups_display_order
        ON service_groups (display_order, id);
    CREATE INDEX IF NOT EXISTS ix_services_service_group_id
        ON services (service_group_id);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_service_notifications_schema(engine):
    """Create per-operator service notification settings."""
    ddl = """
    CREATE TABLE IF NOT EXISTS operator_service_notifications (
        id serial PRIMARY KEY,
        operator_id integer NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
        service_id integer NOT NULL REFERENCES services(id) ON DELETE CASCADE,
        enabled integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_operator_service_notifications UNIQUE (operator_id, service_id)
    );

    CREATE INDEX IF NOT EXISTS ix_operator_service_notifications_operator_id
        ON operator_service_notifications (operator_id);
    CREATE INDEX IF NOT EXISTS ix_operator_service_notifications_service_id
        ON operator_service_notifications (service_id);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_workflow_settings_schema(engine):
    """Add configurable limits for operator ticket workflow."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS short_service_warning_minutes integer DEFAULT 5,
        ADD COLUMN IF NOT EXISTS max_deferred_tickets_per_operator integer DEFAULT 3;

    UPDATE system_settings
    SET short_service_warning_minutes = COALESCE(short_service_warning_minutes, 5),
        max_deferred_tickets_per_operator = COALESCE(max_deferred_tickets_per_operator, 3);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_operator_changelog_button_text_schema(engine):
    """Add configurable text for the operator changelog confirmation button."""
    ddl = """
    ALTER TABLE system_settings
        ADD COLUMN IF NOT EXISTS operator_changelog_confirm_button_text varchar(200)
        DEFAULT 'Понятно';

    UPDATE system_settings
    SET operator_changelog_confirm_button_text = COALESCE(
        NULLIF(TRIM(operator_changelog_confirm_button_text), ''),
        'Понятно'
    );
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def migrate_ticket_admin_changes_schema(engine):
    """Create the immutable audit trail for manual admin ticket changes."""
    ddl = """
    CREATE TABLE IF NOT EXISTS ticket_admin_changes (
        id bigserial PRIMARY KEY,
        ticket_id integer NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
        admin_id integer REFERENCES admins(id) ON DELETE SET NULL,
        admin_login varchar NOT NULL,
        previous_status varchar NOT NULL,
        new_status varchar NOT NULL,
        reason varchar(255),
        changed_at timestamp without time zone NOT NULL
            DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Irkutsk')
    );

    CREATE INDEX IF NOT EXISTS ix_ticket_admin_changes_ticket_changed
        ON ticket_admin_changes (ticket_id, changed_at);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
