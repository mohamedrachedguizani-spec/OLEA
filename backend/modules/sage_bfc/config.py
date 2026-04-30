import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, Any

_mapping_path = Path(__file__).parent / "data" / "mapping_sage_bfc.json"
_mapping_lock = threading.Lock()

def load_mapping_config() -> Dict[str, Any]:
    """Charge la configuration du mapping SAGE → BFC"""
    config_path = _mapping_path
    
    if not config_path.exists():
        raise FileNotFoundError(f"Fichier mapping non trouvé: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Singleton pour le mapping
_mapping_config = None

def get_mapping_config() -> Dict[str, Any]:
    global _mapping_config
    if _mapping_config is None:
        _mapping_config = load_mapping_config()
    return _mapping_config

def reload_mapping_config() -> Dict[str, Any]:
    """Force le rechargement du mapping depuis le fichier JSON"""
    global _mapping_config
    _mapping_config = load_mapping_config()
    return _mapping_config

def save_mapping_config(mapping: Dict[str, Any]) -> None:
    """Sauvegarde atomique du mapping JSON"""
    if not isinstance(mapping, dict):
        raise ValueError("Le mapping doit être un objet JSON")

    config_path = _mapping_path
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with _mapping_lock:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="mapping_sage_bfc_", suffix=".json", dir=str(config_path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, config_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    reload_mapping_config()