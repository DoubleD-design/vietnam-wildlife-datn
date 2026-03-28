from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import requests

from app.core.config import settings


logger = logging.getLogger(__name__)


class ImageRecognitionService:
    def __init__(self) -> None:
        self._model = None
        self._device = None
        self._transform = None
        self._idx_to_class: dict[int, str] = {}
        self._torch = None

    def predict(self, image_url: str, top_k: int = 5) -> list[tuple[str, float]]:
        self._ensure_ready()
        if not image_url.strip():
            return []

        image = self._load_image(image_url)
        if image is None:
            return []

        tensor = self._transform(image).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=-1)[0]

        k = min(top_k, len(self._idx_to_class))
        top_prob, top_idx = self._torch.topk(probs, k)
        out: list[tuple[str, float]] = []
        for i in range(k):
            class_idx = int(top_idx[i].item())
            confidence = float(top_prob[i].item())
            class_name = self._idx_to_class.get(class_idx)
            if not class_name:
                continue
            out.append((class_name, confidence))
        return out

    def _ensure_ready(self) -> None:
        if self._model is not None:
            return

        try:
            import torch
            import torch.nn as nn
            from PIL import Image
            from torchvision import transforms
            import open_clip
        except ImportError as ex:
            raise RuntimeError(
                "Missing vision dependencies. Install torch/torchvision/open_clip_torch/Pillow in wildlife-ai env."
            ) from ex

        class BioCLIPClassifier(nn.Module):
            EMBED_DIM = 512

            def __init__(self, visual_encoder: nn.Module, num_classes: int):
                super().__init__()
                self.visual = visual_encoder
                self.classifier = nn.Sequential(
                    nn.Dropout(p=0.0),
                    nn.Linear(self.EMBED_DIM, num_classes),
                )

            def forward(self, x):
                features = self.visual(x)
                return self.classifier(features)

        self._torch = torch
        self._pil_image = Image

        if torch.cuda.is_available():
            self._device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self._device = torch.device("mps")
        else:
            self._device = torch.device("cpu")

        mapping_path = Path(settings.vision_class_mapping_path)
        weights_path = Path(settings.vision_model_weights_path)

        if not mapping_path.exists():
            raise RuntimeError(f"Class mapping not found: {mapping_path}")
        if not weights_path.exists():
            raise RuntimeError(f"Model weights not found: {weights_path}")

        with mapping_path.open("r", encoding="utf-8") as f:
            mapping = json.load(f)
        self._idx_to_class = {int(k): str(v) for k, v in mapping.items()}

        backbone = None
        if settings.vision_use_remote_backbone:
            try:
                backbone, _, _ = open_clip.create_model_and_transforms(
                    settings.vision_backbone
                )
                logger.info(
                    "Loaded remote vision backbone: %s", settings.vision_backbone
                )
            except Exception as ex:
                logger.warning(
                    "Remote backbone unavailable (%s). Falling back to local arch %s.",
                    ex,
                    settings.vision_local_arch,
                )

        if backbone is None:
            try:
                backbone, _, _ = open_clip.create_model_and_transforms(
                    settings.vision_local_arch,
                    pretrained=None,
                )
            except TypeError:
                # Backward compatible path for open_clip signatures.
                local_model = open_clip.create_model(
                    settings.vision_local_arch,
                    pretrained=None,
                )
                backbone = local_model
            logger.info(
                "Loaded local vision architecture: %s", settings.vision_local_arch
            )

        model = BioCLIPClassifier(
            visual_encoder=backbone.visual,
            num_classes=len(self._idx_to_class),
        ).to(self._device)
        del backbone

        checkpoint = torch.load(
            weights_path, map_location=self._device, weights_only=True
        )
        state = checkpoint.get("model_state") if isinstance(checkpoint, dict) else None
        if state is None:
            state = checkpoint
        model.load_state_dict(state)
        model.eval()

        self._model = model
        self._transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    [0.48145466, 0.4578275, 0.40821073],
                    [0.26862954, 0.26130258, 0.27577711],
                ),
            ]
        )

    def _load_image(self, image_url: str):
        if image_url.startswith(("http://", "https://")):
            timeout = max(1, settings.vision_download_timeout_seconds)
            response = requests.get(image_url, timeout=timeout)
            response.raise_for_status()
            return self._pil_image.open(io.BytesIO(response.content)).convert("RGB")

        path = Path(image_url)
        if not path.exists():
            return None
        return self._pil_image.open(path).convert("RGB")
