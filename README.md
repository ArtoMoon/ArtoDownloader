# ArtoDownloader

<p align="center"><img src="assets/icon.png" width="128" alt="ArtoDownloader"></p>

<p align="center">
  <b>A multi-segment, pausable download manager inspired by IDM, with a LibreWolf / Firefox extension.</b><br>
  English · <a href="README.tr.md">Türkçe</a>
</p>

The browser extension intercepts downloads and hands them off to ArtoDownloader, which splits each file into parts, downloads them in parallel and lets you pause and resume at any time.

## Features
- **8 parallel connections** using HTTP `Range` requests. Parts are written straight to their offset in the file, so there is no merge step at the end.
- **Dynamic segmentation**: an idle connection takes over half of the part with the most work left, so a slow part never stalls the download.
- **Pause / resume**: progress is stored in a `.arto` state file. You can close the window and continue later.
- **Automatic retries**. If a server does not support `Range`, it falls back to a single stream.
- **Modern dark UI** with live speed, a speed graph, a segment map and ETA.
- **Fast start-up**: the probe connection is reused as the first part, and large files use NTFS sparse files instead of slow pre-allocation.
- **Safe fallback**: if the native host fails, the browser downloads the file itself.

## Installation
1. Download `ArtoDownloader-Setup.exe` from the [Releases](../../releases) page and run it.
2. At the end of the setup, keep **"Install the extension in LibreWolf"** checked and confirm the prompt.
   To install manually: `about:addons` → gear icon → **Install Add-on From File** → `artodownloader.xpi` in the install folder.
3. If you get a signature error, set `xpinstall.signatures.required` to `false` in `about:config`.

No admin rights are needed. Everything is installed under `%LOCALAPPDATA%\Programs\ArtoDownloader`.

## How it works
```
LibreWolf extension ──native messaging──▶ ArtoHost.exe ──▶ ArtoDownloader.exe (UI + download engine)
```
1. The extension cancels the browser download and sends the URL, cookies and referer to the native host.
2. The host launches the ArtoDownloader window.
3. The engine probes the server (`Content-Length`, `Accept-Ranges`, `ETag`), splits the file into segments and downloads them concurrently.

| Path | Purpose |
| --- | --- |
| `extension/` | Browser extension (captures downloads, forwards cookies and referer) |
| `host/host.py` | Native messaging host |
| `host/app.py` | Download engine |
| `host/ui.py` | Desktop UI (tkinter) |
| `setup.iss` | Inno Setup installer script |
| `build.ps1` | Build script (PyInstaller + Inno Setup) |

## Building from source
Requirements: Python 3.10+, `pip install pyinstaller pillow`, and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The installer is written to `dist\ArtoDownloader-Setup.exe`.

## License
MIT. See [LICENSE](LICENSE).
