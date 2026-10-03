from pypdf import PdfReader
import re

pdf_path = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Abiraterone/Abiraterone_20250428_CAN-KUW-UAE-PBRER_Final.pdf"
reader = PdfReader(pdf_path)
print("Total pages:", len(reader.pages))

# Search for Section 16 or 16.3 or 16.4
matching_pages = []
for idx, page in enumerate(reader.pages):
    text = page.extract_text() or ""
    if re.search(r"16\.3|16\.4|Evaluation of Risks|Hepatotoxicity", text, re.IGNORECASE):
        matching_pages.append((idx + 1, text[:300].replace("\n", " ")))

print(f"Matching pages count: {len(matching_pages)}")
for p_num, snippet in matching_pages[:15]:
    print(f"Page {p_num}: {snippet[:150]}")
