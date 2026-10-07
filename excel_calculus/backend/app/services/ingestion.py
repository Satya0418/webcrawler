import os
import re
import hashlib
from datetime import datetime
import openpyxl
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import CaseRecord, CaseEvent, CaseProduct, AuditLog, Dataset

class IngestionService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def clean_xml_hex(val: str) -> str:
        """Removes Excel/XML hex artifacts such as _x000D_, _x0015_, _x0016_, etc."""
        if not val:
            return ""
        return re.sub(r"_x[0-9a-fA-F]{4}_", "", str(val))

    @staticmethod
    def normalize_term(val: str) -> str:
        """
        Equivalent to TRIM(event) in Excel / Power Query:
        - Replaces tabs and newlines with spaces
        - Collapses duplicate whitespace
        - Strips leading and trailing whitespace
        """
        if not val:
            return ""
        clean = re.sub(r"[\r\n\t]+", " ", str(val))
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def parse_event_verbatim(self, raw_ev: str):
        """
        Parses multi-event verbatim text, e.g.:
        [PAIN IN EXTREMITY_x0015__x0016_]_x000D_
        Y / Y / Y_x000D_
        [GAIT DISTURBANCE_x0016_]...

        Preserves:
        - raw_event_value: exact bracketed segment from raw cell
        - normalized_event_text: cleaned, normalized uppercase medical event term
        - flags: clinical assessment markers (seriousness, listedness, causality)
        Guarantees that flags like Y/Y/Y or N/Y/Y NEVER pollute the medical event term.
        """
        if not raw_ev:
            return []

        # Find bracketed expressions and any trailing flag lines
        pattern = re.compile(r'\[([^\]]+)\](?:\s*([YyNn\s/]+))?')
        matches = pattern.findall(raw_ev)

        events = []
        if matches:
            for term, flags in matches:
                # Raw representation preserving brackets and original content
                raw_token = f"[{term}]"
                clean_term = self.clean_xml_hex(term)
                norm_term = self.normalize_term(clean_term)

                clean_flags = self.clean_xml_hex(flags) if flags else ""
                norm_flags = self.normalize_term(clean_flags)

                if norm_term:
                    flag_parts = [f.strip() for f in norm_flags.split("/") if f.strip()]
                    seriousness = flag_parts[0] if len(flag_parts) > 0 else None
                    listedness = flag_parts[1] if len(flag_parts) > 1 else None
                    causality = flag_parts[2] if len(flag_parts) > 2 else None

                    events.append({
                        "normalized_term": norm_term.upper(),
                        "raw_verbatim": raw_token,
                        "seriousness": seriousness,
                        "listedness": listedness,
                        "causality": causality
                    })
        else:
            # Fallback if events are not bracketed
            cleaned_text = self.clean_xml_hex(raw_ev)
            lines = [self.normalize_term(l) for l in cleaned_text.splitlines() if self.normalize_term(l)]
            for l in lines:
                if not re.match(r'^[YyNn\s/]+$', l):
                    events.append({
                        "normalized_term": l.upper(),
                        "raw_verbatim": l,
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

    def parse_event_onsets(self, raw_onsets):
        """
        Parses 'Event Onset' column. Can be datetime object or multi-line string.
        """
        if raw_onsets is None:
            return []
        if isinstance(raw_onsets, datetime):
            return [raw_onsets.strftime("%Y-%m-%d")]

        cleaned = self.clean_xml_hex(str(raw_onsets))
        lines = [self.normalize_term(l) for l in cleaned.splitlines() if self.normalize_term(l)]
        return lines

    def parse_products(self, raw_products: str, primary_product_name: str = "", primary_dose: str = "", primary_form: str = "", primary_duration: str = "", primary_indication: str = ""):
        """
        Parses complete product information from line listing:
        1. Primary suspect drug from case columns (Daily Dose, Form, Duration, Indication)
        2. Co-suspect and concomitant drugs from 'Product Name' column
        """
        products = []

        # 1. Primary suspect product
        clean_primary_dose = self.normalize_term(self.clean_xml_hex(primary_dose)) if primary_dose else None
        clean_primary_form = self.normalize_term(self.clean_xml_hex(primary_form)) if primary_form else None
        clean_primary_dur = self.normalize_term(self.clean_xml_hex(primary_duration)) if primary_duration else None
        clean_primary_ind = self.normalize_term(self.clean_xml_hex(primary_indication)) if primary_indication else None

        # Extract brand from primary dose header if available (e.g. 'APO-ABIRATERONE / Film coated...')
        primary_brand = primary_product_name
        if clean_primary_dose and " / " in clean_primary_dose:
            primary_brand = clean_primary_dose.split(" / ")[0].strip()

        products.append({
            "raw": f"{primary_brand} (Primary Suspect)",
            "brand": primary_brand,
            "active_substance": primary_product_name.upper(),
            "role": "Suspect",
            "daily_dose": clean_primary_dose,
            "form": clean_primary_form,
            "duration": clean_primary_dur,
            "indication_pt": clean_primary_ind
        })

        # 2. Additional products from Product Name column
        if raw_products:
            cleaned = self.clean_xml_hex(raw_products)
            for line in cleaned.splitlines():
                line_clean = self.normalize_term(line)
                if not line_clean:
                    continue

                role = "Suspect" if "suspect" in line_clean.lower() else ("Concom" if "concom" in line_clean.lower() else "Concomitant")

                active_sub = None
                paren_match = re.search(r'\(([^)]+)\)', line_clean)
                if paren_match:
                    active_sub = paren_match.group(1).strip()

                brand = line_clean.split("(")[0].strip() if paren_match else line_clean.split()[0]

                # Extract daily dose if embedded in string
                dose_match = re.search(r'daily dose:\s*([^,]+)', line_clean, re.IGNORECASE)
                dose_val = dose_match.group(1).strip() if dose_match else None

                # Extract form/route if embedded
                form_val = None
                for candidate_form in ["Oral use", "Tablet", "Capsule", "Injection", "Intravenous"]:
                    if candidate_form.lower() in line_clean.lower():
                        form_val = candidate_form
                        break

                products.append({
                    "raw": line_clean,
                    "brand": brand,
                    "active_substance": active_sub or brand,
                    "role": role,
                    "daily_dose": dose_val,
                    "form": form_val,
                    "duration": None,
                    "indication_pt": None
                })

        return products

    def ingest_linelisting_file(
        self,
        file_path: str,
        primary_product_name: str = "Unknown",
        reporting_period: str = None,
        data_lock_point: str = None
    ):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        if not reporting_period:
            if "20260428" in file_name or "abiraterone" in primary_product_name.lower():
                reporting_period = "29-Apr-2025 to 28-Apr-2026"
                data_lock_point = "28-Apr-2026"
            elif "20260412" in file_name or "oxycodone" in primary_product_name.lower():
                reporting_period = "13-Apr-2025 to 12-Apr-2026"
                data_lock_point = "12-Apr-2026"
            else:
                reporting_period = "Current Reporting Period"
                data_lock_point = datetime.utcnow().strftime("%d-%b-%Y")

        dataset_id = f"ds_{primary_product_name.lower()}_{file_hash[:8]}"
        dataset = self.db.query(Dataset).filter_by(id=dataset_id).first()
        if not dataset:
            dataset = Dataset(
                id=dataset_id,
                dataset_type="LINE_LISTING",
                product_name=primary_product_name,
                reporting_period=reporting_period,
                data_lock_point=data_lock_point,
                source_filename=file_name,
                source_file_hash=file_hash,
                status="ACTIVE"
            )
            self.db.add(dataset)
            self.db.flush()

        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_name = wb.sheetnames[0]
        ws = wb[sheet_name]

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"status": "empty", "cases": 0, "events": 0}

        headers = [str(c).strip() if c is not None else "" for c in rows[0]]

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
        idx_daily_dose = col_idx("Daily Dose")
        idx_form = col_idx("Form")
        idx_duration = col_idx("Duration")
        idx_onset = col_idx("Event Onset")
        idx_ev = col_idx("Event Verbatim")
        idx_outcome = col_idx("Outcome")
        idx_outcome_ev = col_idx("Outcome of Event")
        idx_hcp = col_idx("Health Care Prof.")
        idx_non_ser_list = col_idx("Non-Serious Listed")
        idx_followup = col_idx("FollowUp")
        idx_receipt_date = col_idx("Case Initial Receipt Date")
        idx_narrative = col_idx("Case Narrative")
        idx_seriousness = col_idx("Case Seriousness?")
        idx_prod_ind = col_idx("Product Indication PT")
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
            raw_dose = str(row[idx_daily_dose]) if (idx_daily_dose >= 0 and row[idx_daily_dose] is not None) else ""
            raw_form = str(row[idx_form]) if (idx_form >= 0 and row[idx_form] is not None) else ""
            raw_dur = str(row[idx_duration]) if (idx_duration >= 0 and row[idx_duration] is not None) else ""
            raw_onset = row[idx_onset] if idx_onset >= 0 else None
            raw_ind = str(row[idx_prod_ind]) if (idx_prod_ind >= 0 and row[idx_prod_ind] is not None) else ""

            # Check if case exists in this specific dataset
            case_rec = self.db.query(CaseRecord).filter_by(dataset_id=dataset_id, case_number=case_num).first()
            if not case_rec:
                case_rec = CaseRecord(dataset_id=dataset_id, case_number=case_num)
                self.db.add(case_rec)
                self.db.flush()

            seriousness_val = str(row[idx_seriousness]).strip() if (idx_seriousness >= 0 and row[idx_seriousness] is not None) else ""

            case_rec.product_name = primary_product_name
            case_rec.reporting_period = reporting_period
            case_rec.data_lock_point = data_lock_point
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

            # Clear existing child event & product records for this internal case_id during reconciliation
            self.db.query(CaseEvent).filter_by(case_id=case_rec.id).delete()
            self.db.query(CaseProduct).filter_by(case_id=case_rec.id).delete()

            # Explode events
            parsed_events = self.parse_event_verbatim(raw_ev)
            outcomes_map = self.parse_outcomes(raw_outcome_ev)
            onsets_list = self.parse_event_onsets(raw_onset)

            for pos, ev_item in enumerate(parsed_events):
                norm_upper = ev_item["normalized_term"]
                matched_outcome = outcomes_map.get(norm_upper, case_rec.case_outcome)

                # Determine onset mapping
                matched_onset = None
                onset_status = "CONFIRMED"
                if onsets_list:
                    if len(onsets_list) == 1:
                        matched_onset = onsets_list[0]
                        onset_status = "CONFIRMED"
                    elif pos < len(onsets_list):
                        matched_onset = onsets_list[pos]
                        onset_status = "UNCERTAIN_MAPPED_BY_POSITION"
                    else:
                        matched_onset = onsets_list[0]
                        onset_status = "UNCERTAIN_MAPPED_BY_POSITION"

                ev_rec = CaseEvent(
                    case_id=case_rec.id,
                    case_number=case_num,
                    dataset_id=dataset_id,
                    position=pos + 1,  # 1-indexed position
                    raw_verbatim=ev_item["raw_verbatim"],
                    normalized_term=norm_upper,
                    preferred_term=None,  # Null until exact MedDRA lookup matches it! Never fabricate!
                    pt_code=None,
                    soc=case_rec.primary_soc if pos == 0 else None,
                    event_onset=matched_onset,
                    onset_mapping_status=onset_status,
                    event_outcome=matched_outcome,
                    seriousness_flag=ev_item["seriousness"],
                    listedness_flag=ev_item["listedness"],
                    causality_flag=ev_item["causality"],
                    source_file=file_name,
                    source_sheet=sheet_name,
                    source_row=r_idx
                )
                self.db.add(ev_rec)
                total_events += 1

            # Populate products (Primary + Concomitants)
            parsed_prods = self.parse_products(
                raw_products=raw_prod,
                primary_product_name=primary_product_name,
                primary_dose=raw_dose,
                primary_form=raw_form,
                primary_duration=raw_dur,
                primary_indication=raw_ind
            )
            for prod_item in parsed_prods:
                prod_rec = CaseProduct(
                    case_id=case_rec.id,
                    case_number=case_num,
                    dataset_id=dataset_id,
                    product_name_raw=prod_item["raw"],
                    brand_name=prod_item["brand"],
                    active_substance=prod_item["active_substance"],
                    role=prod_item["role"],
                    daily_dose=prod_item["daily_dose"],
                    form=prod_item["form"],
                    duration=prod_item["duration"],
                    indication_pt=prod_item["indication_pt"]
                )
                self.db.add(prod_rec)
                total_products += 1

            total_cases += 1

        dataset.total_cases = total_cases
        dataset.total_events = total_events
        self.db.commit()

        # Audit log entry
        audit = AuditLog(
            dataset_id=dataset_id,
            action="INGEST_LINE_LISTING",
            new_state=f"Ingested {total_cases} cases, {total_events} events, {total_products} products from {file_name}"
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "dataset_id": dataset_id,
            "status": "success",
            "file_name": file_name,
            "file_hash": file_hash,
            "total_cases": total_cases,
            "total_events": total_events,
            "total_products": total_products
        }
