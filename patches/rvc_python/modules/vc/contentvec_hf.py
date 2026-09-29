"""Fairseq-free HuBERT/ContentVec feature extractor (transformers backend).

The original rvc_python uses fairseq to load hubert_base.pt. fairseq does not
install on this machine (no compiler / py3.12), so we use the HF-format
ContentVec - the same model family used by RVC for feature extraction.
Interface-compatible with the fairseq model: .to/.half/.float/.eval and
.extract_features(source=..., padding_mask=..., output_layer=N) -> (feats, mask)
"""
import os
import torch


class _HFHubert:
    def __init__(self, model_name_or_dir):
        from transformers import HubertModel
        self.model = HubertModel.from_pretrained(model_name_or_dir)
        self.device = torch.device("cpu")

    def to(self, device):
        self.device = torch.device(device) if str(device) else torch.device("cpu")
        if "cuda" not in str(self.device):
            self.device = torch.device("cpu")
        self.model.to(self.device)
        return self

    def half(self):
        return self

    def float(self):
        return self

    def eval(self):
        self.model.eval()
        return self

    def extract_features(self, source=None, padding_mask=None, output_layer=12):
        with torch.no_grad():
            out = self.model(source.to(self.device), output_hidden_states=True)
            feats = out.hidden_states[int(output_layer)]
        return (feats, padding_mask)

    def final_proj(self, x):
        # only used by v1 models; our target models are v2 (768-dim features)
        return x


def load_contentvec(lib_dir):
    local = os.path.join(lib_dir, "base_model", "contentvec_hf")
    name = local if os.path.isdir(local) else "lengyue233/content-vec-best"
    return _HFHubert(name)