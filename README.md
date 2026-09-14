# 🛠️ fayzillo-agy-tools

> **JarvisOS & Antigravity (AGY) Autonomous CLI Toolsuite**  
> *AI agentlari (Antigravity CLI, JarvisOS Core AI Engine) va dasturchilar uchun ultra-tezkor AST tahlili, multimodal media razvedkasi, biometrik yuz tanish, xavfsiz sandbox sinovlari va 95%+ token tejamkorligini ta'minlovchi avtonom tizim vositalari majmuasi.*

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/fummatov92/fayzillo-agy-tools)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20Ubuntu%20%7C%20macOS-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)]()
[![Modules](https://img.shields.io/badge/modules-10%20Active%20Toolsuites-purple.svg)]()

---

## 📑 Mundarija

1. [💡 Loyiha Haqida va Falsafasi](#-loyiha-haqida-va-falsafasi)
2. [⚡ Asosiy Afzalliklar & Benchmark](#-asosiy-afzalliklar--benchmark)
3. [💻 Tizim Talablari (System Requirements)](#-tizim-talablari-system-requirements)
4. [🚀 O'rnatish Qo'llanmasi (Installation Guide)](#-ornatish-qollanmasi-installation-guide)
   - [A. Tezkor Avtomatik O'rnatish](#a-tezkor-avtomatik-ornatish-tavsiya-etiladi)
   - [B. Qo'lda (Manual) O'rnatish](#b-qolda-manual-ornatish)
5. [⚙️ Konfiguratsiya Fayllari (.env, config.py, .apiignore)](#️-konfiguratsiya-fayllari)
6. [🛠 Modullar va CLI Buyruqlar Qo'llanmasi](#-modullar-va-cli-buyruqlar-qollanmasi)
   - [1. `sys` — Tizim Monitoringi, Portlar va Audit Jurnali](#1-sys--tizim-monitoringi-portlar-va-audit-jurnali)
   - [2. `code` — AST Kod Tahlili, Endpointlar va Signaturalar](#2-code--ast-kod-tahlili-endpointlar-va-signaturalar)
   - [3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi](#3-secure--xavfsizlik-va-maxfiy-kalitlar-sanitizatsiyasi)
   - [4. `debug` — Stack Trace Tahlili va Sintaksis Diagnostikasi](#4-debug--stack-trace-tahlili-va-sintaksis-diagnostikasi)
   - [5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing](#5-doc--api-kontraktlar-dto-generator--safe-db-sandbox-probing)
   - [6. `media` — Interoperable Multimodal Razvedka](#6-media--interoperable-multimodal-razvedka)
   - [7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv](#7-super-media--video-reducer-timeline-sync--smart-arxiv)
   - [8. `session` — AGY Sessiyalar va Transkriptlar Tahlili](#8-session--agy-sessiyalar-va-transkriptlar-tahlili)
   - [9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)](#9-face--ultra-yengil-biometrik-yuz-tanish-0-token-cpu-only)
   - [10. `bot` — JarvisOS Dinamik Modullari va Plaginlar Boshqaruvi](#10-bot--jarvisos-dinamik-modullari-va-plaginlar-boshqaruvi)
7. [🛡️ Xavfsizlik va Server Izolyatsiyasi Qoidalari](#️-xavfsizlik-va-server-izolyatsiyasi-qoidalari)
8. [👥 Muallif va Litsenziya](#-muallif-va-litsenziya)

---

## 💡 Loyiha Haqida va Falsafasi

AI coding assistantlar va avtonom agentlar (LLM) katta kod bazalarida ishlaganda ikkita ulkan muammoga duch keladi:
1. **Tokenlarning haddan tashqari ko'p sarflanishi:** Butun fayllar yoki repozitoriyalarni o'qib chiqish yuz minglab kontekst tokenlarini va byudjetni yoqib yuboradi.
2. **Sekin ishlash va xatoliklar:** Matnli qidiruvlar sekin bo'lib, noaniq taxminlarga (hallucinations) olib keladi.

`fayzillo-agy-tools` ushbu muammolarni **deterministik lokal tizim dvigatellari** orqali hal qiladi:
- AST parserlar, POSIX tizim utilitalari, Pillow, cryptography, ONNX Runtime va ffmpeg orqali **lokal bajarilishda 0 LLM token** sarflanadi;
- Operatsiyalar 20–60 millisekundda bajariladi (**~30x tezroq**);
- Barcha amallar real vaqtli **NDJSON Progress Eventlari** orqali Telegram bot va boshqaruv panellariga uzatiladi.

---

## ⚡ Asosiy Afzalliklar & Benchmark

| Xususiyat | ❌ An'anaviy LLM Agent (Toolsiz) | ⚡ `agy-tool` CLI Bilan | Farq / Yutuq |
|---|---|---|---|
| **Ijro Tezligi** | 25 – 60 soniya | **0.02 – 0.08 soniya** | **~30x–50x tezroq** ⚡ |
| **Token Sarfi** | 15,000 – 120,000 token | **0 Token** (Lokal Dvigatel) | **95%+ Tejamkorlik** 💰 |
| **Biometrik Yuz Tanish** | Cloud Vision API ($$$ va sekin) | UltraFace + MobileFaceNet ONNX | **0 Token / 16 FPS Offline** 🛡️ |
| **API Kontraktlar** | Qo'lda taxminiy DTO yozish | 3-tomonlama sinxron MD, TS va Postman | **100% Deterministik** |
| **Media Tahlili** | Rasmni ko'rish / audio tavsifi | EXIF, dHash, 4-rang palitra, STT, Video kadrlar | **To'liq Raqamli Digest** |
| **Xavfsizlik** | Real DB ga teginish xavfi | Safe DB Sandbox (`--dev-db`), Masking (`[REDACTED]`) | **Zero Secret Leak** 🛡️ |

---

## 💻 Tizim Talablari (System Requirements)

Har qanday Linux (Ubuntu, Debian, Fedora, Arch) yoki macOS muhitida quyidagi paketlar talab etiladi:

### 1. Operatsion Tizim Paketlari:
```bash
# Ubuntu / Debian:
sudo apt update && sudo apt install -y python3 python3-pip ffmpeg tesseract-ocr

# macOS (Homebrew orqali):
brew install python ffmpeg tesseract
```

### 2. Python Kutubxonalari (`requirements.txt`):
- `Pillow>=10.0.0` (Tasvirlarni qayta ishlash va perceptual dHash)
- `numpy>=1.24.0` (Vektor hisob-kitoblari va neyrotarmoq matritsalari)
- `onnxruntime>=1.16.0` (CPU-Only yengil MobileFaceNet yuz tanish modeli)
- `cryptography>=41.0.0` (Biometrik bazani AES-256 Fernet PBKDF2 shifrlash)
- `requests>=2.31.0` (API va xavfsiz sandbox probe integratsiyalari)

---

## 🚀 O'rnatish Qo'llanmasi (Installation Guide)

### A. Tezkor Avtomatik O'rnatish (Tavsiya etiladi):

```bash
# 1. Repozitoriyani klonlash:
git clone https://github.com/fummatov92/fayzillo-agy-tools.git ~/Desktop/fayzillo-agy-tools

# 2. O'rnatish skriptini ishga tushirish:
cd ~/Desktop/fayzillo-agy-tools
bash install.sh
```

`install.sh` skripti avtomatik ravishda:
1. Python va tizim vositalarini (`ffmpeg`, `tesseract`, `docker`) tekshiradi;
2. `requirements.txt` dagi barcha kutubxonalarni o'rnatadi;
3. `.env.example` dan `.env` konfiguratsiya faylini yaratadi;
4. `~/.local/bin/agy-tool` ga universal global ishga tushiruvchini ulaydi.

### B. Qo'lda (Manual) O'rnatish:

```bash
cd ~/Desktop/fayzillo-agy-tools

# Python kutubxonalarini o'rnatish:
pip install -r requirements.txt

# Konfiguratsiya faylini yaratish:
cp .env.example .env

# Binarni ishga tushirish huquqini berish:
chmod +x bin/agy-tool

# Global buyruq sifatida ulash:
mkdir -p ~/.local/bin
ln -sf $(pwd)/bin/agy-tool ~/.local/bin/agy-tool
```

### O'rnatishni tekshirish:
```bash
agy-tool --describe
```

---

## ⚙️ Konfiguratsiya Fayllari

Barcha sozlamalar loyiha ildizidagi `.env` va `agy_tools/config.py` orqali dinamik boshqariladi:

| Parametr | Standart Qiymat | Vazifasi |
|---|---|---|
| `AGY_ALLOWED_DIRS` | `~/Desktop,~/.local,~/.gemini,~/Downloads` | Path Jailing xavfsizlik chegarasi (faqat shu jildlarda ishlash) |
| `AGY_PORT_RANGE_START` | `15800` | Port skaneri boshlang'ich chegarasi |
| `AGY_PORT_RANGE_END` | `15900` | Port skaneri yakuniy chegarasi |
| `AGY_LOG_DIR` | `~/.local/state/agy-tool` | JSONL audit loglari saqlanish joyi |
| `AGY_TEMP_MEDIA_DIR` | `~/Desktop/temp/media_artifacts` | Media va video kadrlari saqlanadigan xavfsiz jild |
| `AGY_PROBE_SAFE_TABLES` | `branches,categories,roles...` | cURL probe uchun ruxsat etilgan xavfsiz jadvallar |
| `AGY_API_IGNORE_PATTERNS` | `*payme*,*click*,*billing*...` | Tahlildan chiqarib tashlanadigan nozik endpointlar |

---

## 🛠 Modullar va CLI Buyruqlar Qo'llanmasi

### 1. `sys` — Tizim Monitoringi, Portlar va Audit Jurnali
- `agy-tool sys status` — CPU, RAM, Disk va Load Avg ma'lumotlari.
- `agy-tool sys ports --start 15800 --end 15900` — Foydalanuvchi portlarini xavfsiz skanerlash.
- `agy-tool sys docker` — Rootless Docker konteynerlari holati.
- `agy-tool sys last-run` — Oxirgi bajarilgan buyruq va audit natijasi tafsilotlari.
- `agy-tool sys logs` — Tizimdagi barcha bajarilgan operatsiyalar audit jurnali.

### 2. `code` — AST Kod Tahlili, Endpointlar va Signaturalar
- `agy-tool code blueprint [path]` — Loyiha umumiy tuzilishi, ishlatilgan freymvork va asosiy fayllar xaritasi.
- `agy-tool code endpoints [path]` — NestJS, Express, FastAPI, Django marshrutlarini tezkor chiqarish.
- `agy-tool code symbols [path]` — Fayl yoki papkadagi barcha class va funksiyalar signaturalari.

### 3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi
- `agy-tool secure scan [path]` — Sirlar va maxfiy kalitlar sizib chiqishini aniqlash.
- `agy-tool secure redact [path]` — Maxfiy ma'lumotlarni xavfsiz niqoblash (`[REDACTED_...]`).

### 4. `debug` — Stack Trace Tahlili va Sintaksis Diagnostikasi
- `agy-tool debug trace "<stacktrace>"` — Xato stack trace matnini tahlil qilib, muammoli kod kontekstini chiqarish.
- `agy-tool debug check [path]` — TypeScript / Python loyihasidagi sintaksis xatoliklarini tekshirish.

### 5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing
- `agy-tool doc generate [path] --export=md,ts,postman` — 3 xil formatda API kontraktlarini generatsiya qilish.
- `agy-tool doc probe [path] --probe-db` — Xavfsiz GET-only aktiv probing orqali tirik endpointlar javoblarini olish.
- `agy-tool doc sync-db [path]` — Dev DB Sandboxga xavfsiz minimal dataset sync qilish.

### 6. `media` — Interoperable Multimodal Razvedka
- `agy-tool media video <file> [--interval=5s]` — Videoni tahlil qilish va kadrlarga ajratish.
- `agy-tool media audio <file> [--transcribe]` — Audio metadata, shovqinni kesish va Speech-to-Text.
- `agy-tool media image <file> [--ocr]` — Rasm tahlili (EXIF, dominant ranglar va OCR).
- `agy-tool media archive <file>` — ZIP/TAR arxivlarini ochmasdan xavfsiz tahlil qilish.

### 7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv
- `agy-tool super-media video <file>` — Videoni perceptual dHash orqali tozalash va Audio-Visual Timeline sinxronizatsiyasi.
- `agy-tool super-media archive <file>` — Arxivni 5 toifaga (Docs, Config, Code, Media, Build) ajratish va 0-token xulosa.
- `agy-tool super-media pipeline <file>` — To'liq multimodal avtomatlashtirilgan tahlil.

### 8. `session` — AGY Sessiyalar va Transkriptlar Tahlili
- `agy-tool session list` — Mavjud AGY sessiyalari ro'yxatini ko'rish.
- `agy-tool session inspect <id>` — Sessiyaning muloqotlari va tool statistikasini tahlil qilish.
- `agy-tool session export <id>` — Sessiya muloqotini toza Markdown formatida eksport qilish.

### 9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)
- `agy-tool face enroll <rasm> --name="Foydalanuvchi" --consent-confirmed` — Shaxs yuzini shifrlangan bazaga kiritish.
- `agy-tool face identify <rasm>` — Kadr ichidagi yuzlarni aniqlash va taqqoslash.
- `agy-tool face benchmark` — CPU tezligi va FPS samaradorligini o'lchash.

### 10. `bot` — JarvisOS Dinamik Modullari va Plaginlar Boshqaruvi
- `agy-tool bot list` — Botdagi barcha faol dinamik handlerlarni ko'rish.
- `agy-tool bot check` — Barcha handler fayllari sintaksisini tekshirish.

---

## 🛡️ Xavfsizlik va Server Izolyatsiyasi Qoidalari

1. **Path Jailing:** Barcha operatsiyalar `.env` da ko'rsatilgan xavfsiz jildlar doirasida cheklangan (`safe_jail_path`).
2. **Fail-Closed Determinizm:** Har qanday ruxsatsiz yoki xavfli buyruq darhol `exit 1` bilan to'xtatiladi.
3. **Zero Secret Leak:** Chiqariladigan barcha audit jurnallari va hisobotlarda API kalitlar avtomatik niqoblanadi.
4. **Port Boundaries:** Port operatsiyalari faqat belgilangan xavfsiz oraliqda (15800–15900) amalga oshiriladi.

---

## 👥 Muallif va Litsenziya

- **Muallif:** Fayzillo Ummatov ([@fummatov92](https://github.com/fummatov92))
- **Litsenziya:** MIT License — Ochiq manba va bepul foydalanish uchun.
