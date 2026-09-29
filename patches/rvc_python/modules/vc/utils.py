import os

# fairseq is not available on this machine: hubert features come from a
# transformers-format ContentVec instead (same model family, numerically close).
def get_index_path_from_model(sid):
    return next(
        (
            f
            for f in [
                os.path.join(root, name)
                for root, _, files in os.walk(os.getenv("index_root"), topdown=False)
                for name in files
                if name.endswith(".index") and "trained" not in name
            ]
            if sid.split(".")[0] in f
        ),
        "",
    )


def load_hubert(config, lib_dir):
    from rvc_python.modules.vc.contentvec_hf import load_contentvec
    model = load_contentvec(lib_dir)
    try:
        model = model.to(getattr(config, "device", "cpu"))
    except Exception:
        pass
    return model.eval()