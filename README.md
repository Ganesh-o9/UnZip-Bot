# 🚀 NovaUnzip: The Ultimate Telegram Unzip Bot

**NovaUnzip** is a next-generation Telegram Bot engine engineered specifically to overcome the architectural flaws, crashes, and rate-limit traps found in legacy unzip bots like **EDM115/unzip-bot**, **Itz-fork/Unzipper-Bot**, **IDN-C-X/IDN-Unzip-Bot**, and **LISA-KOREA/UnZip-Bot**.

---

## ⚡ Architectural Comparison Matrix

| Feature | EDM115/unzip-bot | Itz-fork/Unzipper | IDN-C-X | LISA-KOREA | **NovaUnzip (This Engine)** |
|---|---|---|---|---|---|
| **Underlying Subprocess** | `asyncio` 7z | `subprocess` | `os.system` | `subprocess` | **Non-blocking `7z` with `-bsp1 -y -p-` (No stdin freeze)** |
| **Password Pre-Verification** | ❌ (Extracts blindly) | ❌ | ❌ | ❌ | **✅ Verified in <1s via `7z t -p` before extracting** |
| **Files > 2GB Handling** | ⚠️ Partial split | ❌ Crashes | ❌ Crashes | ❌ Crashes | **✅ Auto-chunks into 1.95GB parts (`.7z.001`)** |
| **Interactive File Picker** | ❌ Dumps all files | ❌ Dumps all | ❌ Dumps all | ❌ Dumps all | **✅ Paginated Inline Tree Explorer** |
| **Split Archive Assembly** | ⚠️ Complex/MongoDB | ❌ Broken | ❌ Broken | ❌ | **✅ Automated Multi-part Session Collector** |
| **FloodWait Rate Limiter** | ❌ Often throttled | ❌ Flood 429 | ❌ Flood 429 | ❌ | **✅ Atomic 3.5s Throttle + Speed/ETA math** |
| **Zip Bomb Defense** | ❌ Disk fill risk | ❌ | ❌ | ❌ | **✅ Checks Uncompressed Ratio & Size Quotas** |
| **Video Thumbnail Engine** | ⚠️ Partial | ❌ None | ❌ None | ❌ | **✅ Fast ffmpeg Frame Extraction + Duration** |
| **Direct URL Extractor** | ✅ `requests` | ❌ None | ⚠️ Basic | ⚠️ Basic | **✅ High-speed async `aiohttp` streaming** |
| **Standalone Mode** | ❌ Requires MongoDB | ✅ Yes | ✅ Yes | ✅ Yes | **✅ 100% Zero-DB needed (Optional Mongo)** |

---

## 🛠️ Quick Start (Docker)

1. Clone or download this project.
2. Create `.env` from `.env.example` and fill in:
   ```ini
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   OWNER_ID=your_telegram_id
   ```
3. Run with Docker Compose:
   ```bash
   docker compose up -d --build
   ```

---

## 💻 Manual VPS Setup

```bash
chmod +x deploy.sh
sudo ./deploy.sh
```
