# 🛠️ fayzillo-agy-tools

> **JarvisOS & Antigravity (AGY) Autonomous CLI Toolsuite**  
> *Yuqori tezlikdagi AST tahlili, multimodal media razvedkasi, xavfsiz sandbox sinovlari va 95%+ token tejamkorligi uchun avtonom vositalar to'plami.*

[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)](https://github.com/fummatov92/fayzillo-agy-tools)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20Ubuntu%20x86__64-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)]()
[![Modules](https://img.shields.io/badge/modules-6%20Active%20Toolsuites-purple.svg)]()

---

## 📑 Mundarija

1. [Loyiha Haqida](#-loyiha-haqida)
2. [Asosiy Afzalliklar & Benchmark](#-asosiy-afzalliklar--benchmark)
3. [Tezkor O'rnatish](#-tezkor-ornatish)
4. [Modullar va CLI Qo'llanmasi](#-modullar-va-cli-qollanmasi)
   - [1. `sys` — Tizim Monitoringi va Audit Jurnali](#1-sys--tizim-monitoringi-va-audit-jurnali)
   - [2. `code` — Kod Tahlili, Endpointlar va Signaturalar](#2-code--kod-tahlili-endpointlar-va-signaturalar)
   - [3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi](#3-secure--xavfsizlik-va-maxfiy-kalitlar-sanitizatsiyasi)
   - [4. `debug` — Xatoliklar Tahlili va Sintaksis Diagnostikasi](#4-debug--xatoliklar-tahlili-va-sintaksis-diagnostikasi)
   - [5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing](#5-doc--api-kontraktlar-dto-generator--safe-db-sandbox-probing)
   - [6. `media` — Interoperable Multimodal Razvedka](#6-media--interoperable-multimodal-razvedka)
5. [Konfiguratsiya Fayllari (.apiignore, .proberc)](#-konfiguratsiya-fayllari)
6. [Xavfsizlik va Server Izolyatsiyasi Qoidalari](#-xavfsizlik-va-server-izolyatsiyasi-qoidalari)
7. [Dasturlash va Testlash](#-dasturlash-va-testlash)

---

## 💡 Loyiha Haqida

`fayzillo-agy-tools` — AI agentlari (Antigravity CLI, JarvisOS Core AI Engine) va ishlab chiquvchilar uchun maxsus yaratilgan ultra-tezkor va xavfsiz tizim vositalari majmuasidir.

An'anaviy usulda LLM butun loyiha fayllarini bittalab o'qib chiqishiga yuz minglab tokenlar va daqiqalar sarflanadi. `agy-tool` esa deterministik lokal AST parserlar, POSIX tizim utilitalari, Pillow, mutagen va ffmpeg orqali **0 LLM token** sarflagan holda bir necha millisoniyada aniq natija va ixcham JSON chiqarib beradi.

Barcha operatsiyalar real vaqtli **NDJSON Progress Eventlari** orqali Telegram bot va boshqaruv panellariga uzatiladi.

---

## ⚡ Asosiy Afzalliklar & Benchmark

| Xususiyat | ❌ An'anaviy LLM Agent (Asbobsiz) | ⚡ `agy-tool` CLI Bilan | Farq / Yutuq |
|---|---|---|---|
| **Ijro Tezligi** | 25 – 60 soniya | **0.05 – 1.0 soniya** | **~28x–50x tezroq** ⚡ |
| **Token Sarfi** | 15,000 – 120,000 token | **0 Token** (Lokal AST / Tizim) | **95%+ Tejamkorlik** 💰 |
| **API Kontraktlar** | Qo'lda taxminiy DTO yozish | 3-tomonlama sinxron MD, TS va Postman | **100% Deterministik** |
| **Media Tahlili** | Rasmni ko'rish / audio tavsifi | EXIF, dHash, 4-rang palitra, STT, Video kadrlar | **To'liq Raqamli Digest** |
| **Xavfsizlik** | Real DB ga teginish xavfi | Safe DB Sandbox (`--dev-db`), Masking (`[REDACTED]`) | **Zero Secret Leak** 🛡️ |

---

## 🚀 Tezkor O'rnatish

### 1. Repozitoriyani klonlash:
```bash
# SSH orqali:
git clone git@github.com:fummatov92/fayzillo-agy-tools.git ~/Desktop/fayzillo-agy-tools

# Yoki HTTPS orqali:
git clone https://github.com/fummatov92/fayzillo-agy-tools.git ~/Desktop/fayzillo-agy-tools
```

### 2. O'rnatish va deploy:
```bash
cd ~/Desktop/fayzillo-agy-tools
bash install.sh
```

O'rnatilgach, `agy-tool` buyrug'i butun server muhitida (`~/.local/bin/agy-tool`) global ishlaydi:
```bash
agy-tool --describe
```

---

## 🛠 Modullar va CLI Qo'llanmasi

### 1. `sys` — Tizim Monitoringi va Audit Jurnali

Server resurslari, foydalanuvchiga ajratilgan portlar, Rootless Docker va bajarilgan buyruqlar tarixini kuzatish.

```bash
# Tizim umumiy holati (CPU, RAM, Disk, Load Avg)
agy-tool sys status

# Xavfsiz foydalanuvchi portlarini skanerlash (15800-15900)
agy-tool sys ports --start 15800 --end 15900

# Rootless Docker konteynerlari monitoringi
agy-tool sys docker

# Oxirgi bajarilgan buyruq audit hisoboti (inson o'qiydigan jadval)
agy-tool sys last-run --table

# Audit loglari tarixini ko'rish (oxirgi 20 ta yozuv yoki faqat xatolar)
agy-tool sys logs -n 20 --table
agy-tool sys logs -e --table
agy-tool sys logs -s <session_id>
```

---

### 2. `code` — Kod Tahlili, Endpointlar va Signaturalar

Loyiha arxitekturasi, marshrutlar xaritasi va dasturlash tillari bo'yicha class/funksiyalar signaturalarini ajratish.

```bash
# Loyiha umumiy arxitekturasi va konfiguratsiyalar xaritasi
agy-tool code blueprint /path/to/project

# NestJS / Express / FastAPI loyihalaridagi barcha API marshrutlari
agy-tool code endpoints /path/to/backend

# TypeScript, JavaScript, Python, Go, PHP fayl yoki papkasidagi barcha signaturalar
agy-tool code symbols /path/to/project/src/modules/company
agy-tool code symbols /path/to/file.py
```

---

### 3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi

Loglar, fayllar va hisobotlardagi sirlar (parollar, tokenlar, API kalitlar, DB URI) ni aniqlash va niqoblash.

```bash
# Fayl yoki papkadagi maxfiy ma'lumotlarni qidirish (tekshirish)
agy-tool secure scan /path/to/project

# Sirlarni [REDACTED_PASSWORD], [REDACTED_TOKEN] bilan almashtirish (dry-run)
agy-tool secure redact /path/to/log.txt --dry-run

# Haqiqiy faylni xavfsiz tozalash
agy-tool secure redact /path/to/log.txt
```

---

### 4. `debug` — Xatoliklar Tahlili va Sintaksis Diagnostikasi

Server stack trace loglarini chuqur tahlil qilish va TypeScript/Python loyihalarini tezkor diagnostika qilish.

```bash
# Xato stack trace tahlili (aybdor fayl, satr va 10 qatorli kod konteksti)
agy-tool debug trace "TypeError: Cannot read properties of undefined (reading 'id') at UserService.find (/path/user.service.ts:42:15)"

# Loyihaning TypeScript/Python sintaksisi va tiplarini tekshirish (tsc / py_compile)
agy-tool debug check /path/to/project
```

---

### 5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing

NestJS, Express, Go va Laravel loyihalaridan **0 LLM token** bilan 3 xil formatda API hujjatlarini generatsiya qilish hamda xavfsiz Dev DB Sandbox orqali tirik ma'lumotlar bilan boyitish.

```bash
# 1. Statik AST tahlil orqali Markdown, TS Types va Postman generatsiyasi
agy-tool doc /path/to/nestjs_project --export=md,ts,postman --output-dir=./docs

# 2. Xesh keshini chetlab o'tib, majburiy qayta yaratish
agy-tool doc /path/to/project --force

# 3. Tirik GET endpointlarni xavfsiz aktiv probing qilish
agy-tool doc /path/to/project --probe --probe-url=http://127.0.0.1:15801

# 4. Dev DB Sandbox va avtomatik xavfsiz data-sync bilan probing
agy-tool doc /path/to/project --probe-db --dev-db=sqlite:///tmp/dev_sandbox.db --safe-tables=companies,branches,users

# 5. Rootless Docker sandbox konteyneri orqali probing
agy-tool doc /path/to/project --probe-db --dev-docker=zdes_backend_app
```

#### Yaratiladigan Fayllar Strukturasi:
- `docs/<module>/<controller>.api.md` — To'liq parametrlar, DTO va Mock javoblar.
- `types/<module>/<controller>.d.ts` — TypeScript tip kontraktlari.
- `postman/api_collection.json` — Postman v2.1 import to'plami.
- `docs/README.md` — Modullar navigatsiya xaritasi.

---

### 6. `media` — Interoperable Multimodal Razvedka

Video, audio, tasvir, arxivlar va hujjatlarni chuqur tahlil qilish uchun yagona interfeys.

#### A. Video Tahlili (`media video`):
```bash
# Video metadata, kadrlarga ajratish va audioni WAV qilib olish
agy-tool media video sample.mp4 --interval=5s --extract-audio --output-dir=./frames

# Faqat asosiy I-Framelarni (keyframes) ajratish
agy-tool media video sample.mp4 --keyframes

# Sahna o'zgarishi (scene detection) bo'yicha ajratish
agy-tool media video sample.mp4 --scene-change=0.3
```

#### B. Audio Tahlili & Speech-to-Text (`media audio`):
```bash
# Audio metadata va 30 soniyalik segmentlarga bo'lish
agy-tool media audio speech.m4a --chunk-size=30 --output-dir=./audio_chunks

# Jimlikni kesish va o'zbekcha Speech-to-Text transkripsiya
agy-tool media audio speech.m4a --silence-removal --language=uz-UZ
```

#### C. Tasvir Tahlili & Visual Intelligence (`media image`):
```bash
# EXIF, 9:16 nisbat, 4-rangli dominant palitra va dHash/aHash xesh
agy-tool media image photo.jpg --palette-size=4

# Terminal uchun ASCII vizual griddi va OCR matn qidiruvi
agy-tool media image photo.jpg --ascii-preview --ocr
```

#### D. Arxivlarni Xavfsiz Ko'rish (`media archive`):
```bash
# ZIP / TAR arxivlarini ochmasdan daraxt (Tree) va Zip-Bomb xavfsizlik tekshiruvi
agy-tool media archive project.zip

# Arxiv ichidagi faylni xotirada ochib o'qish (xavfsiz preview)
agy-tool media archive project.zip --view-file=src/index.ts
```

#### E. Matn va Markdown Struktura Tahlili (`media text`):
```bash
# 0-Token statistik tahlil, sarlavhalar va kod bloklari xaritasi
agy-tool media text README.md --keywords=10
```

#### F. Yagona Multimodal Pipeline (`media pipeline`):
```bash
# Bitta buyruq bilan video/rasm/audiodan yaxlit AI Digest tayyorlash:
agy-tool media pipeline presentation.mp4
```

---

## ⚙️ Konfiguratsiya Fayllari

Loyihangiz ildiz jildida quyidagi ixtiyoriy konfiguratsiya fayllarini yaratishingiz mumkin:

### 1. `.apiignore` (Maxfiy endpointlarni filtrlash)
```text
# To'lov va maxfiy tizim marshrutlarini API hujjatlaridan chiqarib tashlash
/api/v1/billing/*
/api/v1/payme/*
/api/v1/click/*
/api/v1/internal/*
POST /api/v1/auth/reset-root-password
```

### 2. `.proberc` yoki `.env.probe` (Dev DB Sandbox sozlamalari)
```ini
DEV_DB_URL=postgresql://sandbox_user:sandbox_pass@127.0.0.1:15842/dev_sandbox
DEV_PROBE_URL=http://127.0.0.1:15801
SAFE_TABLES=users,companies,branches,departments,holidays
EXCLUDE_FIELDS=password,token,secret,credit_card,cvv
```

---

## 🛡️ Xavfsizlik va Server Izolyatsiyasi Qoidalari

1. **Jail Izolyatsiyasi (`safe_jail_path`)**: Barcha fayl tahlillari va yaratishlar FAQAT `/home/fayzillo/Desktop/` va `~/.local/` doirasida bajariladi. Tizim papkalari (`/root/`, `/srv/`, `/opt/*`, `/etc/`) qat'iy bloklangan.
2. **Xavfsiz Portlar oralig'i (`validate_safe_port`)**: Sandbox va dev serverlar FAQAT **15800 dan 15900 gacha** bo'lgan portlarda ochiladi (`4000`, `5432`, `6379` kabi tizim portlari taqiqlangan).
3. **Avtomatik Sirlarni Niqoblash**: Barcha audit loglari va prob qilingan JSON javoblari avtomatik ravishda `[REDACTED_PASSWORD]`, `[REDACTED_TOKEN]` shablonlari bilan himoyalanadi.
4. **Advisory File Lock (`fcntl.flock`)**: Ko'p agentli parallel muhitda audit loglari yozilishi poyga holatlarisiz (race-condition free) va 0o600 xavfsiz huquqlar bilan kafolatlanadi.

---

## 🧪 Dasturlash va Testlash

Barcha modullar to'liq avtomatlashtirilgan regressiya testlari bilan qoplangan:

```bash
# Barcha testlarni ishga tushirish:
python3 tests/test_audit_logger.py
python3 tests/test_doc_tool.py
python3 tests/test_media_tool.py

# Bir qatorda to'liq verifikatsiya:
python3 tests/test_audit_logger.py && python3 tests/test_doc_tool.py && python3 tests/test_media_tool.py
```

---

## 👥 Muallif va Bog'lanish

- **Muallif**: Fayzillo Ummatov & JarvisOS Core AI Engine
- **GitHub**: [@fummatov92](https://github.com/fummatov92)
- **Repozitoriy**: [https://github.com/fummatov92/fayzillo-agy-tools](https://github.com/fummatov92/fayzillo-agy-tools)

*Litsenziya: MIT — ochiq manbali va tijoriy maqsadlarda foydalanish mumkin.*
