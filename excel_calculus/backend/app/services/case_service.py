from datetime import datetime
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import (
    CaseRecord, CaseEvent, CaseProduct, SearchMatch, RelevanceAssessment, AuditLog, SafetyConcern
)

class CaseService:
    def __init__(self, db: Session):
        self.db = db

    def get_complete_case(self, case_number: str, concern_id: str = None):
        case = self.db.query(CaseRecord).filter_by(case_number=case_number).first()
        if not case:
            raise ValueError(f"Case not found: {case_number}")

        # Fetch events
        events = self.db.query(CaseEvent).filter_by(case_number=case_number).order_by(CaseEvent.position).all()

        # Fetch products
        products = self.db.query(CaseProduct).filter_by(case_number=case_number).all()

        # Fetch matches for this case (optionally filtered by concern)
        match_query = self.db.query(SearchMatch).filter_by(case_number=case_number)
        if concern_id:
            match_query = match_query.filter_by(concern_id=concern_id)
        matches = match_query.all()
        matched_event_ids = {m.event_id for m in matches if m.event_id is not None}
        matched_terms = {m.matched_term.upper() for m in matches if m.matched_term}

        # Build events list with match flagging
        events_data = []
        for ev in events:
            is_matched = (ev.id in matched_event_ids) or (ev.normalized_term in matched_terms)
            ev_matches = [m for m in matches if m.event_id == ev.id or m.matched_term.upper() == ev.normalized_term]
            
            events_data.append({
                "id": ev.id,
                "position": ev.position,
                "raw_verbatim": ev.raw_verbatim,
                "normalized_term": ev.normalized_term,
                "preferred_term": ev.preferred_term,
                "soc": ev.soc,
                "outcome": ev.event_outcome,
                "seriousness": ev.seriousness_flag,
                "listedness": ev.listedness_flag,
                "causality": ev.causality_flag,
                "is_matched": is_matched,
                "match_reason": ev_matches[0].reference_source if ev_matches else None
            })

        # Build products list
        products_data = [
            {
                "id": p.id,
                "product_name_raw": p.product_name_raw,
                "brand_name": p.brand_name,
                "active_substance": p.active_substance,
                "role": p.role,
                "is_suspect": (p.role or "").lower() == "suspect"
            }
            for p in products
        ]

        # Fetch assessment for this concern
        assessment = None
        if concern_id:
            ass_rec = self.db.query(RelevanceAssessment).filter_by(
                case_number=case_number,
                concern_id=concern_id
            ).first()
            if ass_rec:
                assessment = {
                    "status": ass_rec.status,
                    "exclusion_reason": ass_rec.exclusion_reason,
                    "reviewer_notes": ass_rec.reviewer_notes,
                    "secondary_assessment_result": ass_rec.secondary_assessment_result,
                    "reviewer_id": ass_rec.reviewer_id,
                    "updated_at": ass_rec.updated_at.isoformat() if ass_rec.updated_at else None
                }

        # Audit logs for this case
        logs = self.db.query(AuditLog).filter_by(case_number=case_number).order_by(AuditLog.timestamp.desc()).all()
        audit_data = [
            {
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "user_id": l.user_id,
                "action": l.action,
                "previous_state": l.previous_state,
                "new_state": l.new_state
            }
            for l in logs
        ]

        return {
            "case_number": case.case_number,
            "overview": {
                "product_name": case.product_name,
                "country": case.country,
                "report_type": case.report_type,
                "initial_receipt_date": case.initial_receipt_date,
                "is_serious": case.is_serious,
                "seriousness_raw": case.seriousness_raw,
                "listedness": case.listedness,
                "case_outcome": case.case_outcome,
                "primary_soc": case.primary_soc,
                "case_classification": case.case_classification,
                "follow_up": case.follow_up
            },
            "patient": {
                "age": case.age,
                "sex": case.sex,
                "relevant_history": case.relevant_history,
                "death_cause": case.death_cause
            },
            "products": products_data,
            "events": events_data,
            "narrative": case.narrative,
            "comments": case.case_comments,
            "source_lineage": {
                "file": case.raw_source_file,
                "sheet": case.raw_source_sheet,
                "row": case.raw_source_row
            },
            "assessment": assessment,
            "audit_trail": audit_data,
            "matches": [
                {
                    "field": m.matched_field,
                    "term": m.matched_term,
                    "source": m.reference_source,
                    "evidence": m.evidence
                }
                for m in matches
            ]
        }

    def update_assessment(self, case_number: str, concern_id: str, status: str, 
                          exclusion_reason: str = None, reviewer_notes: str = None, 
                          secondary_result: str = None, reviewer_id: str = "reviewer"):
        ass = self.db.query(RelevanceAssessment).filter_by(
            case_number=case_number,
            concern_id=concern_id
        ).first()

        prev_status = ass.status if ass else "NEW"

        if not ass:
            ass = RelevanceAssessment(
                case_number=case_number,
                concern_id=concern_id
            )
            self.db.add(ass)

        ass.status = status
        ass.exclusion_reason = exclusion_reason
        ass.reviewer_notes = reviewer_notes
        ass.secondary_assessment_result = secondary_result
        ass.reviewer_id = reviewer_id
        ass.updated_at = datetime.utcnow()

        audit = AuditLog(
            case_number=case_number,
            concern_id=concern_id,
            user_id=reviewer_id,
            action=f"Changed assessment status for case {case_number} to {status}",
            previous_state=prev_status,
            new_state=status
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "case_number": case_number,
            "concern_id": concern_id,
            "status": status,
            "exclusion_reason": exclusion_reason,
            "reviewer_notes": reviewer_notes,
            "secondary_result": secondary_result
        }
