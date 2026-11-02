from library.app import RAW_MODE
from functions.torboxFunctions import getUserDownloads, DownloadType
from library.filesystem import MOUNT_METHOD, MOUNT_PATH
from library.app import MOUNT_REFRESH_TIME
from functions.databaseFunctions import getAllData, replaceData
import logging
import os
import shutil
import threading
from library.app import getCurrentVersion
import git

# Serializes an API refresh with a mount rebuild. Re-entrant so a caller can
# hold it across getAllUserDownloadsFresh() and runStrm().
refresh_lock = threading.RLock()

def initializeFolders():
    folders = [MOUNT_PATH]
    if not RAW_MODE:
        folders.extend([
            os.path.join(MOUNT_PATH, "movies"),
            os.path.join(MOUNT_PATH, "series"),
        ])
    for folder in folders:
        if os.path.exists(folder):
            logging.debug(f"Folder {folder} already exists. Deleting...")
            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
        else:
            logging.debug(f"Creating folder {folder}...")
            os.makedirs(folder, exist_ok=True)

def getAllUserDownloadsFresh():
    """
    Fetch every type first, then replace that type's database.
    A type whose fetch fails keeps its previous rows; nothing is cleared
    before the API call succeeds.
    """
    all_downloads = []
    errors = {}

    with refresh_lock:
        logging.info("Fetching all user downloads...")
        for download_type in DownloadType:
            logging.debug(f"Fetching {download_type.value} downloads...")
            downloads, success, detail = getUserDownloads(download_type)
            if not success:
                logging.error(f"Error fetching {download_type.value}: {detail}")
                errors[download_type.value] = detail
                continue

            success, detail = replaceData(downloads or [], download_type.value)
            if not success:
                logging.error(f"Error storing {download_type.value}: {detail}")
                errors[download_type.value] = detail
                continue

            all_downloads.extend(downloads or [])
            logging.debug(f"Fetched {len(downloads or [])} {download_type.value} downloads.")

    return {"downloads": all_downloads, "errors": errors}

def getAllUserDownloadsWithStatus():
    """
    Read all download types from the local database.
    Returns (records, errors) so callers can distinguish an empty library
    from a database read failure.
    """
    all_downloads = []
    errors = {}
    for download_type in DownloadType:
        logging.debug(f"Fetching {download_type.value} downloads...")
        downloads, success, detail = getAllData(download_type.value)
        if not success:
            logging.error(f"Error fetching {download_type.value}: {detail}")
            errors[download_type.value] = detail
            continue
        all_downloads.extend(downloads)
        logging.debug(f"Fetched {len(downloads)} {download_type.value} downloads.")
    return all_downloads, errors

def getAllUserDownloads():
    downloads, _ = getAllUserDownloadsWithStatus()
    return downloads

def bootUp():
    logging.debug("Booting up...")
    logging.info("Mount method: %s", MOUNT_METHOD)
    logging.info("Mount path: %s", MOUNT_PATH)
    logging.info("Mount refresh time: %s %s", MOUNT_REFRESH_TIME, "hours")

    # check version
    latest_version = getLatestVersion()
    current_version = getCurrentVersion()

    if latest_version != current_version:
        logging.warning(f"!!! A new version of TorBox Media Center is available: {latest_version}. You are running version: {current_version}. Please consider updating to the latest version. !!!")

    initializeFolders()

    return True

def getMountMethod():
    return MOUNT_METHOD

def getMountPath():
    return MOUNT_PATH

def getMountRefreshTime():
    return MOUNT_REFRESH_TIME

def getLatestVersion():
    try:
        url = "https://github.com/torbox-app/torbox-media-center.git"
        g = git.cmd.Git()
        tags_output = g.ls_remote("--tags", url)
        tags = [line.split("refs/tags/")[1] for line in tags_output.splitlines() if "refs/tags/" in line]
        tags = [tag for tag in tags if not tag.endswith("^{}")]
        tags.sort(key=lambda s: list(map(int, s.lstrip('v').split('.'))))
        latest_tag = tags[-1] if tags else None
        return latest_tag
    except Exception as e:
        logging.error(f"Error fetching latest version: {e}")
        return None

