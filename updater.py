"""Checks GitHub Releases for a newer version and runs the installer."""
import hashlib
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

GITHUB_REPO = "AubreyHeeren/windy-wallpaper"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"
USER_AGENT = "WindyLiveWallpaper-Updater"
INSTALLER_RE = re.compile(r"WindyWallpaper-Setup-.+\.exe")


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(remote, local):
    r, l = parse_version(remote), parse_version(local)
    return bool(r and l and r > l)


def _get_json(url, timeout=10):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def check_for_update(current):
    """Returns {version, notes, page, url, size, sha256} for a newer release, else None."""
    data = _get_json(API_URL)
    tag = data.get("tag_name", "")
    if data.get("draft") or data.get("prerelease") or not is_newer(tag, current):
        return None
    for asset in data.get("assets", []):
        url = asset.get("browser_download_url", "")
        if INSTALLER_RE.fullmatch(asset.get("name", "")) and url.startswith(DOWNLOAD_PREFIX):
            digest = asset.get("digest") or ""
            return {
                "version": tag.lstrip("vV"),
                "notes": (data.get("body") or "")[:1000],
                "page": data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest",
                "url": url,
                "size": int(asset.get("size") or 0),
                "sha256": digest[7:].lower() if digest.startswith("sha256:") else None,
            }
    return None  # release exists but the installer isn't uploaded yet


def download_installer(info, progress=None):
    dest = Path(tempfile.gettempdir()) / f"WindyWallpaper-Setup-{info['version']}.exe"
    req = urllib.request.Request(info["url"], headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or info.get("size") or 0)
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if info.get("size") and done != info["size"]:
        dest.unlink(missing_ok=True)
        raise ValueError("Download was incomplete")
    if info.get("sha256") and sha.hexdigest() != info["sha256"]:
        dest.unlink(missing_ok=True)
        raise ValueError("Download failed its checksum")
    return dest


def installed_via_setup(app_dir):
    """True when the app was installed by the Setup exe (it leaves an uninstaller next to it)."""
    return (Path(app_dir) / "unins000.exe").exists()


def launch_installer(path):
    """Start the installer after a short delay so this process has time to exit first."""
    cmd = f'cmd /c ping -n 4 127.0.0.1 >nul & "{path}" /SILENT /NORESTART /CLOSEAPPLICATIONS'
    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=0x08000000 | 0x00000200, close_fds=True)
