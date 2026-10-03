from collections import Counter
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import (
    SafetyConcern, CaseRecord, SearchRun, SearchMatch, RelevanceAssessment
)
from excel_calculus.backend.app.services.pdf_service import PDFReportService

class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def generate_pbrer_section_report(self, concern_id: str):
        concern = self.db.query(SafetyConcern).filter_by(id=concern_id).first()
        if not concern:
            raise ValueError(f"Safety Concern not found: {concern_id}")

        # Retrieve matches from the active/latest SearchRun
        latest_run = self.db.query(SearchRun).filter_by(concern_id=concern_id, is_active=True).order_by(SearchRun.execution_time.desc()).first()
        if not latest_run:
            latest_run = self.db.query(SearchRun).filter_by(concern_id=concern_id).order_by(SearchRun.execution_time.desc()).first()

        matches = self.db.query(SearchMatch).filter_by(search_run_id=latest_run.id).all() if latest_run else self.db.query(SearchMatch).filter_by(concern_id=concern_id).all()
        distinct_case_nums = sorted(list(set(m.case_number for m in matches)))

        assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=concern_id).all()
        ass_map = {a.case_number: a for a in assessments}

        cases = self.db.query(CaseRecord).filter(CaseRecord.case_number.in_(distinct_case_nums)).all()
        cases_map = {c.case_number: c for c in cases}

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
                "case_id": case.id if case else None,
                "case_number": c_num,
                "country": case.country if case else "",
                "report_type": case.report_type if case else "",
                "product_name": case.product_name if case else "",
                "reporting_period": case.reporting_period if case else concern.reporting_period,
                "age": case.age if case else "",
                "sex": case.sex if case else "",
                "is_serious": case.is_serious if case else False,
                "outcome": case.case_outcome if case else "",
                "initial_receipt_date": case.initial_receipt_date if case else "",
                "matches": [
                    {
                        "matched_field": m.matched_field,
                        "matched_term": m.matched_term,
                        "pt_code": m.pt_code,
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

            if status == "RELEVANT":
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

        target_pt_cases = relevant_cases if len(relevant_cases) > 0 else pending_cases
        display_counter = Counter()
        for ci in target_pt_cases:
            for term in ci["matched_terms"]:
                display_counter[term] += 1

        pt_summary_table = [
            {"preferred_term": pt, "case_count": count}
            for pt, count in display_counter.most_common()
        ]

        clinical_narrative_summary = (
            f"During the review period ({concern.reporting_period}), the MAH retrieved {len(distinct_case_nums)} "
            f"candidate case reports pertaining to the safety concern of '{concern.name}' using {concern.search_method} "
            f"({concern.description or ''}). "
            f"Following clinical relevance assessment, {len(relevant_cases)} distinct cases were confirmed to be relevant "
            f"({serious_count} serious, {fatal_count} fatal). "
            f"{len(excluded_cases)} cases were determined to be not relevant following clinical evaluation. "
            f"There are currently {len(pending_cases)} candidate cases awaiting review. "
            f"The events were categorized across {len(pt_summary_table)} Preferred Terms: "
            + (", ".join([f"{item['preferred_term']} ({item['case_count']})" for item in pt_summary_table]) if pt_summary_table else "None")
            + ". Based on the evaluation of these cases, no new safety signals or modifications to the product benefit-risk profile were established."
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
                "relevant_case_count": len(relevant_cases),  # Strict count of RELEVANT distinct cases
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
        """
        Generates the master PBRER Section 16.1 Summary of Safety Concerns table.
        Rule:
        - Number of Relevant Case Reports must be COUNT(DISTINCT Case Number WHERE status = 'RELEVANT')
        - Never count candidate cases as relevant
        - Never hard-code counts
        - Categories strictly: Important Identified Risks, Important Potential Risks, Missing Information
        """
        concerns = self.db.query(SafetyConcern).filter_by(product_name=product_name).all()
        if not concerns:
            concerns = self.db.query(SafetyConcern).all()

        reporting_period = concerns[0].reporting_period if concerns else "Current Reporting Period"

        categories_order = [
            "Important Identified Risks",
            "Important Potential Risks",
            "Missing Information"
        ]

        category_map = {cat: [] for cat in categories_order}
        total_relevant = 0
        total_candidate = 0

        for c in concerns:
            c_cat_lower = (c.category or "").lower()
            if "section 9" in c_cat_lower:
                continue

            if c.category in category_map:
                cat = c.category
            elif "potential" in c_cat_lower:
                cat = "Important Potential Risks"
            elif "missing" in c_cat_lower:
                cat = "Missing Information"
            elif "identified" in c_cat_lower:
                cat = "Important Identified Risks"
            else:
                continue

            # Query matches from the active/latest SearchRun
            latest_run = self.db.query(SearchRun).filter_by(concern_id=c.id, is_active=True).order_by(SearchRun.execution_time.desc()).first()
            if not latest_run:
                latest_run = self.db.query(SearchRun).filter_by(concern_id=c.id).order_by(SearchRun.execution_time.desc()).first()

            if latest_run:
                matches = self.db.query(SearchMatch).filter_by(search_run_id=latest_run.id).all()
            else:
                matches = self.db.query(SearchMatch).filter_by(concern_id=c.id).all()

            distinct_cases = sorted(list(set(m.case_number for m in matches)))

            assessments = self.db.query(RelevanceAssessment).filter_by(concern_id=c.id).all()
            ass_map = {a.case_number: a.status for a in assessments}

            relevant_count = 0
            excluded_count = 0
            needs_review_count = 0
            pending_count = 0

            for c_num in distinct_cases:
                st = ass_map.get(c_num, "CANDIDATE")
                if st == "RELEVANT":
                    relevant_count += 1
                elif st == "NOT_RELEVANT":
                    excluded_count += 1
                elif st == "NEEDS_REVIEW":
                    needs_review_count += 1
                else:
                    pending_count += 1

            total_relevant += relevant_count
            total_candidate += len(distinct_cases)

            category_map[cat].append({
                "concern_id": c.id,
                "risk_term": c.name,
                "category": cat,
                "search_method": c.search_method,
                "search_criteria": c.description,
                "number_of_relevant_cases": relevant_count,  # STRICTLY RELEVANT COUNT
                "candidate_case_count": len(distinct_cases),
                "excluded_count": excluded_count,
                "needs_review_count": needs_review_count,
                "pending_count": pending_count,
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

    def generate_section_16_1_pdf(self, product_name: str) -> bytes:
        """
        Generates official regulatory PBRER Section 16.1 PDF from current database data.
        """
        table_data = self.generate_section_16_1_table(product_name=product_name)
        pdf_service = PDFReportService(self.db)
        return pdf_service.generate_section_16_1_pdf(table_data)
