import json
import os
from pathlib import Path
from typing import Dict, Any

def load_mapping_config() -> Dict[str, Any]:
    """Charge la configuration du mapping SAGE → BFC"""
    config_path = Path(__file__).parent / "data" / "mapping_sage_bfc.json"
    
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