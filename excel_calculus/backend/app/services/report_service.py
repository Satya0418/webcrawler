from collections import Counter
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import (
    SafetyConcern, CaseRecord, SearchMatch, RelevanceAssessment
)

class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def generate_pbrer_section_report(self, concern_id: str):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        matches = self.db.query(SearchMatch).filter_by(concern_id=concern_id).all()
        distinct_case_nums = sorted(list(set(m.case_number for m in matches)))

        assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=concern_id).all()
        ass_map = {a.case_number: a for a in assessments}

        cases = self.db.query(CaseRecord).filter(CaseRecord.case_number.in_(distinct_case_nums)).all()
        cases_map = {c.case_number: c for c in cases}

        # Segregate relevant vs excluded vs pending
        relevant_cases = []
        excluded_cases = []
        pending_cases = []

        pt_counter = Counter()
        fatal_count = 0
        serious_count = 0

        for c_num in distinct_case_nums:
            case = cases_map.get(c_num)
            ass = ass_map.get(c_num)
            c_matches = [m for m in matches if m.case_number == c_num]

            status = ass.status if ass else "CANDIDATE"

            case_item = {
                "case_number": c_num,
                "country": case.country if case else "",
                "report_type": case.report_type if case else "",
                "product_name": case.product_name if case else "",
                "age": case.age if case else "",
                "sex": case.sex if case else "",
                "is_serious": case.is_serious if case else False,
                "outcome": case.case_outcome if case else "",
                "initial_receipt_date": case.initial_receipt_date if case else "",
                "matches": [
                    {
                        "matched_field": m.matched_field,
                        "matched_term": m.matched_term,
                        "reference_source": m.reference_source,
                        "evidence": m.evidence
                    }
                    for m in c_matches
                ],
                "matched_terms": list(set(m.matched_term for m in c_matches)),
                "evidence": [m.evidence for m in c_matches],
                "assessment_status": status,
                "exclusion_reason": ass.exclusion_reason if ass else None,
                "reviewer_notes": ass.reviewer_notes if ass else None,
                "secondary_result": ass.secondary_assessment_result if ass else None
            }

            if status == "RELEVANT" or (status == "CANDIDATE" and not any(a.status == "NOT_RELEVANT" for a in [ass] if ass)):
                # Default candidate or confirmed relevant
                relevant_cases.append(case_item)
                for term in case_item["matched_terms"]:
                    pt_counter[term] += 1
                if case and case.is_serious:
                    serious_count += 1
                if case and case.case_outcome and "fatal" in case.case_outcome.lower():
                    fatal_count += 1
            elif status == "NOT_RELEVANT":
                excluded_cases.append(case_item)
            else:
                pending_cases.append(case_item)

        # Tabular summary of Preferred Terms
        pt_summary_table = [
            {"preferred_term": pt, "case_count": count}
            for pt, count in pt_counter.most_common()
        ]

        # Clinical summary text template
        clinical_narrative_summary = (
            f"During the review period ({concern.reporting_period}), the MAH retrieved {len(distinct_case_nums)} "
            f"candidate case reports pertaining to the risk of {concern.name.lower()} using {concern.search_method} "
            f"({concern.description}). "
            f"Following clinical relevance assessment, {len(relevant_cases)} cases were determined to be relevant "
            f"({serious_count} serious, {fatal_count} associated with a fatal outcome). "
            f"The events were categorized across {len(pt_summary_table)} Preferred Terms: "
            + ", ".join([f"{item['preferred_term']} ({item['case_count']})" for item in pt_summary_table])
            + ". Based on the review of these case reports, no new significant safety signals or changes in the benefit-risk balance were identified."
        )

        return {
            "metadata": {
                "product_name": concern.product_name,
                "reporting_period": concern.reporting_period,
                "safety_concern": concern.name,
                "category": concern.category,
                "search_criteria": concern.description,
                "search_method": concern.search_method
            },
            "metrics": {
                "candidate_case_count": len(distinct_case_nums),
                "total_event_matches": len(matches),
                "relevant_case_count": len(relevant_cases),
                "excluded_case_count": len(excluded_cases),
                "pending_review_count": len(pending_cases),
                "serious_count": serious_count,
                "fatal_count": fatal_count
            },
            "pt_summary_table": pt_summary_table,
            "clinical_narrative_summary": clinical_narrative_summary,
            "relevant_cases": relevant_cases,
            "excluded_cases": excluded_cases,
            "pending_cases": pending_cases
        }

    def generate_section_16_1_table(self, product_name: str):
        concerns = self.db.query(SafetyConcern).filter_by(product_name=product_name).all()
        if not concerns:
            concerns = self.db.query(SafetyConcern).all()

        reporting_period = concerns[0].reporting_period if concerns else "Current Period"

        categories_order = [
            "Important Identified Risks",
            "Important Potential Risks",
            "Missing Information"
        ]

        category_map = {cat: [] for cat in categories_order}
        total_relevant = 0
        total_candidate = 0

        for c in concerns:
            cat = c.category if c.category in category_map else "Important Identified Risks"
            matches = self.db.query(SearchMatch).filter_by(concern_id=c.id).all()
            distinct_cases = sorted(list(set(m.case_number for m in matches)))

            assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=c.id).all()
            ass_map = {a.case_number: a.status for a in assessments}

            relevant_count = 0
            excluded_count = 0
            needs_review_count = 0

            for c_num in distinct_cases:
                st = ass_map.get(c_num, "CANDIDATE")
                if st == "RELEVANT" or st == "CANDIDATE":
                    relevant_count += 1
                elif st == "NOT_RELEVANT":
                    excluded_count += 1
                elif st == "NEEDS_REVIEW":
                    needs_review_count += 1

            total_relevant += relevant_count
            total_candidate += len(distinct_cases)

            category_map[cat].append({
                "concern_id": c.id,
                "risk_term": c.name,
                "category": cat,
                "search_method": c.search_method,
                "search_criteria": c.description,
                "number_of_relevant_cases": relevant_count,
                "candidate_case_count": len(distinct_cases),
                "excluded_count": excluded_count,
                "needs_review_count": needs_review_count,
                "requires_secondary_assessment": c.requires_secondary_assessment
            })

        table_sections = []
        for cat in categories_order:
            if category_map[cat]:
                table_sections.append({
                    "category_name": cat,
                    "risks": category_map[cat]
                })

        return {
            "title": "Section 16.1 Summary of Safety Concerns",
            "product_name": product_name,
            "reporting_period": reporting_period,
            "intro_text": "The number of case reports received by the MAH pertaining to the above mentioned safety concerns are presented in the table below.",
            "total_relevant_cases": total_relevant,
            "total_candidate_cases": total_candidate,
            "table_sections": table_sections
        }
