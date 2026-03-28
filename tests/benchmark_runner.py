import os
import sys
import time
import shutil
import hashlib
from pathlib import Path
from diffinite.pipeline import run_pipeline

def b_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def main():
    root_dir = Path(__file__).resolve().parent.parent
    tmp_out = root_dir / "tmp"
    bench_left = tmp_out / "bench_src_left"
    bench_right = tmp_out / "bench_src_right"
    
    if not tmp_out.exists():
        tmp_out.mkdir(parents=True, exist_ok=True)
        
    print("Preparing 50-file benchmark payload (disabling Winnowing)...")
    if bench_left.exists(): shutil.rmtree(bench_left)
    if bench_right.exists(): shutil.rmtree(bench_right)
    bench_left.mkdir(parents=True)
    bench_right.mkdir(parents=True)
    
    count = 0
    src_dir = root_dir / "src"
    
    # Collect 50 small python files safely
    for f in src_dir.rglob("*.py"):
        if count >= 50:
            break
        if f.is_file() and f.stat().st_size < 50000:  # < 50KB
            try:
                # Left
                dest_l = bench_left / f.relative_to(src_dir)
                dest_l.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest_l)
                
                # Right (mutated)
                dest_r = bench_right / f.relative_to(src_dir)
                dest_r.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest_r)
                txt = dest_r.read_text(encoding="utf-8")
                dest_r.write_text(txt + "\n# diffinite forced diff\n", encoding="utf-8")
                count += 1
            except Exception:
                pass

    print(f"--- Diffinite HTML Rendering Multi-processing Benchmark ---")
    workers_to_test = [1, 2, 4, 8]
    
    reference_hash = None
    results = []

    for w in workers_to_test:
        out_html = tmp_out / f"bench_{w}_workers.html"
        start_time = time.time()
        
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        
        try:
            run_pipeline(
                dir_a=str(bench_left),
                dir_b=str(bench_right),
                report_html=str(out_html),
                workers=w,
                by_word=False,
                strip_comments=True,
                exec_mode="simple"
            )
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout

        elapsed = time.time() - start_time
        results.append((w, elapsed))
        
        # Identity Check
        if not out_html.exists():
            print(f"Worker {w}: FAIL (File not generated)")
            continue
            
        current_hash = b_hash(str(out_html))
        if reference_hash is None:
            reference_hash = current_hash
            match_status = "REFERENCE"
        else:
            match_status = "PASS" if current_hash == reference_hash else "FAIL (Mismatch!)"
            
        print(f"Workers: {w:<2} | Time: {elapsed:.3f}s | Identity: {match_status}")

    print("\n--- Summary ---")
    base_time = results[0][1]
    for w, t in results:
        speedup = base_time / t
        print(f"{w} Core(s) : {t:.2f}s (Speedup: {speedup:.2f}x)")

if __name__ == "__main__":
    main()
