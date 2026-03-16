"""Quick check of ifgramStack.h5: structure, attributes, coherence and Bperp for NaN."""
import sys
import os

def main():
    path = r"d:\processing\tianfu\mintpy\inputs\ifgramStack.h5"
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return 1

    try:
        import h5py
    except ImportError:
        print("h5py not found, trying MintPy readfile...")
        h5py = None

    if h5py:
        with h5py.File(path, "r") as f:
            print("=== Groups/Datasets ===")
            def print_structure(name, obj):
                if isinstance(obj, h5py.Dataset):
                    print(f"  {name}: shape={obj.shape}, dtype={obj.dtype}")
                else:
                    print(f"  {name}/ (Group)")
            f.visititems(print_structure)

            print("\n=== Root attributes ===")
            for k, v in f.attrs.items():
                print(f"  {k}: {v}")

            # Date12 and per-pair data
            if "date" in f:
                date12 = f["date"][:]
                if hasattr(date12, "astype"):
                    date12 = date12.astype(str)
                print("\n=== date (date12 list) ===")
                for i, d in enumerate(date12):
                    print(f"  {i}: {d}")

            for dset_name in ["coherence", "unwrapPhase", "bperp", "pbase"]:
                key = None
                for k in f.keys():
                    if dset_name.lower() in k.lower() or (dset_name == "pbase" and "base" in k.lower()):
                        key = k
                        break
                if key is None and dset_name in f:
                    key = dset_name
                if key is None:
                    continue
                d = f[key]
                if hasattr(d, "shape"):
                    arr = d[:]
                    if hasattr(arr, "flatten"):
                        flat = arr.flatten()
                        nnan = float("nan") if flat.dtype.kind != "f" else sum(1 for x in flat if x != x)
                        try:
                            nnan = int(__import__("numpy").isnan(flat).sum())
                        except Exception:
                            nnan = "?"
                        print(f"\n=== {key} ===")
                        print(f"  shape: {d.shape}")
                        if flat.size > 0 and flat.dtype.kind in "fc":
                            print(f"  min/max/mean: {flat.min():.6f} / {flat.max():.6f} / {flat.mean():.6f}")
                            print(f"  NaN count: {nnan}")

    # MintPy-style summary if available
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib", "MintPy-main", "src"))
        import mintpy
        from mintpy.objects import ifgramStack
        from mintpy.utils import readfile
        print("\n=== MintPy ifgramStack summary ===")
        obj = ifgramStack(path)
        obj.open()
        date12_list = obj.get_date12_list(dropIfgram=False)
        print(f"  date12 list: {date12_list}")
        if hasattr(obj, "pbaseIfgram"):
            pbase = obj.pbaseIfgram
            print(f"  pbaseIfgram: {pbase}")
            import numpy as np
            print(f"  pbase NaN count: {np.isnan(pbase).sum()}")
        if "coherence" in readfile.get_dataset_list(path):
            coh = readfile.read(path, datasetName="coherence")[0]
            import numpy as np
            if coh is not None and hasattr(coh, "flatten"):
                cflat = coh.flatten()
                print(f"  coherence NaN count: {np.isnan(cflat).sum()}")
    except Exception as e:
        print(f"\nMintPy check skipped: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
