import os
import re
import openpyxl
from datetime import datetime
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import CaseRecord, CaseEvent, CaseProduct, AuditLog

class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def clean_xml_hex(val: str) -> str:
        if not val:
            return ""
        return re.sub(r"_x[0-9a-fA-F]{4}_", "", str(val))

    @staticmethod
    def normalize_term(val: str) -> str:
        if not val:
            return ""
        # Remove extra whitespace and newlines
        clean = re.sub(r"[\r\n\t]+", " ", str(val))
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def parse_event_verbatim(self, raw_ev: str):
        """
        Parses multi-event verbatim text, e.g.:
        [PAIN IN EXTREMITY_x0015__x0016_]_x000D_
        Y / Y / Y_x000D_
        [GAIT DISTURBANCE_x0016_]...
        Returns list of dicts: [{'term': 'PAIN IN EXTREMITY', 'raw': '...', 'flags': 'Y/Y/Y'}]
        """
        if not raw_ev:
            return []

        cleaned_text = self.clean_xml_hex(raw_ev)
        
        # Regex to capture bracketed term and optional trailing assessment flags
        pattern = re.compile(r'\[([^\]]+)\](?:\s*([YyNn\s/]+))?')
        matches = pattern.findall(cleaned_text)
        
        events = []
        if matches:
            for term, flags in matches:
                clean_t = self.normalize_term(term)
                clean_flags = self.normalize_term(flags) if flags else ""
                if clean_t:
                    flag_parts = [f.strip() for f in clean_flags.split("/") if f.strip()]
                    seriousness = flag_parts[0] if len(flag_parts) > 0 else None
                    listedness = flag_parts[1] if len(flag_parts) > 1 else None
                    causality = flag_parts[2] if len(flag_parts) > 2 else None
                    
                    events.append({
                        "term": clean_t,
                        "raw": term,
                        "seriousness": seriousness,
                        "listedness": listedness,
                        "causality": causality
                    })
        else:
            # Fallback if not enclosed in brackets
            lines = [self.normalize_term(l) for l in cleaned_text.splitlines() if self.normalize_term(l)]
            for l in lines:
                if not re.match(r'^[YyNn\s/]+$', l): # not just flags
                    events.append({
                        "term": l,
                        "raw": l,
                        "seriousness": None,
                        "listedness": None,
                        "causality": None
                    })
        return events

    def parse_outcomes(self, raw_outcomes: str):
        """
        Parses 'Outcome of Event' column, e.g.:
        Pain in extremity - Unknown
        Gait disturbance - Fatal
        """
        if not raw_outcomes:
            return {}
        cleaned = self.clean_xml_hex(raw_outcomes)
        outcomes_map = {}
        for line in cleaned.splitlines():
            line_clean = self.normalize_term(line)
            if " - " in line_clean:
                parts = line_clean.split(" - ", 1)
                term = parts[0].strip().upper()
                outcomes_map[term] = parts[1].strip()
        return outcomes_map

    def parse_products(self, raw_products: str):
        """
        Parses 'Product Name' column, e.g.:
        PREDNISONE (PREDNISONE) Suspect, Unknown, Unknown
        APO DEXAMETHASONE (DEXAMETHASONE) Concom, daily dose: .5milligram...
        """
        if not raw_products:
            return []
        cleaned = self.clean_xml_hex(raw_products)
        products = []
        for line in cleaned.splitlines():
            line_clean = self.normalize_term(line)
            if not line_clean:
                continue
            
            # Extract role (Suspect vs Concom)
            role = "Suspect" if "suspect" in line_clean.lower() else ("Concom" if "concom" in line_clean.lower() else "Unknown")
            
            # Active substance in parentheses e.g. APO DEXAMETHASONE (DEXAMETHASONE)
            active_sub = None
            paren_match = re.search(r'\(([^)]+)\)', line_clean)
            if paren_match:
                active_sub = paren_match.group(1).strip()
            
            # Brand name before parenthesis
            brand = line_clean.split("(")[0].strip() if paren_match else line_clean.split()[0]
            
            products.append({
                "raw": line_clean,
                "brand": brand,
                "active_substance": active_sub or brand,
                "role": role
            })
        return products

    def ingest_linelisting_file(self, file_path: str, primary_product_name: str = "Unknown"):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_name = wb.sheetnames[0]
        ws = wb[sheet_name]

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"status": "empty", "cases": 0, "events": 0}

        headers = [str(c).strip() if c is not None else "" for c in rows[0]]
        
        # Build index mapping
        def col_idx(name):
            return headers.index(name) if name in headers else -1

        idx_case = col_idx("Case Number")
        idx_soc = col_idx("System Organ Class")
        idx_primary_ev = col_idx("Primary Event")
        idx_prev_sub = col_idx("Previous Submission")
        idx_country = col_idx("Country")
        idx_report_type = col_idx("Report Type")
        idx_age = col_idx("Age")
        idx_sex = col_idx("Sex")
        idx_ev = col_idx("Event Verbatim")
        idx_outcome = col_idx("Outcome")
        idx_outcome_ev = col_idx("Outcome of Event")
        idx_hcp = col_idx("Health Care Prof.")
        idx_non_ser_list = col_idx("Non-Serious Listed")
        idx_followup = col_idx("FollowUp")
        idx_receipt_date = col_idx("Case Initial Receipt Date")
        idx_narrative = col_idx("Case Narrative")
        idx_seriousness = col_idx("Case Seriousness?")
        idx_prod = col_idx("Product Name")
        idx_listedness = col_idx("Case Listedness")
        idx_classification = col_idx("Case Classification")
        idx_history = col_idx("Relevant History Sort Order")
        idx_death_cause = col_idx("Death Cause")
        idx_comments = col_idx("Report Comment")

        total_cases = 0
        total_events = 0
        total_products = 0

        for r_idx, row in enumerate(rows[1:], start=2):
            if idx_case < 0 or r_idx - 2 >= len(rows) - 1:
                break
            case_num = str(row[idx_case]).strip() if (row[idx_case] is not None and str(row[idx_case]).strip()) else None
            if not case_num or case_num.lower() == "case number":
                continue

            raw_ev = str(row[idx_ev]) if (idx_ev >= 0 and row[idx_ev] is not None) else ""
            raw_outcome_ev = str(row[idx_outcome_ev]) if (idx_outcome_ev >= 0 and row[idx_outcome_ev] is not None) else ""
            raw_prod = str(row[idx_prod]) if (idx_prod >= 0 and row[idx_prod] is not None) else ""

            # Check if case exists, otherwise create
            case_rec = self.db.query(CaseRecord).filter_by(case_number=case_num).first()
            if not case_rec:
                case_rec = CaseRecord(case_number=case_num)
                self.db.add(case_rec)

            seriousness_val = str(row[idx_seriousness]).strip() if (idx_seriousness >= 0 and row[idx_seriousness] is not None) else ""
            
            case_rec.product_name = primary_product_name
            case_rec.primary_product = primary_product_name
            case_rec.country = str(row[idx_country]).strip() if (idx_country >= 0 and row[idx_country] is not None) else ""
            case_rec.report_type = str(row[idx_report_type]).strip() if (idx_report_type >= 0 and row[idx_report_type] is not None) else ""
            case_rec.age = str(row[idx_age]).strip() if (idx_age >= 0 and row[idx_age] is not None) else ""
            case_rec.sex = str(row[idx_sex]).strip() if (idx_sex >= 0 and row[idx_sex] is not None) else ""
            case_rec.initial_receipt_date = str(row[idx_receipt_date]).strip() if (idx_receipt_date >= 0 and row[idx_receipt_date] is not None) else ""
            case_rec.is_serious = (seriousness_val.lower() == "yes")
            case_rec.seriousness_raw = seriousness_val
            case_rec.listedness = str(row[idx_listedness]).strip() if (idx_listedness >= 0 and row[idx_listedness] is not None) else ""
            case_rec.case_outcome = str(row[idx_outcome]).strip() if (idx_outcome >= 0 and row[idx_outcome] is not None) else ""
            case_rec.primary_soc = str(row[idx_soc]).strip() if (idx_soc >= 0 and row[idx_soc] is not None) else ""
            case_rec.primary_event_flag = str(row[idx_primary_ev]).strip() if (idx_primary_ev >= 0 and row[idx_primary_ev] is not None) else ""
            case_rec.previous_submission = str(row[idx_prev_sub]).strip() if (idx_prev_sub >= 0 and row[idx_prev_sub] is not None) else ""
            case_rec.healthcare_prof = str(row[idx_hcp]).strip() if (idx_hcp >= 0 and row[idx_hcp] is not None) else ""
            case_rec.non_serious_listed = str(row[idx_non_ser_list]).strip() if (idx_non_ser_list >= 0 and row[idx_non_ser_list] is not None) else ""
            case_rec.follow_up = str(row[idx_followup]).strip() if (idx_followup >= 0 and row[idx_followup] is not None) else ""
            case_rec.case_classification = str(row[idx_classification]).strip() if (idx_classification >= 0 and row[idx_classification] is not None) else ""
            case_rec.relevant_history = self.clean_xml_hex(str(row[idx_history])) if (idx_history >= 0 and row[idx_history] is not None) else ""
            case_rec.narrative = self.clean_xml_hex(str(row[idx_narrative])) if (idx_narrative >= 0 and row[idx_narrative] is not None) else ""
            case_rec.death_cause = str(row[idx_death_cause]).strip() if (idx_death_cause >= 0 and row[idx_death_cause] is not None) else ""
            case_rec.case_comments = str(row[idx_comments]).strip() if (idx_comments >= 0 and row[idx_comments] is not None) else ""
            case_rec.raw_source_file = file_name
            case_rec.raw_source_sheet = sheet_name
            case_rec.raw_source_row = r_idx

            # Clear existing child records if re-ingesting
            self.db.query(CaseEvent).filter_by(case_number=case_num).delete()
            self.db.query(CaseProduct).filter_by(case_number=case_num).delete()

            # Explode events
            parsed_events = self.parse_event_verbatim(raw_ev)
            outcomes_map = self.parse_outcomes(raw_outcome_ev)

            for pos, ev_item in enumerate(parsed_events):
                clean_term = ev_item["term"]
                norm_upper = clean_term.upper()
                pref_title = clean_term.title()
                
                # Check outcome match
                matched_outcome = outcomes_map.get(norm_upper, case_rec.case_outcome)

                ev_rec = CaseEvent(
                    case_number=case_num,
                    position=pos,
                    raw_verbatim=ev_item["raw"],
                    normalized_term=norm_upper,
                    preferred_term=pref_title,
                    soc=case_rec.primary_soc if pos == 0 else None,
                    event_onset=None,
                    event_outcome=matched_outcome,
                    seriousness_flag=ev_item["seriousness"],
                    listedness_flag=ev_item["listedness"],
                    causality_flag=ev_item["causality"]
                )
                self.db.add(ev_rec)
                total_events += 1

            # Parse and insert products
            parsed_products = self.parse_products(raw_prod)
            for prod_item in parsed_products:
                prod_rec = CaseProduct(
                    case_number=case_num,
                    product_name_raw=prod_item["raw"],
                    brand_name=prod_item["brand"],
                    active_substance=prod_item["active_substance"],
                    role=prod_item["role"]
                )
                self.db.add(prod_rec)
                total_products += 1

            total_cases += 1

        audit = AuditLog(
            user_id="system_ingestion",
            action=f"Ingested {file_name}: {total_cases} cases, {total_events} exploded events, {total_products} products."
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "file": file_name,
            "sheet": sheet_name,
            "total_cases": total_cases,
            "total_events": total_events,
            "total_products": total_products
        }
