# Check ifgramStack.h5 and write report to ifgram_report.txt
import os
out = open(r"d:\coding\insar-system\ifgram_report.txt", "w", encoding="utf-8")
path = r"d:\processing\tianfu\mintpy\inputs\ifgramStack.h5"
if not os.path.isfile(path):
    out.write("File not found: " + path)
    out.close()
    raise SystemExit(1)

import h5py
import numpy as np

with h5py.File(path, "r") as f:
    out.write("=== Keys ===\n")
    out.write(str(list(f.keys())) + "\n\n")
    out.write("=== Root attributes ===\n")
    for k, v in f.attrs.items():
        out.write("  %s: %s\n" % (k, v))
    out.write("\n")

    if "date" in f:
        date12 = f["date"][:]
        if date12.dtype.kind == "S" or date12.dtype.kind == "U":
            date12 = [x.decode("utf-8") if hasattr(x, "decode") else str(x) for x in date12]
        out.write("=== date12 (%d pairs) ===\n" % len(date12))
        for i, d in enumerate(date12):
            out.write("  %d: %s\n" % (i, d))
        out.write("\n")

    for name in ["coherence", "unwrapPhase", "bperp"]:
        if name not in f:
            continue
        d = f[name]
        arr = d[:]
        out.write("=== %s ===\n" % name)
        out.write("  shape: %s dtype: %s\n" % (arr.shape, arr.dtype))
        if arr.size > 0 and np.issubdtype(arr.dtype, np.floating):
            out.write("  min: %s max: %s mean: %s\n" % (np.nanmin(arr), np.nanmax(arr), np.nanmean(arr)))
            nnan = np.isnan(arr).sum()
            out.write("  NaN count: %d\n" % nnan)
        out.write("\n")

    # Per-pair baseline: often in attributes or a 1D dataset
    for key in f.keys():
        obj = f[key]
        if hasattr(obj, "shape") and hasattr(obj, "attrs"):
            if obj.shape == (3,) or (len(obj.shape) == 1 and obj.shape[0] == 3):
                v = obj[:]
                out.write("=== %s (per-pair?) ===\n" % key)
                out.write("  %s\n" % v)
                if np.issubdtype(v.dtype, np.floating):
                    out.write("  NaN count: %d\n" % np.isnan(v).sum())
                out.write("\n")

# Per-pair coherence from spatial mean (like MintPy does)
with h5py.File(path, "r") as f:
    if "coherence" in f:
        coh = f["coherence"][:]
        out.write("=== Per-pair mean coherence (like MintPy) ===\n")
        for i in range(coh.shape[0]):
            m = np.nanmean(coh[i])
            nnan = np.isnan(coh[i]).sum()
            out.write("  pair %d: mean=%s NaN_in_slice=%d\n" % (i, m, nnan))
        out.write("\n")

out.close()
print("Done. See ifgram_report.txt")
