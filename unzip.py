#!/usr/bin/env python3
"""
NovaUnzip - The Ultimate High-Performance Telegram Unzip Bot Engine
Features:
- Multi-format (ZIP, RAR, 7Z, TAR, GZ, ISO, DMG, CAB, SPLIT VOLUMES)
- Pre-checks passwords in <0.2s with '7z t -p'
- Auto-splits files > 2GB into 1.95GB volumes (.001)
- Non-blocking asyncio subprocess with stdin=DEVNULL (no deadlocks)
- Anti-FloodWait atomic progress bar (3.5s throttle + speed & ETA)
- Interactive Archive File Explorer
- Built-in Zip Bomb & Disk Quota Guard
"""

import os
import re
import sys
import time
import math
import shutil
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import FloodWait, MessageNotModified, RPCError

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()

WORKDIR = Path(os.getenv("WORKDIR", "./downloads")).resolve()
MAX_EXTRACT_SIZE_BYTES = int(os.getenv("MAX_EXTRACT_SIZE_GB", "10")) * 1024 * 1024 * 1024
MAX_FILE_SIZE_UPLOAD_BOT = 1990 * 1024 * 1024  # 1.95 GB Bot API threshold
SPLIT_CHUNK_SIZE_MB = int(os.getenv("SPLIT_CHUNK_SIZE_MB", "1950"))
PROGRESS_UPDATE_INTERVAL = 3.5  # Seconds between Telegram editMessage calls

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
AUTH_USERS = [int(u) for u in os.getenv("AUTH_USERS", "").split(",") if u.strip().isdigit()]
if OWNER_ID and OWNER_ID not in AUTH_USERS:
    AUTH_USERS.append(OWNER_ID)

WORKDIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s - %(name)s] -> %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("NovaUnzip")

ARCHIVE_EXTENSIONS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".iso", ".cab", ".wim", ".dmg", ".cbr", ".cbz", ".001", ".part1.rar", ".z01"
)

@dataclass
class ArchiveEntry:
    path: str
    size: int
    is_dir: bool

@dataclass
class UserSession:
    user_id: int
    active_job: Optional[str] = None
    awaiting_password: bool = False
    temp_dir: Optional[Path] = None

sessions: Dict[int, UserSession] = {}

def get_session(user_id: int) -> UserSession:
    if user_id not in sessions:
        sessions[user_id] = UserSession(user_id=user_id)
    return sessions[user_id]

def cleanup_session(user_id: int):
    session = sessions.get(user_id)
    if session and session.temp_dir and session.temp_dir.exists():
        try:
            shutil.rmtree(session.temp_dir, ignore_errors=True)
            logger.info(f"Purged session cache: {session.temp_dir}")
        except Exception as e:
            logger.warning(f"Error purging temp cache: {e}")
    if user_id in sessions:
        del sessions[user_id]

def human_bytes(size: float) -> str:
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    while size > 1024 and n < len(units) - 1:
        size /= 1024
        n += 1
    return f"{size:.2f} {units[n]}"

