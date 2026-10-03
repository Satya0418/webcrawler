"""
SQLite Migration Script for Excel Calculus PBRER Platform.
Safely migrates SQLite database schema without data loss:
- Upgrades CaseRecord to internal integer PK 'id' with composite uniqueness on (dataset_id, case_number).
- Links CaseEvent, CaseProduct, SearchMatch, RelevanceAssessment, and AuditLog to internal case_id.
- Adds new tracking columns (onset_mapping_status, is_active, dataset_id).
- Backfills case_id linkages for all existing records.
"""

import os
import shutil
import sqlite3
from datetime import datetime

def migrate_database(db_path: str = None):
    if not db_path:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        db_path = os.path.join(base_dir, "data", "excel_calculus.db")

    if not os.path.exists(db_path):
        print(f"Database file does not exist at {db_path}. Initial creation will be handled by SQLAlchemy.")
        return

    # Create backup before migrating
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Created pre-migration backup at: {backup_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        cur.execute("PRAGMA foreign_keys = OFF;")
        cur.execute("BEGIN TRANSACTION;")

        # Check if case_records already has 'id' column as integer PK
        col_info = cur.execute("PRAGMA table_info(case_records)").fetchall()
        cols = [c[1] for c in col_info]
        needs_case_records_migration = "id" not in cols

        if needs_case_records_migration:
            print("Migrating case_records to integer PK 'id'...")
            cur.execute("""
                CREATE TABLE case_records_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_number VARCHAR(64) NOT NULL,
                    dataset_id VARCHAR(64),
                    product_name VARCHAR(128),
                    reporting_period VARCHAR(128),
                    data_lock_point VARCHAR(64),
                    primary_product VARCHAR(128),
                    country VARCHAR(64),
                    report_type VARCHAR(64),
                    age VARCHAR(32),
                    sex VARCHAR(16),
                    initial_receipt_date VARCHAR(64),
                    is_serious BOOLEAN,
                    seriousness_raw VARCHAR(255),
                    listedness VARCHAR(64),
                    case_outcome VARCHAR(64),
                    primary_soc VARCHAR(255),
                    primary_event_flag VARCHAR(16),
                    previous_submission VARCHAR(64),
                    healthcare_prof VARCHAR(16),
                    non_serious_listed VARCHAR(64),
                    follow_up VARCHAR(64),
                    case_classification VARCHAR(64),
                    relevant_history TEXT,
                    narrative TEXT,
                    death_cause VARCHAR(255),
                    case_comments TEXT,
                    raw_source_file VARCHAR(255),
                    raw_source_sheet VARCHAR(128),
                    raw_source_row INTEGER,
                    created_at DATETIME,
                    CONSTRAINT uq_dataset_case UNIQUE (dataset_id, case_number)
                );
            """)

            # Copy existing columns
            common_cols = [c for c in cols if c != "id"]
            cols_str = ", ".join(common_cols)
            cur.execute(f"INSERT INTO case_records_new ({cols_str}) SELECT {cols_str} FROM case_records;")
            cur.execute("DROP TABLE case_records;")
            cur.execute("ALTER TABLE case_records_new RENAME TO case_records;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_records_case_number ON case_records (case_number);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_records_dataset_id ON case_records (dataset_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_records_product_name ON case_records (product_name);")
            print("case_records successfully migrated.")

        # Check and migrate case_events
        ev_cols = [c[1] for c in cur.execute("PRAGMA table_info(case_events)").fetchall()]
        if "case_id" not in ev_cols or "onset_mapping_status" not in ev_cols:
            print("Migrating case_events to add case_id and onset_mapping_status...")
            cur.execute("""
                CREATE TABLE case_events_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    case_number VARCHAR(64),
                    dataset_id VARCHAR(64),
                    position INTEGER,
                    raw_verbatim TEXT,
                    normalized_term VARCHAR(255),
                    preferred_term VARCHAR(255),
                    pt_code VARCHAR(32),
                    soc VARCHAR(255),
                    event_onset VARCHAR(64),
                    onset_mapping_status VARCHAR(64) DEFAULT 'CONFIRMED',
                    event_outcome VARCHAR(64),
                    seriousness_flag VARCHAR(64),
                    listedness_flag VARCHAR(64),
                    causality_flag VARCHAR(64),
                    source_file VARCHAR(255),
                    source_sheet VARCHAR(128),
                    source_row INTEGER,
                    FOREIGN KEY(case_id) REFERENCES case_records(id)
                );
            """)
            common_ev_cols = [c for c in ev_cols if c not in ("case_id", "onset_mapping_status")]
            ev_cols_str = ", ".join(common_ev_cols)
            cur.execute(f"INSERT INTO case_events_new ({ev_cols_str}) SELECT {ev_cols_str} FROM case_events;")
            cur.execute("""
                UPDATE case_events_new
                SET case_id = (
                    SELECT cr.id FROM case_records cr 
                    WHERE cr.case_number = case_events_new.case_number 
                    AND (case_events_new.dataset_id IS NULL OR cr.dataset_id = case_events_new.dataset_id)
                    LIMIT 1
                );
            """)
            cur.execute("DROP TABLE case_events;")
            cur.execute("ALTER TABLE case_events_new RENAME TO case_events;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_events_case_id ON case_events (case_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_events_case_number ON case_events (case_number);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_events_normalized_term ON case_events (normalized_term);")
            print("case_events successfully migrated.")

        # Check and migrate case_products
        prod_cols = [c[1] for c in cur.execute("PRAGMA table_info(case_products)").fetchall()]
        if "case_id" not in prod_cols:
            print("Migrating case_products to add case_id...")
            cur.execute("""
                CREATE TABLE case_products_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    case_number VARCHAR(64),
                    dataset_id VARCHAR(64),
                    product_name_raw TEXT,
                    brand_name VARCHAR(128),
                    active_substance VARCHAR(128),
                    role VARCHAR(64),
                    daily_dose VARCHAR(64),
                    form VARCHAR(64),
                    duration VARCHAR(64),
                    indication_pt VARCHAR(255),
                    FOREIGN KEY(case_id) REFERENCES case_records(id)
                );
            """)
            common_prod = [c for c in prod_cols if c != "case_id"]
            prod_str = ", ".join(common_prod)
            cur.execute(f"INSERT INTO case_products_new ({prod_str}) SELECT {prod_str} FROM case_products;")
            cur.execute("""
                UPDATE case_products_new
                SET case_id = (
                    SELECT cr.id FROM case_records cr 
                    WHERE cr.case_number = case_products_new.case_number 
                    AND (case_products_new.dataset_id IS NULL OR cr.dataset_id = case_products_new.dataset_id)
                    LIMIT 1
                );
            """)
            cur.execute("DROP TABLE case_products;")
            cur.execute("ALTER TABLE case_products_new RENAME TO case_products;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_products_case_id ON case_products (case_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_case_products_case_number ON case_products (case_number);")
            print("case_products successfully migrated.")

        # Check and migrate search_runs
        sr_cols = [c[1] for c in cur.execute("PRAGMA table_info(search_runs)").fetchall()]
        if "is_active" not in sr_cols or "dataset_id" not in sr_cols:
            print("Migrating search_runs to add is_active and dataset_id...")
            cur.execute("""
                CREATE TABLE search_runs_new (
                    id VARCHAR(64) PRIMARY KEY,
                    dataset_id VARCHAR(64),
                    product_name VARCHAR(128),
                    reporting_period VARCHAR(128),
                    concern_id VARCHAR(64),
                    search_method VARCHAR(64),
                    search_config TEXT,
                    reference_version VARCHAR(32) DEFAULT 'MedDRA 29.0',
                    execution_time DATETIME,
                    candidate_events_count INTEGER DEFAULT 0,
                    distinct_cases_count INTEGER DEFAULT 0,
                    executed_by VARCHAR(64) DEFAULT 'reviewer',
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY(concern_id) REFERENCES safety_concerns(id)
                );
            """)
            common_sr = [c for c in sr_cols if c in ("id", "product_name", "reporting_period", "concern_id", "search_method", "search_config", "reference_version", "execution_time", "candidate_events_count", "distinct_cases_count", "executed_by")]
            sr_str = ", ".join(common_sr)
            cur.execute(f"INSERT INTO search_runs_new ({sr_str}) SELECT {sr_str} FROM search_runs;")
            cur.execute("DROP TABLE search_runs;")
            cur.execute("ALTER TABLE search_runs_new RENAME TO search_runs;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_search_runs_concern_id ON search_runs (concern_id);")
            print("search_runs successfully migrated.")

        # Check and migrate search_matches
        sm_cols = [c[1] for c in cur.execute("PRAGMA table_info(search_matches)").fetchall()]
        if "case_id" not in sm_cols:
            print("Migrating search_matches to add case_id...")
            cur.execute("""
                CREATE TABLE search_matches_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_run_id VARCHAR(64),
                    concern_id VARCHAR(64),
                    case_id INTEGER,
                    case_number VARCHAR(64),
                    event_id INTEGER,
                    search_method VARCHAR(64),
                    matched_field VARCHAR(128),
                    matched_term VARCHAR(255),
                    pt_code VARCHAR(32),
                    smq_name VARCHAR(255),
                    smq_scope VARCHAR(32),
                    reference_source VARCHAR(255),
                    evidence TEXT,
                    source_file VARCHAR(255),
                    source_sheet VARCHAR(128),
                    source_row INTEGER,
                    created_at DATETIME,
                    FOREIGN KEY(concern_id) REFERENCES safety_concerns(id),
                    FOREIGN KEY(case_id) REFERENCES case_records(id),
                    FOREIGN KEY(event_id) REFERENCES case_events(id),
                    FOREIGN KEY(search_run_id) REFERENCES search_runs(id)
                );
            """)
            common_sm = [c for c in sm_cols if c != "case_id"]
            sm_str = ", ".join(common_sm)
            cur.execute(f"INSERT INTO search_matches_new ({sm_str}) SELECT {sm_str} FROM search_matches;")
            cur.execute("""
                UPDATE search_matches_new
                SET case_id = (
                    SELECT cr.id FROM case_records cr 
                    WHERE cr.case_number = search_matches_new.case_number 
                    LIMIT 1
                );
            """)
            cur.execute("DROP TABLE search_matches;")
            cur.execute("ALTER TABLE search_matches_new RENAME TO search_matches;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_search_matches_case_id ON search_matches (case_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_search_matches_concern_id ON search_matches (concern_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_search_matches_search_run_id ON search_matches (search_run_id);")
            print("search_matches successfully migrated.")

        # Check and migrate relevance_assessments
        ra_cols = [c[1] for c in cur.execute("PRAGMA table_info(relevance_assessments)").fetchall()]
        if "case_id" not in ra_cols or "dataset_id" not in ra_cols:
            print("Migrating relevance_assessments to add case_id and dataset_id...")
            cur.execute("""
                CREATE TABLE relevance_assessments_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    case_number VARCHAR(64),
                    concern_id VARCHAR(64),
                    dataset_id VARCHAR(64),
                    status VARCHAR(32) DEFAULT 'CANDIDATE',
                    exclusion_reason VARCHAR(255),
                    reviewer_notes TEXT,
                    secondary_assessment_result TEXT,
                    reviewer_id VARCHAR(64) DEFAULT 'reviewer',
                    updated_at DATETIME,
                    FOREIGN KEY(case_id) REFERENCES case_records(id),
                    FOREIGN KEY(concern_id) REFERENCES safety_concerns(id)
                );
            """)
            common_ra = [c for c in ra_cols if c not in ("case_id", "dataset_id")]
            ra_str = ", ".join(common_ra)
            cur.execute(f"INSERT INTO relevance_assessments_new ({ra_str}) SELECT {ra_str} FROM relevance_assessments;")
            cur.execute("""
                UPDATE relevance_assessments_new
                SET case_id = (
                    SELECT cr.id FROM case_records cr 
                    WHERE cr.case_number = relevance_assessments_new.case_number 
                    LIMIT 1
                ),
                dataset_id = (
                    SELECT cr.dataset_id FROM case_records cr 
                    WHERE cr.case_number = relevance_assessments_new.case_number 
                    LIMIT 1
                );
            """)
            cur.execute("DROP TABLE relevance_assessments;")
            cur.execute("ALTER TABLE relevance_assessments_new RENAME TO relevance_assessments;")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_relevance_assessments_case_id ON relevance_assessments (case_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_relevance_assessments_concern_id ON relevance_assessments (concern_id);")
            print("relevance_assessments successfully migrated.")

        # Check and migrate audit_logs
        al_cols = [c[1] for c in cur.execute("PRAGMA table_info(audit_logs)").fetchall()]
        if "case_id" not in al_cols or "dataset_id" not in al_cols:
            print("Migrating audit_logs to add case_id and dataset_id...")
            cur.execute("""
                CREATE TABLE audit_logs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    case_number VARCHAR(64),
                    concern_id VARCHAR(64),
                    dataset_id VARCHAR(64),
                    user_id VARCHAR(64) DEFAULT 'system',
                    action VARCHAR(128),
                    previous_state TEXT,
                    new_state TEXT,
                    timestamp DATETIME
                );
            """)
            common_al = [c for c in al_cols if c not in ("case_id", "dataset_id")]
            al_str = ", ".join(common_al)
            cur.execute(f"INSERT INTO audit_logs_new ({al_str}) SELECT {al_str} FROM audit_logs;")
            cur.execute("""
                UPDATE audit_logs_new
                SET case_id = (
                    SELECT cr.id FROM case_records cr 
                    WHERE cr.case_number = audit_logs_new.case_number 
                    LIMIT 1
                );
            """)
            cur.execute("DROP TABLE audit_logs;")
            cur.execute("ALTER TABLE audit_logs_new RENAME TO audit_logs;")
            print("audit_logs successfully migrated.")

        conn.commit()
        cur.execute("PRAGMA foreign_keys = ON;")
        print("Database schema migration completed successfully without data loss!")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}. Rolled back.")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
