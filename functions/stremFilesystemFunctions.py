import os
import glob
import logging
import threading
from library.app import RAW_MODE
from library.filesystem import MOUNT_PATH
from functions.appFunctions import getAllUserDownloadsWithStatus, refresh_lock

MEDIA_DIRS = {"movie": "movies", "series": "series", "anime": "series"}


def generateFolderPath(data: dict) -> str | None:
    """
    Takes in a user download and returns the folder path for the download.
    """
    if RAW_MODE:
        original_path = data.get("path")
        return os.path.dirname(original_path) if original_path else None

    root_folder: str | None = data.get("metadata_rootfoldername", None)
    metadata_foldername: str | None = data.get("metadata_foldername", None)
    mediatype = data.get("metadata_mediatype")

    if not root_folder:
        return None

    if mediatype in ("series", "anime"):
        if not metadata_foldername:
            return None
        return os.path.join(root_folder, metadata_foldername)

    if mediatype == "movie":
        return root_folder

    logging.debug(f"Unknown media type {mediatype!r} for {data.get('file_name')!r}")
    return None


def generateStremFile(file_path: str, url: str, type: str, file_name: str, download=None) -> str:
    """
    Write a .strm file only when its contents changed.
    Returns "added", "updated", "unchanged", or "error".
    """
    if RAW_MODE:
        original_path = download.get("path") if download else None
        if not original_path:
            return "error"
        full_path = os.path.join(MOUNT_PATH, os.path.dirname(original_path))
    else:
        media_dir = MEDIA_DIRS.get(type)
        if media_dir is None:
            logging.error(f"Unknown media type {type!r} for {file_name}")
            return "error"
        full_path = os.path.join(MOUNT_PATH, media_dir, file_path)

    strm_file_path = os.path.join(full_path, f"{file_name}.strm")
    tmp_path = f"{strm_file_path}.tmp.{os.getpid()}.{threading.get_ident()}"

    try:
        os.makedirs(full_path, exist_ok=True)

        existing = None
        if os.path.exists(strm_file_path):
            try:
                with open(strm_file_path, "r", encoding="utf-8") as file:
                    existing = file.read()
            except OSError:
                existing = None  # overwrite an unreadable file

        if existing == url:
            return "unchanged"

        with open(tmp_path, "w", encoding="utf-8") as file:
            file.write(url)
        os.replace(tmp_path, strm_file_path)
        logging.debug(f"Created strm file: {strm_file_path}")
        return "updated" if existing is not None else "added"
    except FileNotFoundError as e:
        logging.error(f"Error creating strm file (likely bad naming scheme of file): {e}")
    except OSError as e:
        logging.error(f"Error creating strm file (likely bad or missing permissions): {e}")
    except Exception as e:
        logging.error(f"Error creating strm file: {e}")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

    return "error"


def runStrm():
    with refresh_lock:
        return _runStrm()


def _runStrm():
    all_downloads, errors = getAllUserDownloadsWithStatus()
    # Get all existing .strm files
    existing_strm_files = set(glob.glob(os.path.join(MOUNT_PATH, "**", "*.strm"), recursive=True))

    counts = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0, "error": 0}
    new_strm_files = set()

    for download in all_downloads:
        file_path = generateFolderPath(download)
        if file_path is None:
            continue

        mediatype = download.get("metadata_mediatype")
        file_name = download.get("metadata_filename")
        if not file_name:
            continue

        if RAW_MODE:
            strm_path = os.path.join(MOUNT_PATH, file_path, f"{file_name}.strm")
        else:
            media_dir = MEDIA_DIRS.get(mediatype)
            if media_dir is None:
                continue
            strm_path = os.path.join(MOUNT_PATH, media_dir, file_path, f"{file_name}.strm")

        new_strm_files.add(strm_path)
        status = generateStremFile(
            file_path,
            download.get("download_link"),
            mediatype,
            file_name,
            download,
        )
        counts[status] = counts.get(status, 0) + 1

    # A failed type would look like a removed download, so never delete
    # stale files while the database read is incomplete.
    if errors:
        logging.error("Skipping stale .strm cleanup because a database read failed: %s", errors)
    else:
        for strm_file in existing_strm_files - new_strm_files:
            try:
                os.remove(strm_file)
                counts["removed"] += 1
                # Remove empty directories
                directory = os.path.dirname(strm_file)
                while directory != MOUNT_PATH and not os.listdir(directory):
                    os.rmdir(directory)
                    directory = os.path.dirname(directory)
            except Exception as e:
                logging.error(f"Error removing .strm file: {e}")
                counts["error"] += 1

    counts["changed"] = counts["added"] + counts["updated"] + counts["removed"]
    logging.debug("STRM reconcile: %s", counts)
    return counts


def unmountStrm():
    """
    Deletes all strm files and any subfolders in the mount path for cleaning up.
    """
    folders = [
        MOUNT_PATH,
        os.path.join(MOUNT_PATH, "movies"),
        os.path.join(MOUNT_PATH, "series"),
    ]
    for folder in folders:
        if os.path.exists(folder):
            logging.debug(f"Folder {folder} already exists. Deleting...")
            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)
                if os.path.isdir(item_path):
                    import shutil
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
