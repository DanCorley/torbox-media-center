import json
import os
import fnmatch
import logging

_overrides = None

def load_overrides():
    global _overrides
    path = os.getenv("METADATA_OVERRIDES_PATH", "/config/metadata_overrides.json")
    if not os.path.exists(path):
        _overrides = []
        return
    try:
        with open(path) as f:
            _overrides = json.load(f)
        logging.info(f"Loaded {len(_overrides)} metadata override(s) from {path}")
    except Exception as e:
        logging.error(f"Error loading metadata overrides from {path}: {e}")
        _overrides = []

def get_override(folder_hash: str, folder_name: str) -> dict | None:
    """
    Returns the first matching override entry for a given folder hash or name.

    Override entries are dicts with:
      - folder_hash (str): exact match on torrent/usenet hash
      - folder_name (str): glob pattern matched against the item folder name
      - search_query (str): replacement search query for the metadata API
    """
    if _overrides is None:
        load_overrides()
    for override in (_overrides or []):
        if "folder_hash" in override and override["folder_hash"] == folder_hash:
            return override
        if "folder_name" in override and fnmatch.fnmatch(folder_name, override["folder_name"]):
            return override
    return None
