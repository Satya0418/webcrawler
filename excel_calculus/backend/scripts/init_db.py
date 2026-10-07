import os
import sys

# Ensure backend package can be imported
sys.path.insert(0, "/Users/satya/projects/webcrwler")

from excel_calculus.backend.app.database import engine, SessionLocal, Base
from excel_calculus.backend.app.models.entities import (
    CaseRecord, CaseEvent, CaseProduct, SMQTerm, SafetyConcern, SearchMatch
)
from excel_calculus.backend.app.services.ingestion import IngestionService
from excel_calculus.backend.app.services.smq_loader import SMQLoaderService
from excel_calculus.backend.app.services.concern_seeder import seed_safety_concerns
from excel_calculus.backend.app.services.search_engine import SearchEngineService

def main():
    print("=" * 60)
    print("INITIALIZING EXCEL CALCULUS PV DATABASE")
    print("=" * 60)

    # 1. Create tables
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    base_artifacts = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)"
    smq_path = os.path.join(base_artifacts, "MedDRA SMQ list/SMQ_spreadsheet_29_0_English.xlsx")
    abi_path = os.path.join(base_artifacts, "Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx")
    oxy_path = os.path.join(base_artifacts, "Oxycodone/Oxycodone_20260412_CAN PBRER_Interval LL.xlsx")

    # 2. Seed Safety Concerns
    print("\n[1/5] Seeding Safety Concerns...")
    seed_safety_concerns(db)
    concern_count = db.query(SafetyConcern).count()
    print(f" -> {concern_count} Safety Concerns configured.")

    # 3. Load MedDRA SMQs
    print("\n[2/5] Loading MedDRA SMQs...")
    smq_count = db.query(SMQTerm).count()
    if smq_count == 0 and os.path.exists(smq_path):
        loader = SMQLoaderService(db)
        loader_res = loader.load_smq_file(smq_path)
        print(f" -> {loader_res['total_smq_terms']} SMQ terms loaded.")
    else:
        print(f" -> MedDRA SMQ terms already present: {smq_count} entries.")

    # 4. Ingest Abiraterone Line Listing
    print("\n[3/5] Ingesting Abiraterone Interval Line Listing...")
    ingestion = IngestionService(db)
    if os.path.exists(abi_path):
        abi_res = ingestion.ingest_linelisting_file(abi_path, primary_product_name="Abiraterone")
        print(f" -> Abiraterone ingested: {abi_res['total_cases']} cases, {abi_res['total_events']} events, {abi_res['total_products']} products.")

    # 5. Ingest Oxycodone Line Listing
    print("\n[4/5] Ingesting Oxycodone Interval Line Listing...")
    if os.path.exists(oxy_path):
        oxy_res = ingestion.ingest_linelisting_file(oxy_path, primary_product_name="Oxycodone")
        print(f" -> Oxycodone ingested: {oxy_res['total_cases']} cases, {oxy_res['total_events']} events, {oxy_res['total_products']} products.")

    # 6. Execute Deterministic Search for all Safety Concerns
    print("\n[5/5] Executing Deterministic Search for all Safety Concerns...")
    search_service = SearchEngineService(db)
    concerns = db.query(SafetyConcern).all()
    for c in concerns:
        summary = search_service.execute_concern_search(c.id, reviewer_id="init_system")
        print(f" -> Concern: {c.name[:35]:<35} | Matches: {summary['total_event_matches']} events | Cases: {summary['distinct_candidate_cases']}")

    print("\n" + "=" * 60)
    print("DATABASE INITIALIZATION & VERIFICATION COMPLETE")
    print("=" * 60)
    db.close()

if __name__ == "__main__":
    main()
