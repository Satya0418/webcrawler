import openpyxl
from sqlalchemy.orm import Session
from excel_calculus.backend.app.models.entities import SMQTerm, AuditLog

class SMQLoaderService:
    def __init__(self, db: Session):
        self.db = db

    def load_smq_file(self, file_path: str):
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_target = None
        for s in wb.sheetnames:
            s_lower = s.lower()
            if "smq" in s_lower and "hierarchy" not in s_lower and "summary" not in s_lower and "count" not in s_lower and "code" not in s_lower:
                sheet_target = s
                break
        if not sheet_target:
            sheet_target = "SMQ 29.0" if "SMQ 29.0" in wb.sheetnames else wb.sheetnames[0]
        ws = wb[sheet_target]

        # Clear existing SMQ terms
        self.db.query(SMQTerm).delete()

        stack = [] # (col_idx, smq_name)
        batch = []
        batch_size = 5000
        total_inserted = 0

        for r in range(2, ws.max_row + 1):
            row_vals = [ws.cell(r, c).value for c in range(1, 15)]

            # Check for SMQ header
            smq_col = -1
            smq_name = None
            for c_idx, val in enumerate(row_vals):
                if val and "(smq)" in str(val).lower():
                    smq_col = c_idx
                    smq_name = str(val).strip()
                    break

            if smq_name:
                while stack and stack[-1][0] >= smq_col:
                    stack.pop()
                stack.append((smq_col, smq_name))
                continue

            # Check for Scope (Narrow or Broad)
            scope_col = -1
            scope_val = None
            for c_idx, val in enumerate(row_vals):
                if val in ("Narrow", "Broad"):
                    scope_col = c_idx
                    scope_val = val
                    break

            if scope_val and scope_col >= 0:
                pt_name = row_vals[scope_col + 2]
                pt_code = row_vals[scope_col + 3]

                if pt_name:
                    pt_clean = str(pt_name).strip()
                    pt_upper = pt_clean.upper()
                    code_clean = str(pt_code).strip() if pt_code else ""

                    # Add for all active SMQs currently in stack
                    for _, s_name in stack:
                        # Add Broad entry
                        batch.append(SMQTerm(
                            smq_name=s_name,
                            smq_code="",
                            scope="Broad",
                            pt_name=pt_clean,
                            pt_name_upper=pt_upper,
                            pt_code=code_clean,
                            is_active=True
                        ))
                        # If Narrow, also add Narrow entry
                        if scope_val == "Narrow":
                            batch.append(SMQTerm(
                                smq_name=s_name,
                                smq_code="",
                                scope="Narrow",
                                pt_name=pt_clean,
                                pt_name_upper=pt_upper,
                                pt_code=code_clean,
                                is_active=True
                            ))

            if len(batch) >= batch_size:
                self.db.bulk_save_objects(batch)
                self.db.commit()
                total_inserted += len(batch)
                batch = []

        if batch:
            self.db.bulk_save_objects(batch)
            self.db.commit()
            total_inserted += len(batch)

        audit = AuditLog(
            user_id="system_smq_loader",
            action=f"Loaded MedDRA SMQ terminology: {total_inserted} entries inserted."
        )
        self.db.add(audit)
        self.db.commit()

        return {"total_smq_terms": total_inserted}
