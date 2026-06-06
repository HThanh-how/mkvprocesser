"""Upload YouTube qua Data API v3. Nhanh nho chunksize=-1. Mien phi."""
import os
import random
import time

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .metadata import bcp47
from .netutil import parse_proxy

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
_RETRY = {500, 502, 503, 504}


def _proxy_info(url):
    """URL proxy -> httplib2.ProxyInfo (ho tro http/https/socks5/socks4)."""
    p = parse_proxy(url)
    if not p:
        return None
    import httplib2
    types = {
        "socks5": httplib2.socks.PROXY_TYPE_SOCKS5,
        "socks5h": httplib2.socks.PROXY_TYPE_SOCKS5,
        "socks4": httplib2.socks.PROXY_TYPE_SOCKS4,
    }
    ptype = types.get(p["scheme"], httplib2.socks.PROXY_TYPE_HTTP)
    return httplib2.ProxyInfo(ptype, p["host"], int(p["port"]),
                              proxy_user=p["user"], proxy_pass=p["pass"])


def get_service(client_secret, token_path, proxy=""):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    if proxy:  # day toan bo upload + caption + playlist qua proxy
        import google_auth_httplib2
        import httplib2
        authed = google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(proxy_info=_proxy_info(proxy)))
        return build("youtube", "v3", http=authed)
    return build("youtube", "v3", credentials=creds)


def _retry(req, tries=5):
    for i in range(tries):
        try:
            return req.execute()
        except HttpError as e:
            if e.resp.status in _RETRY and i < tries - 1:
                time.sleep(2 ** i + random.random())
                continue
            raise


def upload_video(yt, path, title, description="", tags=None, privacy="private",
                 category_id="22", language=None, log=print):
    body = {"snippet": {"title": title[:100], "description": description,
                        "tags": tags or [], "categoryId": str(category_id)},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    code = bcp47(language, "")
    if code:
        body["snippet"]["defaultAudioLanguage"] = code
    media = MediaFileUpload(path, chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    log(f"  uploaded id={resp['id']}  ({title})")
    return resp["id"]


def upload_caption(yt, video_id, srt_path, language="vi", name="", log=print):
    language = bcp47(language, "vi")
    body = {"snippet": {"videoId": video_id, "language": language,
                        "name": name, "isDraft": False}}
    media = MediaFileUpload(srt_path, mimetype="application/octet-stream", resumable=True)
    _retry(yt.captions().insert(part="snippet", body=body, media_body=media))
    log(f"  caption [{language}] added")


def get_or_create_playlist(yt, cache, title, privacy="private", log=print):
    if title in cache:
        return cache[title]
    resp = _retry(yt.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": title[:150]}, "status": {"privacyStatus": privacy}}))
    cache[title] = resp["id"]
    log(f"  playlist: {title} ({resp['id']})")
    return resp["id"]


def add_to_playlist(yt, playlist_id, video_id, log=print):
    _retry(yt.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": playlist_id,
        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}))
    log("  added to playlist")


def list_uploaded_titles(yt):
    """Liet ke tua cac video DA UPLOAD cua kenh (re: uploads playlist, ~1 unit/50).

    Tra ve set[str] tua tho. Dung de doi chieu 'da co tren YouTube' ma khong ton
    quota nhu search.list (100 unit/lan).
    """
    ch = _retry(yt.channels().list(part="contentDetails", mine=True))
    items = ch.get("items", []) if ch else []
    if not items:
        return set()
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    titles, token = set(), None
    while True:
        resp = _retry(yt.playlistItems().list(
            part="snippet", playlistId=uploads, maxResults=50, pageToken=token))
        for it in resp.get("items", []):
            t = (it.get("snippet", {}) or {}).get("title", "")
            if t:
                titles.add(t)
        token = resp.get("nextPageToken")
        if not token:
            break
    return titles
