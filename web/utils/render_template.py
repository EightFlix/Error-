import urllib.parse
import html

from info import BIN_CHANNEL, URL
from utils import temp


WATCH_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>

<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css"/>

<style>
:root {
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #64748b;
    --accent: #ef4444;
    --btn: #e5e7eb;
}

body.dark {
    --bg: #0f172a;
    --card: #1e293b;
    --text: #f8fafc;
    --muted: #94a3b8;
    --btn: #111827;
}

* {
    box-sizing: border-box;
    font-family: system-ui, -apple-system, sans-serif;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
}

header {
    padding: 14px 16px;
    background: var(--card);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 700;
}

.brand {
    color: var(--accent);
    font-size: 18px;
}

.toggle {
    cursor: pointer;
    font-size: 18px;
}

.container {
    max-width: 880px;
    margin: auto;
    padding: 14px;
}

.card {
    background: var(--card);
    border-radius: 12px;
    padding: 14px;
    border: 1px solid #e5e7eb;
}

body.dark .card {
    border-color: #334155;
}

video {
    width: 100%;
    border-radius: 10px;
    background: black;
}

.title {
    margin-top: 12px;
    font-size: 17px;
    font-weight: 600;
}

.tags {
    margin: 8px 0;
}

.tag {
    display: inline-block;
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 999px;
    background: rgba(239,68,68,.12);
    color: var(--accent);
    margin-right: 6px;
}

.actions {
    margin-top: 12px;
    display: grid;
    gap: 10px;
}

.btn {
    padding: 11px;
    text-align: center;
    border-radius: 8px;
    font-weight: 600;
    background: var(--btn);
    color: var(--text);
    text-decoration: none;
}

.btn.primary {
    background: var(--accent);
    color: #fff;
}

.note {
    margin-top: 12px;
    padding: 10px;
    background: rgba(0,0,0,.05);
    border-radius: 8px;
    font-size: 13px;
    color: var(--muted);
    text-align: center;
}

footer {
    margin: 18px 0;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
}
</style>
</head>

<body>

<header>
    <div class="brand">FAST FINDER</div>
    <div class="toggle" onclick="toggleMode()">🌙</div>
</header>

<div class="container">
    <div class="card">

        <video class="player" controls playsinline src="{src}"></video>

        <div class="title">{file_name}</div>

        <div class="tags">
            <span class="tag">STREAM</span>
            <span class="tag">FAST</span>
            <span class="tag">NO ADS</span>
        </div>

        <div class="actions">
            <a class="btn primary" href="{src}" download>⬇ Direct Download</a>
            <a class="btn" href="vlc://{src}">▶ Play in VLC</a>
        </div>

        <div class="note">
            If video not playing, use VLC or MX Player.
        </div>

    </div>

    <footer>
        © 2025 Fast Finder Bot
    </footer>
</div>

<script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>
<script>
new Plyr('.player');

function toggleMode(){
    document.body.classList.toggle("dark");
    localStorage.setItem("mode",
        document.body.classList.contains("dark") ? "dark" : "light"
    );
}

(function(){
    if(localStorage.getItem("mode")==="dark"){
        document.body.classList.add("dark");
    }
})();
</script>

</body>
</html>
"""


async def media_watch(message_id: int):
    media_msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)

    if not media_msg or not media_msg.media:
        return "<h1>File not found</h1>"

    media = getattr(media_msg, media_msg.media.value, None)

    if not media or not media.mime_type.startswith("video"):
        return "<h1>This file is not streamable</h1>"

    src = urllib.parse.urljoin(URL, f"download/{message_id}")
    file_name = html.escape(media.file_name or "Video")

    return (
        WATCH_TEMPLATE
        .replace("{title}", f"Watch - {file_name}")
        .replace("{file_name}", file_name)
        .replace("{src}", src)
    )
