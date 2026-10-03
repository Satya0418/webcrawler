import subprocess
import glob
import os

base_dir = "/Users/satya/projects/webcrwler/excel_calculus"
frames = sorted(glob.glob(os.path.join(base_dir, "data/apotex_frames/frame_*.jpg")))
out_file = os.path.join(base_dir, "docs/apotex_frames_ocr.txt")

with open(out_file, "w") as out:
    for idx, f in enumerate(frames):
        seconds = idx * 45
        mins = seconds // 60
        secs = seconds % 60
        out.write(f"\n{'='*30} FRAME {idx+1} ({mins:02d}:{secs:02d}) - {f} {'='*30}\n")
        res = subprocess.run([os.path.join(base_dir, "scripts/ocr_frame"), f], capture_output=True, text=True)
        out.write(res.stdout)

print(f"Processed {len(frames)} frames into {out_file}")
