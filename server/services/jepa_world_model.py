"""
JEPA World Model — temporal state prediction for Minta Expert.

Core principle (LeCun): predict in abstract latent space, not raw input space.
Given current interaction state, predict the next reasonable state.

Architecture:
  Encoder:    symptom_emb(384) + domain_emb(16) → latent(128)
  Predictor:  latent(128) → predicted_next_latent(128)
  Comparator: cosine similarity between predicted and actual next state

Iron rules:
  1. Domain rules > JEPA predictions (JEPA never overrides hard rules)
  2. No history → JEPA goes silent (cold start fallback)
  3. JEPA only learns temporal patterns, never modifies domain rules
"""
import logging
import math
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

logger = logging.getLogger(__name__)

# State consistency thresholds (from plan v4)
SIMILARITY_PASS = 0.85
SIMILARITY_FLAG = 0.6

# Cold start thresholds
MIN_HISTORY_FOR_PREDICTION = 10
MIN_HISTORY_FOR_TRAINING = 50


class JEPAEncoder(nn.Module):
    """Encode symptom+domain embedding into latent state.

    Architecture: 400 → 256 → 128 with residual + dropout + layer norm.
    """
    def __init__(self, input_dim: int = 400, hidden_dim: int = 256,
                 latent_dim: int = 128, dropout: float = 0.15):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, latent_dim),
            nn.LayerNorm(latent_dim),
        )
        # Residual projection (if input_dim != latent_dim)
        self.residual = nn.Linear(input_dim, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.residual(x) + self.net(x)


class JEPAPredictor(nn.Module):
    """Predict next latent state from current latent state.

    Bottleneck structure: 128 → 64 → 128.
    Forces model to learn compressed temporal patterns.
    L2 normalized output + temperature scaling prevents collapse.
    """
    def __init__(self, latent_dim: int = 128, bottleneck: int = 64,
                 temperature: float = 0.07):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, bottleneck),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(bottleneck, latent_dim),
        )
        self.residual = nn.Linear(latent_dim, latent_dim)
        self.temperature = temperature

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        delta = self.net(x)
        out = self.residual(x) + delta
        out = F.normalize(out, p=2, dim=-1)
        return out / self.temperature


