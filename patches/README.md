# patches/ — files that live OUTSIDE the repo normally

## rvc_python (custom voice runtime)

fairseq cannot install on this machine (py3.12, no compiler), so the RVC stack was
patched inside site-packages. If the venv is ever rebuilt, reinstall:

    pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio
    pip install --no-deps rvc-python
    pip install torchcrepe ffmpeg-python loguru transformers librosa soundfile faiss-cpu praat-parselmouth pyworld av tqdm

then copy these files back:

    patches/rvc_python/modules/vc/utils.py        -> site-packages/rvc_python/modules/vc/utils.py
    patches/rvc_python/modules/vc/contentvec_hf.py -> site-packages/rvc_python/modules/vc/contentvec_hf.py
    patches/rvc_python/modules/vc/pipeline.py     -> site-packages/rvc_python/modules/vc/pipeline.py

What the patches do:
- utils.py: replaces the fairseq hubert loader with a transformers ContentVec loader
- contentvec_hf.py: the adapter class (fairseq-like API over HuggingFace ContentVec)
- pipeline.py: caches the faiss index between conversions (adds _IDX_CACHE)