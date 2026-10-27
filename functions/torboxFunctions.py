from library.http import api_http_client, general_http_client, requestWrapper
import httpx
from enum import Enum
import re
import PTN
from library.torbox import TORBOX_API_KEY
from library.app import SCAN_METADATA
from functions.mediaFunctions import constructSeriesTitle, cleanTitle, cleanYear
from functions.databaseFunctions import insertData
import os
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

class DownloadType(Enum):
    torrent = "torrents"
    usenet = "usenet"
    webdl = "webdl"

class IDType(Enum):
    torrents = "torrent_id"
    usenet = "usenet_id"
    webdl = "web_id"

ACCEPTABLE_MIME_TYPES = [
    "video/x-matroska",
    "video/mp4",
]

# PTN keys that indicate a main-feature release file; extras parse to a bare title.
RELEASE_TAG_KEYS = ("year", "resolution", "quality", "codec")

# Keywords that mark a file as a secondary extra (interview, trailer, featurette...)
# rather than the feature it ships with, e.g. "Interview - Greg McLean.mkv" or
# "Theatrical Trailer.mkv". Both match patterns below are built from this list.
EXTRA_KEYWORDS = (
    "interviews?", "featurettes?", "making of", "commentar(?:y|ies)", "bloopers?",
    "gag reels?", "deleted scenes?", "first look", "press conferences?",
    "behind the scenes", "red carpet", "sneak peeks?", "b-roll",
    "trailers?", "theatrical trailers?", "official trailers?",
)
# Extras that mimic release-style names still name themselves: either at the start
# of the title ("Theatrical Trailer.1080p"), as a " - Cast"/" - Crew" suffix, or via
# an episodeName ("Jungle.2017.Interview.Greg.McLean.1080p" -> episodeName "Interview Greg").
EXTRA_TITLE_PATTERN = re.compile(
    rf"^(?:{'|'.join(EXTRA_KEYWORDS)})|\s-\s(?:cast|crew)$",
    re.IGNORECASE,
)
EXTRA_EPISODE_NAME_PATTERN = re.compile(
    rf"\b(?:{'|'.join(EXTRA_KEYWORDS)})\b",
    re.IGNORECASE,
)

def normalizeForMatch(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())

def matchesItemTitle(title: str, item_name: str) -> bool:
    """True when a bare file title still looks like the torrent's own name (e.g. specials)."""
    file_norm = normalizeForMatch(title)
    item_norm = normalizeForMatch(PTN.parse(item_name).get("title", ""))
    if not file_norm or not item_norm:
        return False
    return file_norm.startswith(item_norm) or item_norm.startswith(file_norm)

def isExtraFile(title_data: dict, item_name: str) -> bool:
    """Detect secondary files (interviews, trailers, featurettes) using PTN-parsed data."""
    # Episodes with sXXeXX numbering are content, never extras.
    if title_data.get("season") is not None or title_data.get("episode") is not None:
        return False

    # The main feature carries release metadata; extras that mimic release-style
    # names still announce themselves via episodeName or a keyword pattern.
    if any(title_data.get(key) for key in RELEASE_TAG_KEYS):
        return bool(
            EXTRA_EPISODE_NAME_PATTERN.search(title_data.get("episodeName") or "")
            or EXTRA_TITLE_PATTERN.search(title_data.get("title") or "")
        )

    # No release tags and no episode numbering: only keep it if the title
    # still matches the torrent name (covers unnumbered specials), otherwise
    # it's an extra like "Cinephile.mkv" or "Interview - Greg McLean.mkv".
    return not matchesItemTitle(title_data.get("title") or "", item_name)

def getSkipReason(item, file, title_data: dict) -> str | None:
    """Return why a file should be skipped, or None if it is worth processing."""
    mimetype = file.get("mimetype") or ""
    if mimetype not in ACCEPTABLE_MIME_TYPES:
        return f"unacceptable mimetype {mimetype}"
    if "sample." in (file.get("name") or "").lower() or (title_data.get("title") or "").lower() == "sample":
        return "it looks like a sample"
    if isExtraFile(title_data, item.get("name", "")):
        return "it looks like an extra (interview/trailer/featurette)"
    return None

def process_file(item, file, type):
    """Process a single file and return the processed data"""
    title_data = PTN.parse(file.get("short_name"))

    skip_reason = getSkipReason(item, file, title_data)
    if skip_reason:
        logging.debug(f"Skipping file {file.get('short_name')} - {skip_reason}")
        return None
    
    data = {
        "item_id": item.get("id"),
        "type": type.value,
        "folder_name": item.get("name"),
        "DEBUG_name": item.get("name"),
        "DEBUG_hash": item.get("hash"),
        "DEBUG_file_name": file.get("short_name"),
        "folder_hash": item.get("hash"),
        "file_id": file.get("id"),
        "file_name": file.get("short_name"),
        "file_size": file.get("size"),
        "file_mimetype": file.get("mimetype"),
        "path": file.get("name"),
        "download_link": f"https://api.torbox.app/v1/api/{type.value}/requestdl?token={TORBOX_API_KEY}&{IDType[type.value].value}={item.get('id')}&file_id={file.get('id')}&redirect=true",
        "extension": os.path.splitext(file.get("short_name"))[-1],
        "created_at": item.get("created_at"),
    }

    if item.get("name") == item.get("hash"):
        item["name"] = title_data.get("title", file.get("short_name"))

    metadata = parseMetadata(title_data, file.get("short_name"), item.get("name"))
    data.update(metadata)
    logging.debug(data)
    insertData(data, type.value)
    return data

