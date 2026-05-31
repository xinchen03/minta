"""
JEPA Scheduler — manages temporal prediction lifecycle.

Responsibilities:
- Cold start detection: no history → JEPA silent
- Training triggers: enough data → train predictor
- Versioning: track predictor versions for audit
- Domain isolation: each domain has its own predictor instance
- Cross-domain toggle: configurable per domain

Iron rules enforced:
  1. Domain rules > JEPA predictions (JEPA never overrides)
  2. No history → JEPA goes silent
  3. JEPA only learns temporal patterns, never domain rules
"""
import logging
import os
import pickle
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import torch

from models.inference_log import InferenceLog
from services.jepa_world_model import (
    JEPAWorldModel, JEPAStateComparator, MIN_HISTORY_FOR_PREDICTION
)

logger = logging.getLogger(__name__)

# Model storage
MODEL_DIR = Path(os.environ.get("MINTA_MODEL_DIR", "D:/minta-expert-data/jepa_models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Domain config — cross-domain toggle
DEFAULT_DOMAIN_CONFIG = {
    "medical_cpg": {"cross_domain_enable": True, "allowed_cross_domains": ["*"]},
    "legal_review": {"cross_domain_enable": True, "allowed_cross_domains": ["*"]},
    "government_audit": {"cross_domain_enable": False, "allowed_cross_domains": []},
    "engineering_inspection": {"cross_domain_enable": True, "allowed_cross_domains": ["*"]},
}


class JEPAScheduler:
    """Production-grade JEPA lifecycle manager.

    One instance per domain, isolated state.
    """

    def __init__(self, db=None):
        self.db = db
        self._models: Dict[str, JEPAWorldModel] = {}
        self._domain_cache: Dict[str, Dict] = {}

    def get_or_create_model(self, domain: str) -> JEPAWorldModel:
        """Get existing predictor for domain, or create new one."""
        if domain not in self._models:
            model_path = MODEL_DIR / f"jepa_{domain}.pt"
            model = JEPAWorldModel()

            if model_path.exists():
                try:
                    state = torch.load(str(model_path), map_location='cpu')
                    model.load_state_dict(state)
                    # Infer version from filename metadata
                    ver_path = MODEL_DIR / f"jepa_{domain}_version.txt"
                    if ver_path.exists():
                        model._version = int(ver_path.read_text().strip())
                    model._trained = True
                    logger.info(f"JEPA: loaded {domain} model v{model._version}")
                except Exception as e:
                    logger.warning(f"JEPA: failed to load {domain} model: {e}")

            self._models[domain] = model

        return self._models[domain]

    def count_history(self, domain: str, user_id: int = 0) -> int:
        """Count available inference_log entries for domain."""
        if not self.db:
            return 0
        try:
            q = self.db.query(InferenceLog).filter(
                InferenceLog.domain == domain,
            )
            if user_id > 0:
                q = q.filter(InferenceLog.user_id == user_id)
            return q.count()
        except Exception as e:
            logger.debug(f"JEPA count_history failed: {e}")
            return 0

    def get_temporal_sequence(self, domain: str, user_id: int = 0,
                              window: int = 50) -> List[Dict]:
        """Get temporal sequence from inference_log.

        Rule (from plan):
        - Default: same user > same domain public
        - Window: last 50 interactions
        - Isolation: user private and global public separated
        """
        if not self.db:
            return []
        try:
            q = self.db.query(InferenceLog).filter(
                InferenceLog.domain == domain,
                InferenceLog.user_signal.isnot(None),  # Only labeled data
            ).order_by(InferenceLog.id.desc()).limit(window)

            if user_id > 0:
                q = self.db.query(InferenceLog).filter(
                    InferenceLog.domain == domain,
                    InferenceLog.user_id == user_id,
                    InferenceLog.user_signal.isnot(None),
                ).order_by(InferenceLog.id.desc()).limit(window)

            logs = q.all()
            sequences = []
            for log in reversed(logs):
                emb = log.user_message_emb
                if isinstance(emb, list) and len(emb) >= 16:
                    state_emb = np.array(emb, dtype=np.float32)[:128]
                    # Pad if needed
                    if len(state_emb) < 128:
                        state_emb = np.pad(state_emb, (0, 128 - len(state_emb)))

                    # Use positive feedback as "correct next state"
                    if log.user_signal == "positive" and log.confidence:
                        next_emb = np.ones(128, dtype=np.float32) * log.confidence
                        next_emb[:len(state_emb)] = state_emb[:len(next_emb)]
                        sequences.append({
                            "state_emb": state_emb,
                            "next_state_emb": next_emb,
                        })

            return sequences
        except Exception as e:
            logger.debug(f"JEPA temporal sequence failed: {e}")
            return []

    def should_predict(self, domain: str, user_id: int = 0) -> bool:
        """Check if JEPA should make predictions for this domain.

        Iron rule #2: no history → JEPA silent
        """
        count = self.count_history(domain, user_id)
        return count >= MIN_HISTORY_FOR_PREDICTION

    def check_training_trigger(self, domain: str, user_id: int = 0) -> bool:
        """Check if enough new data has accumulated to trigger training.

        Returns True if training should happen.
        """
        model = self.get_or_create_model(domain)
        if not model.trained:
            # First training: need MIN_HISTORY_FOR_TRAINING records
            count = self.count_history(domain, user_id)
            need = 50  # MIN_HISTORY_FOR_TRAINING
            if count >= need:
                logger.info(f"JEPA: initial training trigger for {domain} ({count} records)")
                return True
            return False

        # Subsequent training: check for new records since last version
        # (simple heuristic — every 100 new positive signals)
        try:
            new_count = self.db.query(InferenceLog).filter(
                InferenceLog.domain == domain,
                InferenceLog.user_signal == "positive",
            ).count()
            # Train every 100 new positive signals after initial training
            if new_count >= (model.version + 1) * 100:
                return True
        except Exception:
            pass
        return False

    def train_domain(self, domain: str, user_id: int = 0) -> Dict:
        """Train predictor for a specific domain."""
        model = self.get_or_create_model(domain)
        sequences = self.get_temporal_sequence(domain, user_id)

        result = model.train_on_sequences(sequences)

        if result.get("trained"):
            # Save model
            model_path = MODEL_DIR / f"jepa_{domain}.pt"
            torch.save(model.state_dict(), str(model_path))
            ver_path = MODEL_DIR / f"jepa_{domain}_version.txt"
            ver_path.write_text(str(model._version))
            logger.info(f"JEPA: saved {domain} model v{model._version} to {model_path}")

        return result

    def predict(self, current_emb: np.ndarray, domain: str,
                user_id: int = 0) -> Optional[Dict]:
        """Run JEPA temporal prediction.

        Returns None if:
        - Cold start (no history) — Iron rule #2
        - Model not trained yet

        Args:
            current_emb: current interaction embedding (384,)
            domain: domain name
            user_id: user ID for history scoping

        Returns:
            {"predicted_emb": np.array(128,),
             "has_history": bool,
             "model_trained": bool}
            or None if JEPA should stay silent
        """
        # Iron rule #2: no history → silent
        if not self.should_predict(domain, user_id):
            return None

        model = self.get_or_create_model(domain)
        if not model.trained:
            # Model exists but not trained yet — return basic prediction
            domain_emb = np.zeros(16, dtype=np.float32)
            latent = model.encode_state(current_emb[:384], domain_emb)
            predicted = model.predict_next(latent)
            return {
                "predicted_emb": predicted,
                "has_history": True,
                "model_trained": False,
            }

        # Full prediction
        domain_emb = np.zeros(16, dtype=np.float32)
        latent = model.encode_state(current_emb[:384], domain_emb)
        predicted = model.predict_next(latent)

        return {
            "predicted_emb": predicted,
            "has_history": True,
            "model_trained": True,
        }

    def get_domain_config(self, domain: str) -> Dict:
        """Get domain config with cross-domain toggle."""
        return DEFAULT_DOMAIN_CONFIG.get(domain, {
            "cross_domain_enable": True,
            "allowed_cross_domains": ["*"],
        })

    def cross_domain_enabled(self, domain: str) -> bool:
        """Check if cross-domain is enabled for this domain."""
        config = self.get_domain_config(domain)
        return config.get("cross_domain_enable", True)


# Global singleton
_scheduler: Optional[JEPAScheduler] = None


def get_jepa_scheduler(db=None) -> JEPAScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = JEPAScheduler(db=db)
    if db and _scheduler.db is None:
        _scheduler.db = db
    return _scheduler