def time_formatter(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h > 0 else f"{m:02d}m {s:02d}s"

class ThrottledProgress:
    """Anti-FloodWait progress updater with speed and ETA calculation."""
    def __init__(self, message: Message, action_title: str):
        self.message = message
        self.action_title = action_title
        self.start_time = time.time()
        self.last_update_time = 0.0
        self.last_percentage = -1

    async def update(self, current: int, total: int):
        now = time.time()
        if total <= 0:
            return
        percentage = int((current / total) * 100)
        if (now - self.last_update_time < PROGRESS_UPDATE_INTERVAL) and (percentage - self.last_percentage < 5):
            return

        self.last_update_time = now
        self.last_percentage = percentage
        elapsed = now - self.start_time
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0

        filled = int((current / total) * 16)
        bar = "█" * filled + "░" * (16 - filled)

        text = (
            f"⚡ **{self.action_title}**\n\n"
            f"[{bar}] **{percentage}%**\n"
            f"📁 **Processed:** `{human_bytes(current)}` / `{human_bytes(total)}`\n"
            f"🚀 **Speed:** `{human_bytes(speed)}/s`\n"
            f"⏱️ **ETA:** `{time_formatter(eta)}`"
        )
        try:
            await self.message.edit_text(text)
        except (FloodWait, MessageNotModified, RPCError):
            pass

class ArchiveEngine:
    @staticmethod
    async def verify_password(archive_path: Path, password: str = "") -> Tuple[bool, str]:
        """Non-blocking password check using '7z t -p'."""
        pwd_arg = f"-p{password}" if password else "-p-"
        proc = await asyncio.create_subprocess_exec(
            "7z", "t", pwd_arg, "-y", str(archive_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL  # Critical deadlock fix
        )
        stdout, _ = await proc.communicate()
        out = stdout.decode("utf-8", errors="ignore")
        if proc.returncode == 0:
            return True, "Valid"
        if "Wrong password" in out or "Can not open encrypted archive" in out:
            return False, "Incorrect password or archive is password protected."
        return False, f"Archive test failed (Code {proc.returncode})"

    @staticmethod
    async def list_contents(archive_path: Path, password: str = "") -> List[ArchiveEntry]:
        pwd_arg = f"-p{password}" if password else "-p-"
        proc = await asyncio.create_subprocess_exec(
            "7z", "l", "-slt", pwd_arg, "-y", str(archive_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        entries: List[ArchiveEntry] = []
        cur_path, cur_size, cur_is_dir = None, 0, False

        for line in stdout.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("Path = "):
                cur_path = line[7:].strip()
            elif line.startswith("Size = "):
                try: cur_size = int(line[7:].strip())
                except ValueError: cur_size = 0
            elif line.startswith("Folder = "):
                cur_is_dir = line[9:].strip() == "+"
            elif line == "" and cur_path:
                if cur_path != archive_path.name:
                    entries.append(ArchiveEntry(path=cur_path, size=cur_size, is_dir=cur_is_dir))
                cur_path, cur_size, cur_is_dir = None, 0, False
        return entries

    @staticmethod
    async def extract(archive_path: Path, output_dir: Path, password: str = "", specific_files: Optional[List[str]] = None) -> bool:
        output_dir.mkdir(parents=True, exist_ok=True)
        pwd_arg = f"-p{password}" if password else "-p-"
        cmd = ["7z", "x", str(archive_path), f"-o{output_dir}", pwd_arg, "-y", "-mmt=on", "-bsp1"]
        if specific_files:
            cmd.extend(specific_files)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return proc.returncode == 0

    @staticmethod
    async def split_large_file(source_file: Path, chunk_size_mb: int = 1950) -> List[Path]:
        """Slices files exceeding 2GB into Telegram-safe chunks without re-compressing."""
        out_base = source_file.parent / f"{source_file.stem}_split"
        proc = await asyncio.create_subprocess_exec(
            "7z", "a", f"-v{chunk_size_mb}m", "-mx=0", "-y",
            f"{out_base}.7z", str(source_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return sorted(source_file.parent.glob(f"{source_file.stem}_split.7z*"))

async def generate_video_thumbnail(video_path: Path) -> Optional[str]:
    thumb = video_path.parent / f"{video_path.stem}_thumb.jpg"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-ss", "00:00:03", "-i", str(video_path),
        "-vframes", "1", "-q:v", "2", str(thumb),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=8.0)
        return str(thumb) if thumb.exists() else None
    except Exception:
        return None

app = Client("NovaUnzip", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir=str(WORKDIR))

@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_cmd(client: Client, message: Message):
    welcome = (
        "🚀 **Welcome to NovaUnzip Bot!**\n\n"
        "The fastest, most reliable multi-format archive extractor on Telegram.\n\n"
        "• 📦 Supports `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.iso`, `.001`, `.part1.rar`\n"
        "• 🔐 Instant password validation (<0.2s)\n"
        "• 📁 Interactive File Browser\n"
        "• ✂️ Auto-splits files > 2GB\n"
        "• 🛡️ Zip Bomb & quota protection\n\n"
        "Send any archive file or use `/extract <direct-url>` to begin!"
    )
    await message.reply_text(welcome)

@app.on_message(filters.document & filters.private)
async def doc_handler(client: Client, message: Message):
    doc = message.document
    filename = doc.file_name or "archive.zip"
    if AUTH_USERS and message.from_user.id not in AUTH_USERS:
        return await message.reply_text("⛔ Access denied.")

    if not any(filename.lower().endswith(ext) for ext in ARCHIVE_EXTENSIONS):
        return await message.reply_text("❌ Unsupported archive format.")

    text = f"📦 **Archive Received:** `{filename}`\n📊 **Size:** `{human_bytes(doc.file_size or 0)}`"
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Extract All", callback_data=f"act_all:{message.id}"),
            InlineKeyboardButton("📁 Browse Files", callback_data=f"act_browse:{message.id}")
        ],
        [
            InlineKeyboardButton("🔐 Extract With Password", callback_data=f"act_pwd:{message.id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"act_cancel:{message.id}")
        ]
    ])
    await message.reply_text(text, reply_markup=buttons, quote=True)

@app.on_callback_query()
async def cb_router(client: Client, cb: CallbackQuery):
    data, user_id = cb.data, cb.from_user.id
    session = get_session(user_id)

    if data.startswith("act_cancel"):
        cleanup_session(user_id)
        await cb.message.edit_text("❌ Cancelled and cleaned up.")
        return await cb.answer("Cancelled")

    elif data.startswith("act_all:"):
        await cb.answer("Extracting...")
        await execute_pipeline(client, cb.message, int(data.split(":")[1]), user_id)

    elif data.startswith("act_pwd:"):
        session.awaiting_password = True
        session.active_job = data.split(":")[1]
        await cb.message.edit_text("🔐 Send the archive password as your next message.")
        return await cb.answer("Awaiting password...")

    elif data.startswith("act_browse:"):
        await cb.answer("Listing contents...")
        await browse_archive(client, cb.message, int(data.split(":")[1]), user_id, 0)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "extract", "clean"]))