def getUserDownloads(type: DownloadType):
    offset = 0
    limit = 1000

    file_data = []
    
    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "bypass_cache": True,
        }
        try:
            response = api_http_client.get(f"/{type.value}/mylist", params=params)
        except Exception as e:
            logging.error(f"Error fetching {type.value} at offset {offset}: {e}")
            return None, False, f"Error fetching {type.value} at offset {offset}: {e}"
        if response.status_code != 200:
            return None, False, f"Error fetching {type.value} at offset {offset}. {response.status_code}"
        try:
            data = response.json().get("data", [])
        except Exception as e:
            logging.error(f"Error parsing {type.value} at offset {offset}: {e}")
            logging.error(f"Response: {response.text}")
            return None, False, f"Error parsing {type.value} at offset {offset}. {e}"
        if not data:
            break
        file_data.extend(data)
        offset += limit
        if len(data) < limit:
            break

    if not file_data:
        return None, True, f"No {type.value} found."
    
    logging.debug(f"Fetched {len(file_data)} {type.value} items from API.")
    
    files = []
    
    # Get the number of CPU cores for parallel processing
    max_workers = int(multiprocessing.cpu_count() * 2 - 1)
    logging.info(f"Processing files with {max_workers} parallel threads")
    
    # Collect all files to process
    files_to_process = []
    for item in file_data:
        if not item.get("cached", False):
            continue
        for file in item.get("files", []):
            files_to_process.append((item, file))
    
    # Process files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_file, item, file, type): (item, file) 
            for item, file in files_to_process
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            try:
                data = future.result()
                if data:
                    files.append(data)
            except Exception as e:
                item, file = future_to_file[future]
                logging.error(f"Error processing file {file.get('short_name', 'unknown')}: {e}")
                logging.error(traceback.format_exc())
            
    return files, True, f"{type.value.capitalize()} fetched successfully."

def parseMetadata(title_data: dict, file_name: str, item_name: str) -> dict:
    extension = os.path.splitext(file_name)[-1]
    base_metadata = {
        "metadata_title": cleanTitle(title_data.get("title", os.path.splitext(file_name)[0])),
        "metadata_link": None,
        "metadata_mediatype": "movie",
        "metadata_image": None,
        "metadata_backdrop": None,
        "metadata_years": None,
        "metadata_season": None,
        "metadata_episode": None,
        "metadata_filename": file_name,
        "metadata_rootfoldername": item_name,
    }
    if not SCAN_METADATA:
        return base_metadata

    raw_title = title_data.get("title") or os.path.splitext(file_name)[0]
    title = cleanTitle(raw_title)
    year = cleanYear(title_data.get("year"))
    season = title_data.get("season")
    episode = title_data.get("episode")
    root_folder = f"{title} ({year})" if year else title

    base_metadata.update({
        "metadata_title": title,
        "metadata_years": year,
        "metadata_season": season,
        "metadata_episode": episode,
        "metadata_rootfoldername": root_folder,
    })

    if season is not None or episode is not None:
        season_num = season if season is not None else 1
        se_tag = constructSeriesTitle(season=season_num, episode=episode)
        fname = f"{title} {se_tag}{extension}" if se_tag else f"{title}{extension}"
        base_metadata["metadata_mediatype"] = "series"
        base_metadata["metadata_filename"] = fname
        base_metadata["metadata_foldername"] = constructSeriesTitle(season=season_num, folder=True)
    else:
        fname = f"{title} ({year}){extension}" if year else f"{title}{extension}"
        base_metadata["metadata_mediatype"] = "movie"
        base_metadata["metadata_filename"] = fname

    return base_metadata

def getDownloadLink(url: str):
    response = requestWrapper(general_http_client, "GET", url)
    if response.status_code == httpx.codes.TEMPORARY_REDIRECT or response.status_code == httpx.codes.PERMANENT_REDIRECT or response.status_code == httpx.codes.FOUND:
        return response.headers.get('Location')
    return url

def downloadFile(url: str, size: int, offset: int = 0):
    headers = {
        "Range": f"bytes={offset}-{offset + size - 1}",
        **general_http_client.headers,
    }
    response = requestWrapper(general_http_client, "GET", url, headers=headers)
    if response.status_code == httpx.codes.OK:
        return response.content
    elif response.status_code == httpx.codes.PARTIAL_CONTENT:
        return response.content
    else:
        logging.error(f"Error downloading file: {response.status_code}")
        raise Exception(f"Error downloading file: {response.status_code}")
    