class JEPAWorldModel(nn.Module):
    """Full JEPA world model: encoder + predictor + comparison.

    Not a retrieval system. A temporal prediction system.
    Learns: given state_t, predict state_{t+1} in latent space.
    """
    def __init__(self, input_dim: int = 400, latent_dim: int = 128):
        super().__init__()
        self.encoder = JEPAEncoder(input_dim, latent_dim=latent_dim)
        self.predictor = JEPAPredictor(latent_dim)
        self._trained = False
        self._version = 0

    @property
    def trained(self) -> bool:
        return self._trained

    @property
    def version(self) -> int:
        return self._version

    def encode_state(self, symptom_emb: np.ndarray,
                     domain_emb: np.ndarray) -> np.ndarray:
        """Encode raw embeddings into latent state."""
        x = np.concatenate([symptom_emb, domain_emb], axis=-1)
        x_t = torch.from_numpy(x).float().unsqueeze(0) if x.ndim == 1 else torch.from_numpy(x).float()
        with torch.no_grad():
            latent = self.encoder(x_t)
        return latent.squeeze(0).numpy()

    def predict_next(self, current_latent: np.ndarray) -> np.ndarray:
        """Predict next latent state from current."""
        x = torch.from_numpy(current_latent).float()
        if x.ndim == 1:
            x = x.unsqueeze(0)
        with torch.no_grad():
            predicted = self.predictor(x)
        return predicted.squeeze(0).numpy()

    def compare_states(self, expert_state: np.ndarray,
                       jepa_state: np.ndarray) -> Tuple[float, str]:
        """Compare expert output state vs JEPA predicted state.

        Returns:
            similarity: cosine similarity in [0, 1]
            verdict: "pass" | "flag" | "reject"
        """
        a = torch.from_numpy(expert_state).float().unsqueeze(0)
        b = torch.from_numpy(jepa_state).float().unsqueeze(0)
        similarity = float(F.cosine_similarity(a, b, dim=-1).item())
        similarity = max(0.0, min(1.0, similarity))

        if similarity >= SIMILARITY_PASS:
            verdict = "pass"
        elif similarity >= SIMILARITY_FLAG:
            verdict = "flag"
        else:
            verdict = "reject"

        return similarity, verdict

    def compute_loss(self, predicted: torch.Tensor,
                     target: torch.Tensor) -> Tuple[torch.Tensor, float]:
        """Training loss: Smooth-L1 + implicit regularization via L2 norm.

        Args:
            predicted: (batch, latent_dim) predicted next states
            target: (batch, latent_dim) actual next states

        Returns:
            total_loss, smooth_l1_loss_value
        """
        l1 = F.smooth_l1_loss(predicted, target)
        # L2 norm penalty prevents collapse
        norm_penalty = predicted.norm(dim=-1).mean() * 0.01
        return l1 + norm_penalty, l1.item()

    def train_on_sequences(self, sequences: List[Dict],
                           epochs: int = 100,
                           lr: float = 1e-3) -> Dict:
        """Train on temporal sequences from inference_log.

        Args:
            sequences: list of {"state_emb": np.array(128,),
                                "next_state_emb": np.array(128,)}
            epochs: max training epochs
            lr: learning rate

        Returns:
            {"trained": bool, "epochs": int, "final_loss": float}
        """
        if len(sequences) < MIN_HISTORY_FOR_TRAINING:
            logger.info(f"JEPA: insufficient sequences ({len(sequences)} < {MIN_HISTORY_FOR_TRAINING})")
            return {"trained": False, "epochs": 0, "final_loss": 0}

        self.train()
        optimizer = torch.optim.AdamW(self.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=15, factor=0.5, min_lr=1e-5
        )

        # Prepare data
        states = np.array([s["state_emb"] for s in sequences])
        next_states = np.array([s["next_state_emb"] for s in sequences])
        n = len(states)

        best_loss = float('inf')
        patience_counter = 0
        max_patience = 25

        for epoch in range(epochs):
            perm = np.random.permutation(n)
            epoch_loss = 0
            batch_size = min(32, n)
            n_batches = max(1, n // batch_size)

            for b in range(n_batches):
                idx = perm[b * batch_size: (b + 1) * batch_size]
                batch_states = torch.from_numpy(states[idx]).float()
                batch_targets = torch.from_numpy(next_states[idx]).float()

                optimizer.zero_grad()
                predicted = self.predictor(batch_states)
                loss, l1_val = self.compute_loss(predicted, batch_targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                optimizer.step()
                epoch_loss += l1_val

            avg_loss = epoch_loss / max(n_batches, 1)
            scheduler.step(avg_loss)

            # Early stopping
            if avg_loss < best_loss:
                best_loss = avg_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= max_patience:
                    logger.info(f"JEPA early stopping at epoch {epoch}, loss={avg_loss:.6f}")
                    break

            if epoch % 20 == 0:
                logger.info(f"JEPA epoch {epoch}: loss={avg_loss:.6f}")

        self.eval()
        self._trained = True
        self._version += 1
        logger.info(f"JEPA training complete: version={self._version}, loss={best_loss:.6f}")
        return {"trained": True, "epochs": epoch + 1, "final_loss": best_loss}


class JEPAStateComparator:
    """Compare Expert output state with JEPA predicted state.

    Pure geometric operations — no model, no ML.
    """
    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        a_t = torch.from_numpy(a).float().unsqueeze(0)
        b_t = torch.from_numpy(b).float().unsqueeze(0)
        return float(F.cosine_similarity(a_t, b_t, dim=-1).item())

    @staticmethod
    def verdict(similarity: float) -> str:
        if similarity >= SIMILARITY_PASS:
            return "pass"
        elif similarity >= SIMILARITY_FLAG:
            return "flag"
        return "reject"

    @staticmethod
    def get_missing_dimensions(domain: str, inference_logs: List[Dict]) -> List[str]:
        """Extract 'missing dimensions' from historical logs.

        Rule: dimensions come from what past users supplemented.
        Not generated, not hallucinated.
        """
        dimensions = set()
        for log in inference_logs[:20]:
            mi = log.get("missing_info") or []
            if isinstance(mi, list):
                for m in mi:
                    if isinstance(m, str) and len(m) < 200:
                        dimensions.add(m)
        return list(dimensions)[:5]