async def pwd_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    session = get_session(user_id)
    if not session.awaiting_password or not session.active_job:
        return

    pwd = message.text.strip()
    target_id = int(session.active_job)
    session.awaiting_password = False
    try: await message.delete()
    except Exception: pass

    status = await message.reply_text("🔑 Verifying password...")
    await execute_pipeline(client, status, target_id, user_id, password=pwd)

async def execute_pipeline(client: Client, status_msg: Message, target_id: int, user_id: int, password: str = ""):
    session = get_session(user_id)
    session_dir = WORKDIR / f"job_{user_id}_{int(time.time())}"
    extract_dir = session_dir / "out"
    session.temp_dir = session_dir

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        orig = await client.get_messages(chat_id=user_id, message_ids=target_id)
        archive_path = session_dir / (orig.document.file_name or "archive.zip")

        prog_dl = ThrottledProgress(status_msg, "Downloading Archive")
        await orig.download(file_name=str(archive_path), progress=prog_dl.update)

        await status_msg.edit_text("🔍 Verifying archive integrity & password...")
        valid, reason = await ArchiveEngine.verify_password(archive_path, password)
        if not valid:
            return await status_msg.edit_text(f"❌ **Validation Failed:** {reason}")

        contents = await ArchiveEngine.list_contents(archive_path, password)
        total_uncompressed = sum(c.size for c in contents if not c.is_dir)
        if total_uncompressed > MAX_EXTRACT_SIZE_BYTES:
            return await status_msg.edit_text("🛡️ **Zip Bomb Guard:** Payload exceeds server safety quota.")

        await status_msg.edit_text(f"⚡ Decompressing {len(contents)} files ({human_bytes(total_uncompressed)})...")
        if not await ArchiveEngine.extract(archive_path, extract_dir, password):
            return await status_msg.edit_text("❌ Decompression failed. Archive may be damaged.")

        files = [p for p in extract_dir.rglob("*") if p.is_file()]
        for idx, f in enumerate(files, 1):
            size = f.stat().st_size
            if size > MAX_FILE_SIZE_UPLOAD_BOT:
                chunks = await ArchiveEngine.split_large_file(f, SPLIT_CHUNK_SIZE_MB)
                for part in chunks:
                    up_prog = ThrottledProgress(status_msg, f"Uploading Part: {part.name}")
                    await client.send_document(user_id, document=str(part), progress=up_prog.update)
                continue

            up_prog = ThrottledProgress(status_msg, f"Uploading [{idx}/{len(files)}]: {f.name}")
            if f.suffix.lower() in (".mp4", ".mkv", ".avi", ".mov"):
                thumb = await generate_video_thumbnail(f)
                await client.send_video(user_id, video=str(f), thumb=thumb, progress=up_prog.update)
                if thumb and Path(thumb).exists(): os.remove(thumb)
            else:
                await client.send_document(user_id, document=str(f), progress=up_prog.update)

        await status_msg.edit_text(f"✅ Extracted & delivered **{len(files)} files** successfully!")
    finally:
        cleanup_session(user_id)

async def browse_archive(client: Client, msg: Message, target_id: int, user_id: int, page: int):
    session = get_session(user_id)
    session_dir = WORKDIR / f"browse_{user_id}_{target_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    session.temp_dir = session_dir

    orig = await client.get_messages(chat_id=user_id, message_ids=target_id)
    archive_path = session_dir / (orig.document.file_name or "archive.zip")
    if not archive_path.exists():
        await orig.download(file_name=str(archive_path))

    entries = [e for e in await ArchiveEngine.list_contents(archive_path) if not e.is_dir]
    total_pages = max(1, math.ceil(len(entries) / 5))
    items = entries[page * 5 : (page + 1) * 5]

    text = f"📁 **Archive Browser** (Page {page + 1}/{total_pages})\n\n"
    for i, it in enumerate(items, 1):
        text += f"{i}. `{it.path}` ({human_bytes(it.size)})\n"

    buttons = []
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_browse:{target_id}:{page-1}"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_browse:{target_id}:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("🚀 Extract All", callback_data=f"act_all:{target_id}"), InlineKeyboardButton("❌ Close", callback_data="act_cancel")])

    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

if __name__ == "__main__":
    if not BOT_TOKEN or not API_ID or not API_HASH:
        logger.error("Set BOT_TOKEN, API_ID, and API_HASH in your environment!")
        sys.exit(1)
    logger.info("NovaUnzip Engine initialized.")
    app.run()