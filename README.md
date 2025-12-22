# 🤖 X File Bot — Advanced Telegram Auto Filter Bot

A **high-performance Telegram Auto Filter Bot** built with **Hydrogram + MongoDB**,  
designed for **ultra-fast search**, **smart file delivery**, **premium system**,  
and **Hindi / English adaptive UI**.

---

## 🚀 Features

### 🔎 Auto Filter System
- Ultra-fast MongoDB indexed search
- Smart keyword learning (offline, RAM based)
- AI-like search fallback suggestions
- Pagination with Prev / Next buttons
- One-user-one-result protection

---

### 📦 File Delivery (PM)
- Secure file delivery in private chat
- `/start` command auto-deleted after use
- Clean captions (no duplicate / no countdown spam)
- Silent auto-delete after defined time
- Resend button after expiry
- Stream / Download button support

---

### 👑 Premium System
- Premium & free user separation
- Grace period after expiry
- Auto downgrade watcher
- Smart premium expiry reminders (1d / 6h / 1h)
- Premium emoji UI theme
- Premium-only features support

---

### 🌍 Language System
- Hindi / English UI support
- User-based language override (PM)
- Group-based language toggle
- Auto language fallback
- Festival greeting per language
- Language-aware greetings

---

### 🎉 Smart Greetings
- Time-based greeting (Morning / Afternoon / Evening)
- Random emoji rotation
- Premium emoji mood
- Festival auto detect (Holi / Diwali / Eid)
- User-name based greetings

---

### ⚙️ Group Settings Panel
- `/settings` admin panel
- Search ON / OFF toggle
- Shortlink enable / disable
- Language toggle (hi / en / auto)
- Live UI update via inline buttons

---

### 📢 Broadcast System
- User broadcast
- Group broadcast
- FloodWait auto handling
- Invalid user / group auto cleanup

---

### 🔐 Security & Stability
- Protect content support
- Memory leak protection
- Auto cleanup background tasks
- Safe callback handling
- No duplicate message edits

---

## 🛠 Tech Stack

| Component | Used |
|---------|------|
| Language | Python 3.11 |
| Library | Hydrogram |
| Database | MongoDB |
| Async | asyncio + uvloop |
| Hosting | Koyeb / VPS |
| Cache | RAM-based |

---

## ⚡ Installation

```bash
git clone https://github.com/joneysinx/x
cd x-file-bot
pip install -r requirements.txt
