import json
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from excel_calculus.backend.app.models.entities import (
    SafetyConcern, CaseRecord, CaseEvent, CaseProduct, 
    SMQTerm, SearchMatch, RelevanceAssessment, AuditLog
)

class SearchEngineService:
    def __init__(self, db: Session):
        self.db = db

    def execute_concern_search(self, concern_id: str, reviewer_id: str = "system"):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        config = json.loads(concern.search_config) if concern.search_config else {}
        method = concern.search_method

        # Clear existing matches for this concern to maintain reproducibility
        self.db.query(SearchMatch).filter_by(concern_id=concern_id).delete()

        matches_to_add = []

        if method in ("BROAD_SMQ", "NARROW_SMQ"):
            smq_name = config.get("smq_name")
            scope = config.get("scope", "Broad")
            
            # Fetch all PT uppercase terms for this SMQ & Scope
            smq_pts = self.db.query(SMQTerm.pt_name_upper).filter(
                SMQTerm.smq_name == smq_name,
                SMQTerm.scope == scope
            ).scalar_subquery()

            # Join CaseEvent with SMQ terms, scoped to product
            matching_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name,
                CaseEvent.normalized_term.in_(smq_pts)
            ).all()

            for ev, case in matching_events:
                matches_to_add.append(SearchMatch(
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=ev.id,
                    search_method=method,
                    matched_field="Event Preferred Term",
                    matched_term=ev.preferred_term,
                    reference_source=f"{scope} SMQ: {smq_name}",
                    evidence=f"Matched term '{ev.preferred_term}' in raw verbatim: [{ev.raw_verbatim}]"
                ))

        elif method == "SOC":
            soc_name = config.get("soc_name", "").lower()
            include_event = config.get("include_event_level", True)

            # Match on case-level primary SOC scoped to product
            soc_cases = self.db.query(CaseRecord).filter(
                CaseRecord.product_name == concern.product_name,
                func.lower(CaseRecord.primary_soc).contains(soc_name)
            ).all()

            for case in soc_cases:
                matches_to_add.append(SearchMatch(
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=None,
                    search_method="SOC",
                    matched_field="System Organ Class",
                    matched_term=case.primary_soc,
                    reference_source=f"SOC: {config.get('soc_name')}",
                    evidence=f"Case primary SOC is '{case.primary_soc}'"
                ))

            if include_event:
                # Also check events with cardiac terms scoped to product
                cardiac_keywords = ["cardiac", "arrhythmia", "infarction", "tachycardia", "atrial fibrillation", "angina", "heart"]
                for kw in cardiac_keywords:
                    ev_matches = self.db.query(CaseEvent, CaseRecord).join(
                        CaseRecord, CaseEvent.case_number == CaseRecord.case_number
                    ).filter(
                        CaseRecord.product_name == concern.product_name,
                        func.lower(CaseEvent.normalized_term).contains(kw)
                    ).all()
                    for ev, case in ev_matches:
                        # Avoid duplicates
                        existing = any(m.case_number == case.case_number and m.event_id == ev.id for m in matches_to_add)
                        if not existing:
                            matches_to_add.append(SearchMatch(
                                concern_id=concern_id,
                                case_number=case.case_number,
                                event_id=ev.id,
                                search_method="SOC_EVENT",
                                matched_field="Event Term",
                                matched_term=ev.preferred_term,
                                reference_source=f"Cardiac event keyword '{kw}'",
                                evidence=f"Event '{ev.preferred_term}' matched cardiac criteria in verbatim: [{ev.raw_verbatim}]"
                            ))

        elif method in ("SINGLE_PT", "MULTIPLE_PTS"):
            pts = [config.get("pt")] if method == "SINGLE_PT" else config.get("pts", [])
            pts_upper = [p.strip().upper() for p in pts if p]

            matching_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name,
                CaseEvent.normalized_term.in_(pts_upper)
            ).all()

            for ev, case in matching_events:
                matches_to_add.append(SearchMatch(
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=ev.id,
                    search_method=method,
                    matched_field="Event Preferred Term",
                    matched_term=ev.preferred_term,
                    reference_source=f"Configured PT Criteria ({len(pts_upper)} terms)",
                    evidence=f"Event '{ev.preferred_term}' matched configured PT criteria in verbatim: [{ev.raw_verbatim}]"
                ))

        elif method == "CONCOMITANT_INTERACTION":
            initial_pts = [p.strip().upper() for p in config.get("initial_pts", [])]
            target_substances = [s.strip().lower() for s in config.get("target_substances", [])]

            matching_events = self.db.query(CaseEvent, CaseRecord).join(
                CaseRecord, CaseEvent.case_number == CaseRecord.case_number
            ).filter(
                CaseRecord.product_name == concern.product_name,
                CaseEvent.normalized_term.in_(initial_pts)
            ).all()

            for ev, case in matching_events:
                # Inspect products on this case
                prods = self.db.query(CaseProduct).filter_by(case_number=case.case_number).all()
                matched_prods = []
                for p in prods:
                    act = (p.active_substance or "").lower()
                    brand = (p.brand_name or "").lower()
                    for target in target_substances:
                        if target in act or target in brand:
                            matched_prods.append(f"{p.brand_name} ({p.role})")

                evidence_text = f"Event '{ev.preferred_term}' matched interaction PT criteria."
                if matched_prods:
                    evidence_text += f" Concomitant CYP2D6 candidate drugs identified: {', '.join(matched_prods)}."
                else:
                    evidence_text += " No pre-flagged CYP2D6 inhibitor detected in structured product list (requires narrative review)."

                matches_to_add.append(SearchMatch(
                    concern_id=concern_id,
                    case_number=case.case_number,
                    event_id=ev.id,
                    search_method=method,
                    matched_field="Drug Interaction PT + Concomitant Review",
                    matched_term=ev.preferred_term,
                    reference_source="CYP2D6 Multi-Level Criteria",
                    evidence=evidence_text
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
                        snippet = "..." + case.narrative[start:end].replace("\n", " ") + "..."

                        matches_to_add.append(SearchMatch(
                            concern_id=concern_id,
                            case_number=case.case_number,
                            event_id=None,
                            search_method="NARRATIVE_SEARCH",
                            matched_field="Case Narrative",
                            matched_term=kw,
                            reference_source=f"Keyword '{kw}' in Narrative",
                            evidence=f"Narrative evidence: '{snippet}'"
                        ))
                        break # One match per case for this concern is sufficient

        # Save matches
        if matches_to_add:
            self.db.bulk_save_objects(matches_to_add)
            self.db.commit()

        # Initialize/preserve Relevance Assessments
        matched_case_numbers = sorted(list(set(m.case_number for m in matches_to_add)))
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

        # Log audit trail
        audit = AuditLog(
            concern_id=concern_id,
            user_id=reviewer_id,
            action=f"Executed search for '{concern.name}': found {len(matches_to_add)} matching events across {len(matched_case_numbers)} distinct cases."
        )
        self.db.add(audit)
        self.db.commit()

        return self.get_search_summary(concern_id)

    def get_search_summary(self, concern_id: str):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        matches = self.db.query(SearchMatch).filter_by(concern_id=concern_id).all()
        distinct_cases = sorted(list(set(m.case_number for m in matches)))

        # Status counts
        assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=concern_id).all()
        ass_map = {a.case_number: a for a in assessments}

        relevant_count = sum(1 for a in assessments if a.status == "RELEVANT")
        not_relevant_count = sum(1 for a in assessments if a.status == "NOT_RELEVANT")
        needs_review_count = sum(1 for a in assessments if a.status == "NEEDS_REVIEW")
        candidate_count = sum(1 for a in assessments if a.status == "CANDIDATE")

        # Build detailed case rows
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
                        "reference_source": m.reference_source,
                        "evidence": m.evidence
                    }
                    for m in case_matches
                ],
                "assessment_status": ass.status if ass else "CANDIDATE",
                "exclusion_reason": ass.exclusion_reason if ass else None,
                "reviewer_notes": ass.reviewer_notes if ass else None
            })

        return {
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
