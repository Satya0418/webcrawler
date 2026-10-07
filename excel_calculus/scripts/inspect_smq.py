import openpyxl

path = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/MedDRA SMQ list/SMQ_spreadsheet_29_0_English.xlsx"
wb = openpyxl.load_workbook(path, data_only=True)

for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    print(f"\n{'='*20} Sheet: {sheet_name} (max_row: {ws.max_row}, max_column: {ws.max_column}) {'='*20}")
    for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if r_idx < 15:
            row_clean = [str(c).strip() if c is not None else "" for c in row]
            # only print non-empty or first few
            print(f"R{r_idx}: {row_clean[:10]}")
        else:
            break
