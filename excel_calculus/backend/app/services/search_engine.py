import json
import re
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from excel_calculus.backend.app.models.entities import (
    SafetyConcern, CaseRecord, CaseEvent, CaseProduct, 
    SMQTerm, SearchRun, SearchMatch, RelevanceAssessment, AuditLog
)

class SearchEngineService:
    def __init__(self, db: Session):
        self.db = db

    def execute_concern_search(self, concern_id: str, reviewer_id: str = "reviewer"):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        config = json.loads(concern.search_config) if concern.search_config else {}
        method = concern.search_method

        # Unique Search Run tracking
        run_id = f"run_{concern.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        search_run = SearchRun(
            id=run_id,
            product_name=concern.product_name,
            reporting_period=concern.reporting_period,
            concern_id=concern_id,
            search_method=method,
            search_config=concern.search_config,
            reference_version="MedDRA 29.0",
            execution_time=datetime.utcnow(),
            executed_by=reviewer_id
        )
        self.db.add(search_run)

        # Clear existing matches for this concern to maintain deterministic reproducibility
        self.db.query(SearchMatch).filter_by(concern_id=concern_id).delete()

        matches_to_add = []

        if method in ("BROAD_SMQ", "NARROW_SMQ"):
            smq_name = config.get("smq_name")
            scope = config.get("scope", "Broad" if method == "BROAD_SMQ" else "Narrow")

            # Exact VLOOKUP reference mapping:
            # Query all active SMQ terms for this SMQ and Scope
            smq_records = self.db.query(SMQTerm).filter(
                SMQTerm.smq_name == smq_name,
                SMQTerm.scope == scope,
                SMQTerm.is_active == True
            ).all()

            # Build exact reference lookup map: uppercase_pt -> SMQTerm
            # (Matches Excel: VLOOKUP(event, reference_PT_list, 1, FALSE))
            ref_lookup = {st.pt_name_upper: st for st in smq_records}

            # Fetch events for the product in scope
            events_query = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name
            )
            if concern.reporting_period and concern.reporting_period != "Current Period":
                # Filter by reporting period when set on case record
                events_query = events_query.filter(
                    (CaseRecord.reporting_period == concern.reporting_period) | (CaseRecord.reporting_period.is_(None))
                )

            candidate_events = events_query.all()

            for ev, case in candidate_events:
                # Deterministic exact lookup
                matched_ref = ref_lookup.get(ev.normalized_term)
                if matched_ref:
                    # Update event with authoritative MedDRA terminology mapping
                    ev.preferred_term = matched_ref.pt_name
                    ev.pt_code = matched_ref.pt_code

                    matches_to_add.append(SearchMatch(
                        search_run_id=run_id,
                        concern_id=concern_id,
                        case_number=case.case_number,
                        event_id=ev.id,
                        search_method=method,
                        matched_field="Event Verbatim (Exact PT Lookup)",
                        matched_term=matched_ref.pt_name,
                        pt_code=matched_ref.pt_code,
                        smq_name=smq_name,
                        smq_scope=scope,
                        reference_source=f"{scope} SMQ: {smq_name} (Code: {matched_ref.smq_code or 'N/A'})",
                        evidence=f"Exact match for MedDRA PT '{matched_ref.pt_name}' [PT Code: {matched_ref.pt_code}] in event verbatim: {ev.raw_verbatim}",
                        source_file=ev.source_file or case.raw_source_file,
                        source_sheet=ev.source_sheet or case.raw_source_sheet,
                        source_row=ev.source_row or case.raw_source_row
                    ))

        elif method == "SMQ_SUBFILTER":
            # e.g. Broad SMQ Medication Errors further assessed with PTs of Overdose and Accidental overdose
            smq_name = config.get("smq_name", "Medication errors (SMQ)")
            scope = config.get("scope", "Broad")
            sub_pts = [p.strip().upper() for p in config.get("sub_filter_pts", [])]

            smq_records = self.db.query(SMQTerm).filter(
                SMQTerm.smq_name == smq_name,
                SMQTerm.scope == scope,
                SMQTerm.is_active == True
            ).all()

            # Filter reference terms down to sub-filter PTs
            ref_lookup = {st.pt_name_upper: st for st in smq_records if st.pt_name_upper in sub_pts}

            candidate_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name
            ).all()

            for ev, case in candidate_events:
                matched_ref = ref_lookup.get(ev.normalized_term)
                if matched_ref:
                    ev.preferred_term = matched_ref.pt_name
                    ev.pt_code = matched_ref.pt_code

                    matches_to_add.append(SearchMatch(
                        search_run_id=run_id,
                        concern_id=concern_id,
                        case_number=case.case_number,
                        event_id=ev.id,
                        search_method=method,
                        matched_field="SMQ + Sub-filter PT Lookup",
                        matched_term=matched_ref.pt_name,
                        pt_code=matched_ref.pt_code,
                        smq_name=smq_name,
                        smq_scope=scope,
                        reference_source=f"SMQ {smq_name} + Sub-filter PT: {matched_ref.pt_name}",
                        evidence=f"Event verbatim {ev.raw_verbatim} matched SMQ '{smq_name}' sub-filtered on PT '{matched_ref.pt_name}'",
                        source_file=ev.source_file or case.raw_source_file,
                        source_sheet=ev.source_sheet or case.raw_source_sheet,
                        source_row=ev.source_row or case.raw_source_row
                    ))

        elif method == "SOC":
            soc_name = config.get("soc_name", "").strip().lower()

            # Case-level primary SOC lookup from line listing
            # Deterministic comparison against actual line-listing SOC (no fuzzy keyword guessing)
            soc_cases = self.db.query(CaseRecord).filter(
                CaseRecord.product_name == concern.product_name,
                func.lower(CaseRecord.primary_soc) == soc_name
            ).all()

            for case in soc_cases:
                matches_to_add.append(SearchMatch(
                    search_run_id=run_id,
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=None,
                    search_method="SOC",
                    matched_field="Primary System Organ Class",
                    matched_term=case.primary_soc,
                    reference_source=f"MedDRA SOC: {config.get('soc_name')}",
                    evidence=f"Case primary SOC is '{case.primary_soc}'",
                    source_file=case.raw_source_file,
                    source_sheet=case.raw_source_sheet,
                    source_row=case.raw_source_row
                ))

            # Event-level SOC mapping support if explicit event SOC is recorded
            if config.get("include_event_level", False):
                ev_soc_matches = self.db.query(CaseEvent, CaseRecord).join(
                    CaseRecord, CaseEvent.case_number == CaseRecord.case_number
                ).filter(
                    CaseRecord.product_name == concern.product_name,
                    func.lower(CaseEvent.soc) == soc_name
                ).all()

                for ev, case in ev_soc_matches:
                    existing = any(m.case_number == case.case_number and m.event_id == ev.id for m in matches_to_add)
                    if not existing:
                        matches_to_add.append(SearchMatch(
                            search_run_id=run_id,
                            concern_id=concern_id,
                            case_number=case.case_number,
                            event_id=ev.id,
                            search_method="SOC_EVENT",
                            matched_field="Event System Organ Class",
                            matched_term=ev.soc or ev.normalized_term,
                            reference_source=f"Event SOC: {config.get('soc_name')}",
                            evidence=f"Event '{ev.normalized_term}' mapped to SOC '{ev.soc}' in verbatim: {ev.raw_verbatim}",
                            source_file=ev.source_file or case.raw_source_file,
                            source_sheet=ev.source_sheet or case.raw_source_sheet,
                            source_row=ev.source_row or case.raw_source_row
                        ))

        elif method in ("SINGLE_PT", "MULTIPLE_PTS"):
            pts = [config.get("pt")] if method == "SINGLE_PT" else config.get("pts", [])
            # Map uppercase -> display term
            configured_pt_map = {p.strip().upper(): p.strip() for p in pts if p and p.strip()}

            candidate_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name,
                CaseEvent.normalized_term.in_(list(configured_pt_map.keys()))
            ).all()

            for ev, case in candidate_events:
                matched_canonical = configured_pt_map.get(ev.normalized_term, ev.normalized_term)
                ev.preferred_term = matched_canonical

                matches_to_add.append(SearchMatch(
                    search_run_id=run_id,
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=ev.id,
                    search_method=method,
                    matched_field="Event Preferred Term (Configured PT List)",
                    matched_term=matched_canonical,
                    reference_source=f"Configured PT Criteria ({len(configured_pt_map)} terms)",
                    evidence=f"Exact match for configured PT '{matched_canonical}' in event verbatim: {ev.raw_verbatim}",
                    source_file=ev.source_file or case.raw_source_file,
                    source_sheet=ev.source_sheet or case.raw_source_sheet,
                    source_row=ev.source_row or case.raw_source_row
                ))

        elif method == "CONCOMITANT_INTERACTION":
            # Stage 1: Search configured interaction PTs
            initial_pts = [p.strip().upper() for p in config.get("initial_pts", [])]
            initial_map = {p.strip().upper(): p.strip() for p in config.get("initial_pts", [])}
            target_substances = [s.strip().lower() for s in config.get("target_substances", [])]

            matching_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name,
                CaseEvent.normalized_term.in_(initial_pts)
            ).all()

            for ev, case in matching_events:
                matched_pt_name = initial_map.get(ev.normalized_term, ev.normalized_term)
                ev.preferred_term = matched_pt_name

                # Stage 3 & 4: Inspect concomitant products for configured CYP2D6 terminology
                prods = self.db.query(CaseProduct).filter_by(case_number=case.case_number).all()
                matched_concom_drugs = []
                for p in prods:
                    act = (p.active_substance or "").lower()
                    brand = (p.brand_name or "").lower()
                    for target in target_substances:
                        if target in act or target in brand:
                            matched_concom_drugs.append(f"{p.brand_name or p.active_substance} ({p.role})")

                evidence_text = f"Interaction event matched: '{matched_pt_name}' in verbatim: {ev.raw_verbatim}."
                if matched_concom_drugs:
                    evidence_text += f" Concomitant CYP2D6 candidate drugs identified: {', '.join(set(matched_concom_drugs))}."
                else:
                    evidence_text += " No structured CYP2D6 inhibitor detected; requires clinical narrative review."

                matches_to_add.append(SearchMatch(
                    search_run_id=run_id,
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=ev.id,
                    search_method=method,
                    matched_field="Drug Interaction PT + Concomitant Review",
                    matched_term=matched_pt_name,
                    reference_source="CYP2D6 Multi-Level Interaction Criteria",
                    evidence=evidence_text,
                    source_file=ev.source_file or case.raw_source_file,
                    source_sheet=ev.source_sheet or case.raw_source_sheet,
                    source_row=ev.source_row or case.raw_source_row
                ))

        elif method == "NARRATIVE":
            keywords = [k.strip().lower() for k in config.get("keywords", [])]
            cases = self.db.query(CaseRecord).filter(
                CaseRecord.product_name == concern.product_name,
                CaseRecord.narrative.isnot(None)
            ).all()

            for case in cases:
                narr_lower = (case.narrative or "").lower()
                for kw in keywords:
                    if kw in narr_lower:
                        idx = narr_lower.find(kw)
                        start = max(0, idx - 80)
                        end = min(len(case.narrative), idx + len(kw) + 80)
                        snippet = "..." + case.narrative[start:end].replace("\n", " ").strip() + "..."

                        matches_to_add.append(SearchMatch(
                            search_run_id=run_id,
                            concern_id=concern_id,
                            case_number=case.case_number,
                            event_id=None,
                            search_method="NARRATIVE_SEARCH",
                            matched_field="Case Narrative Snippet",
                            matched_term=kw,
                            reference_source=f"Narrative keyword criterion: '{kw}'",
                            evidence=f"Clinical narrative snippet: '{snippet}'",
                            source_file=case.raw_source_file,
                            source_sheet=case.raw_source_sheet,
                            source_row=case.raw_source_row
                        ))
                        break  # One match per case for this narrative rule

        # Save matches
        if matches_to_add:
            self.db.bulk_save_objects(matches_to_add)
            self.db.commit()

        # Update SearchRun metrics
        matched_case_numbers = sorted(list(set(m.case_number for m in matches_to_add)))
        search_run.candidate_events_count = len(matches_to_add)
        search_run.distinct_cases_count = len(matched_case_numbers)
        self.db.commit()

        # Initialize/preserve Relevance Assessments
        # Important: If reviewer already assessed a case, PRESERVE their assessment!
        # If it's a new candidate case, initialize as "CANDIDATE"
        for c_num in matched_case_numbers:
            existing_ass = self.db.query(RelevanceAssessment).filter_by(
                case_number=c_num,
                concern_id=concern_id
            ).first()
            if not existing_ass:
                ass = RelevanceAssessment(
                    case_number=c_num,
                    concern_id=concern_id,
                    status="CANDIDATE",
                    reviewer_id=reviewer_id
                )
                self.db.add(ass)
        self.db.commit()

        # Audit trail logging
        audit = AuditLog(
            concern_id=concern_id,
            user_id=reviewer_id,
            action=f"Executed deterministic search run '{run_id}' for '{concern.name}': {len(matches_to_add)} candidate events across {len(matched_case_numbers)} distinct cases."
        )
        self.db.add(audit)
        self.db.commit()

        return self.get_search_summary(concern_id, search_run_id=run_id)

    def get_search_summary(self, concern_id: str, search_run_id: str = None):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        matches_query = self.db.query(SearchMatch).filter_by(concern_id=concern_id)
        if search_run_id:
            matches_query = matches_query.filter_by(search_run_id=search_run_id)
        matches = matches_query.all()

        distinct_cases = sorted(list(set(m.case_number for m in matches)))

        # Status counts from human relevance assessment
        assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=concern_id).all()
        ass_map = {a.case_number: a for a in assessments}

        # ONLY cases with status == "RELEVANT" are counted in relevant_count!
        # NEVER count CANDIDATE, NEEDS_REVIEW, or NOT_RELEVANT as relevant!
        relevant_count = sum(1 for c in distinct_cases if ass_map.get(c) and ass_map[c].status == "RELEVANT")
        not_relevant_count = sum(1 for c in distinct_cases if ass_map.get(c) and ass_map[c].status == "NOT_RELEVANT")
        needs_review_count = sum(1 for c in distinct_cases if ass_map.get(c) and ass_map[c].status == "NEEDS_REVIEW")
        candidate_count = sum(1 for c in distinct_cases if not ass_map.get(c) or ass_map[c].status == "CANDIDATE")

        # Build detailed candidate case rows
        case_rows = []
        for c_num in distinct_cases:
            case = self.db.query(CaseRecord).filter_by(case_number=c_num).first()
            case_matches = [m for m in matches if m.case_number == c_num]
            ass = ass_map.get(c_num)

            case_rows.append({
                "case_number": c_num,
                "country": case.country if case else "",
                "report_type": case.report_type if case else "",
                "product_name": case.product_name if case else "",
                "reporting_period": case.reporting_period if case else concern.reporting_period,
                "age": case.age if case else "",
                "sex": case.sex if case else "",
                "is_serious": case.is_serious if case else False,
                "listedness": case.listedness if case else "",
                "outcome": case.case_outcome if case else "",
                "initial_receipt_date": case.initial_receipt_date if case else "",
                "matches": [
                    {
                        "matched_field": m.matched_field,
                        "matched_term": m.matched_term,
                        "pt_code": m.pt_code,
                        "reference_source": m.reference_source,
                        "evidence": m.evidence,
                        "source_file": m.source_file,
                        "source_sheet": m.source_sheet,
                        "source_row": m.source_row
                    }
                    for m in case_matches
                ],
                "assessment_status": ass.status if ass else "CANDIDATE",
                "exclusion_reason": ass.exclusion_reason if ass else None,
                "reviewer_notes": ass.reviewer_notes if ass else None
            })

        return {
            "search_run_id": search_run_id,
            "concern_id": concern.id,
            "concern_name": concern.name,
            "category": concern.category,
            "search_method": concern.search_method,
            "reporting_period": concern.reporting_period,
            "total_event_matches": len(matches),
            "distinct_candidate_cases": len(distinct_cases),
            "relevant_cases_count": relevant_count,
            "not_relevant_cases_count": not_relevant_count,
            "needs_review_cases_count": needs_review_count,
            "candidate_pending_count": candidate_count,
            "cases": case_rows
        }
