# 🛠️ fayzillo-agy-tools

> **JarvisOS & Antigravity (AGY) Autonomous CLI Toolsuite**  
> *Yuqori tezlikdagi AST tahlili, multimodal media razvedkasi, biometrik yuz tanish, xavfsiz sandbox sinovlari va 95%+ token tejamkorligi uchun avtonom vositalar to'plami.*

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/fummatov92/fayzillo-agy-tools)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20Ubuntu%20x86__64-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)]()
[![Modules](https://img.shields.io/badge/modules-9%20Active%20Toolsuites-purple.svg)]()

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
   - [7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv](#7-super-media--video-reducer-timeline-sync--smart-arxiv)
   - [8. `session` — AGY Sessiyalar va Transkriptlar Tahlili](#8-session--agy-sessiyalar-va-transkriptlar-tahlili)
   - [9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)](#9-face--ultra-yengil-biometrik-yuz-tanish-0-token-cpu-only)
5. [Konfiguratsiya Fayllari (.apiignore, .proberc)](#-konfiguratsiya-fayllari)
6. [Xavfsizlik va Server Izolyatsiyasi Qoidalari](#-xavfsizlik-va-server-izolyatsiyasi-qoidalari)
7. [Dasturlash va Testlash](#-dasturlash-va-testlash)

---

## 💡 Loyiha Haqida

`fayzillo-agy-tools` — AI agentlari (Antigravity CLI, JarvisOS Core AI Engine) va ishlab chiquvchilar uchun maxsus yaratilgan ultra-tezkor va xavfsiz tizim vositalari majmuasidir.

An'anaviy usulda LLM butun loyiha fayllarini bittalab o'qib chiqishiga yuz minglab tokenlar va daqiqalar sarflanadi. `agy-tool` esa deterministik lokal AST parserlar, POSIX tizim utilitalari, Pillow, mutagen, ONNX Runtime va ffmpeg orqali **0 LLM token** sarflagan holda bir necha millisoniyada aniq natija va ixcham JSON chiqarib beradi.

Barcha operatsiyalar real vaqtli **NDJSON Progress Eventlari** orqali Telegram bot va boshqaruv panellariga uzatiladi.

---

## ⚡ Asosiy Afzalliklar & Benchmark

| Xususiyat | ❌ An'anaviy LLM Agent (Asbobsiz) | ⚡ `agy-tool` CLI Bilan | Farq / Yutuq |
|---|---|---|---|
| **Ijro Tezligi** | 25 – 60 soniya | **0.05 – 1.0 soniya** | **~28x–50x tezroq** ⚡ |
| **Token Sarfi** | 15,000 – 120,000 token | **0 Token** (Lokal AST / Tizim) | **95%+ Tejamkorlik** 💰 |
| **Biometrik Yuz Tanish** | Vision API orqali qimmat va sekin | UltraFace + MobileFaceNet ONNX (CPU <60ms) | **0 Token / 16 FPS Offline** 🛡️ |
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
```bash
# Tizim umumiy holati (CPU, RAM, Disk, Load Avg)
agy-tool sys status

# Xavfsiz foydalanuvchi portlarini skanerlash (15800-15900)
agy-tool sys ports --start 15800 --end 15900

# Rootless Docker konteynerlari monitoringi
agy-tool sys docker

# Oxirgi bajarilgan buyruq audit hisoboti
agy-tool sys last-run --table

# Audit loglari tarixini ko'rish
agy-tool sys logs -n 20 --table
```

### 2. `code` — Kod Tahlili, Endpointlar va Signaturalar
```bash
# Loyiha tuzilishi va arxitektura xaritasi
agy-tool code blueprint /yo'l/loyiha

# API marshrutlari va kontrollerlar ro'yxati
agy-tool code endpoints /yo'l/backend

# Class va funksiyalar signaturalari
agy-tool code symbols /yo'l/fayl_yoki_papka
```

### 3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi
```bash
# Maxfiy sirlarni qidirish (dry-run skaner)
agy-tool secure scan /yo'l/loyiha

# Sirlarni avtomatik tozalash va niqoblash
agy-tool secure redact /yo'l/fayl.env
```

### 4. `debug` — Xatoliklar Tahlili va Sintaksis Diagnostikasi
```bash
# Stack trace tahlili va muammoli kod konteksti
agy-tool debug trace "Traceback (most recent call last)..."

# Loyihadagi sintaksis va tiplar diagnostikasi
agy-tool debug check /yo'l/loyiha
```

### 5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing
```bash
# Markdown, TypeScript DTO va Postman eksport qilish
agy-tool doc /yo'l/backend --export=md,ts,postman

# Tirik GET endpointlarni xavfsiz sandboxda prob qilish
agy-tool doc /yo'l/backend --probe-db --dev-db=15842
```

### 6. `media` — Interoperable Multimodal Razvedka
```bash
# Video tahlili va kadrlarga ajratish
agy-tool media video sample.mp4 --interval=5s

# Audio tahlili, segmentlash va Speech-to-Text
agy-tool media audio speech.m4a --silence-removal --language=uz-UZ

# Rasm tahlili (EXIF, dHash, ranglar, ASCII preview, OCR)
agy-tool media image photo.jpg --palette-size=4 --ascii-preview

# ZIP/TAR arxivlarini ochmasdan ko'rish
agy-tool media archive project.zip --view-file=src/index.ts

# Multimodal pipeline
agy-tool media pipeline mediafile.mp4
```

### 7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv
```bash
# Videodagi o'xshash kadrlarni dHash (<12%) orqali tozalash va audio bilan Timeline Sync
agy-tool super-media video recording.mp4 --format=table

# Arxivni 5 toifaga ajratib, 0-token blueprint olish
agy-tool super-media archive archive.zip --format=table

# Avtomatik multimodal pipeline
agy-tool super-media pipeline project.zip
```

### 8. `session` — AGY Sessiyalar va Transkriptlar Tahlili
```bash
# Sessiyalar ro'yxati
agy-tool session list -n 10 --table

# Sessiyani chuqur tahlil qilish
agy-tool session inspect <session_id> --table

# Transkript ichidan kalit so'z qidirish
agy-tool session query <session_id> "error"
```

### 9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)

UltraFace (1.2MB) + MobileFaceNet ONNX (13MB) orqali bitta CPU yadrosida **~58 ms**da 512 o'lchamli biometrik vektor chiqarish va shaxsni tanish.

```bash
# 1. Shaxs yuzini biometrik bazaga ro'yxatga olish (Vector Enrollment)
agy-tool face enroll "Fayzillo Ummatov" /yo'l/fayzillo.jpg

# 2. Rasm ichidagi yuzlarni aniqlash va bazadagi shaxslar bilan taqqoslash
agy-tool face identify /yo'l/noma'lum_rasm.jpg

# 3. Kadr ko'rsatilgan shaxsga tegishli ekanligini verifikatsiya qilish
agy-tool face verify /yo'l/kadr.jpg "Fayzillo Ummatov"

# 4. Telegram video xabarlari (doiracha / MP4) ichidan yuzlarni skanerlash
agy-tool face video /yo'l/video_note.mp4

# 5. Ro'yxatdan o'tgan shaxslar bazasini ko'rish
agy-tool face list

# 6. CPU tezligi, RAM sarfi va FPS samaradorligini o'lchash (Benchmark)
agy-tool face benchmark /yo'l/foto.jpg
```

---

## ⚙️ Konfiguratsiya Fayllari

Loyihangiz ildiz jildida quyidagi ixtiyoriy konfiguratsiya fayllarini yaratishingiz mumkin:

### 1. `.apiignore` (Maxfiy endpointlarni filtrlash)
```text
/api/v1/billing/*
/api/v1/payme/*
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

1. **Jail Izolyatsiyasi (`safe_jail_path`)**: Barcha fayl tahlillari FAQAT `/home/fayzillo/Desktop/`, `~/.local/`, `~/.gemini/antigravity-cli` va `~/Downloads/brains` doirasida bajariladi.
2. **Xavfsiz Portlar oralig'i (`validate_safe_port`)**: Sandbox va dev serverlar FAQAT **15800 dan 15900 gacha** bo'lgan portlarda ochiladi.
3. **Avtomatik Sirlarni Niqoblash**: Barcha audit loglari va JSON javoblari avtomatik ravishda `[REDACTED_...]` shablonlari bilan himoyalanadi.
4. **Advisory File Lock (`fcntl.flock`)**: Ko'p agentli parallel muhitda audit loglari yozilishi poyga holatlarisiz kafolatlanadi.

---

## 🧪 Dasturlash va Testlash

Barcha modullar to'liq avtomatlashtirilgan regressiya testlari bilan qoplangan:

```bash
# Barcha testlarni bir vaqtda ishga tushirish:
python3 -m unittest discover -s tests
```

---

## 👥 Muallif va Bog'lanish

- **Muallif**: Fayzillo Ummatov & JarvisOS Core AI Engine
- **GitHub**: [@fummatov92](https://github.com/fummatov92)
- **Repozitoriy**: [https://github.com/fummatov92/fayzillo-agy-tools](https://github.com/fummatov92/fayzillo-agy-tools)

*Litsenziya: MIT — ochiq manbali va tijoriy maqsadlarda foydalanish mumkin.*
