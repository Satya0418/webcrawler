import os

path = "/Users/satya/projects/webcrwler/excel_calculus/docs/apotex_frames_ocr.txt"
with open(path) as f:
    text = f.read()

frames = text.split("==============================")
print(f"Total frame chunks: {len(frames)}")

for idx, chunk in enumerate(frames):
    if not chunk.strip():
        continue
    lines = [l.strip() for l in chunk.split("\n") if l.strip()]
    if not lines:
        continue
    header = lines[0]
    # find notable lines (document titles, excel titles, tables, section headers)
    notable = []
    for l in lines[1:]:
        if any(keyword in l.lower() for keyword in ["section", "pbrer", "psur", "abiraterone", "linelisting", "search", "safety", "table", "case", "interval", "cumulative", "concern", "16.3", "16.2", "9.", "smq"]):
            notable.append(l)
    print(f"\n{header}")
    if notable:
        print("   Notable: " + " | ".join(notable[:5]))
    else:
        print("   Lines count:", len(lines))
