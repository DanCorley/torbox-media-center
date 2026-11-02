from library.filesystem import MOUNT_METHOD
from functions.appFunctions import (
    refresh_lock,
    getAllUserDownloadsFresh,
    getAllUserDownloadsWithStatus,
)


def _record_key(record):
    return (record.get("type"), record.get("item_id"), record.get("file_id"))


def _record_fingerprint(record):
    return (
        record.get("metadata_filename"),
        record.get("metadata_rootfoldername"),
        record.get("metadata_foldername"),
        record.get("download_link"),
        record.get("file_size"),
    )


def diffRecords(old_records, new_records):
    """Return counts of added, removed and updated records."""
    old_map = {_record_key(record): _record_fingerprint(record) for record in old_records}
    new_map = {_record_key(record): _record_fingerprint(record) for record in new_records}

    added = new_map.keys() - old_map.keys()
    removed = old_map.keys() - new_map.keys()
    updated = {
        key for key in new_map.keys() & old_map.keys() if new_map[key] != old_map[key]
    }

    return {
        "added": len(added),
        "removed": len(removed),
        "updated": len(updated),
        "changed": len(added) + len(removed) + len(updated),
    }


def performRefresh():
    """
    Fetch from TorBox, replace successful database types, then reconcile
    the mount. Callers should hold refresh_lock or accept the re-entrant
    acquisition below.
    """
    with refresh_lock:
        old_records, old_errors = getAllUserDownloadsWithStatus()
        fetch_result = getAllUserDownloadsFresh()
        new_records, new_errors = getAllUserDownloadsWithStatus()

        result = {
            **diffRecords(old_records, new_records),
            "partial": bool(old_errors or fetch_result["errors"] or new_errors),
            "errors": {**old_errors, **fetch_result["errors"], **new_errors},
            "mode": MOUNT_METHOD,
        }

        if MOUNT_METHOD == "fuse":
            from functions.fuseFilesystemFunctions import requestFuseRefresh
            result["mount"] = {"refreshed": requestFuseRefresh(wait=True)}
        else:
            from functions.stremFilesystemFunctions import runStrm
            mount = runStrm()
            result["mount"] = mount
            # A missing/corrupt .strm file can be repaired even when the DB
            # record set did not change; still ask Jellyfin to rescan.
            result["changed"] = max(result["changed"], mount["changed"])
            if mount.get("error"):
                result["partial"] = True

        result["refreshed"] = True
        return result
