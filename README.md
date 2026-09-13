# 🛠️ fayzillo-agy-tools

> **JarvisOS & Antigravity (AGY) Autonomous CLI Toolsuite**  
> *AI agentlari (Antigravity CLI, JarvisOS Core AI Engine) va dasturchilar uchun ultra-tezkor AST tahlili, multimodal media razvedkasi, biometrik yuz tanish, xavfsiz sandbox sinovlari va 95%+ token tejamkorligini ta'minlovchi avtonom tizim vositalari majmuasi.*

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/fummatov92/fayzillo-agy-tools)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20Ubuntu%20%7C%20macOS-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)]()
[![Modules](https://img.shields.io/badge/modules-9%20Active%20Toolsuites-purple.svg)]()

---

## 📑 Mundarija

1. [💡 Loyiha Haqida va Falsafasi](#-loyiha-haqida-va-falsafasi)
2. [⚡ Asosiy Afzalliklar & Benchmark](#-asosiy-afzalliklar--benchmark)
3. [💻 Tizim Talablari (System Requirements)](#-tizim-talablari-system-requirements)
4. [🚀 O'rnatish Qo'llanmasi (Installation Guide)](#-ornatish-qollanmasi-installation-guide)
   - [A. Tezkor Avtomatik O'rnatish](#a-tezkor-avtomatik-ornatish-tavsiya-etiladi)
   - [B. Qo'lda (Manual) O'rnatish](#b-qolda-manual-ornatish)
5. [🛠 Modullar va CLI Buyruqlar Qo'llanmasi](#-modullar-va-cli-buyruqlar-qollanmasi)
   - [1. `sys` — Tizim Monitoringi, Portlar va Audit Jurnali](#1-sys--tizim-monitoringi-portlar-va-audit-jurnali)
   - [2. `code` — AST Kod Tahlili, Endpointlar va Signaturalar](#2-code--ast-kod-tahlili-endpointlar-va-signaturalar)
   - [3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi](#3-secure--xavfsizlik-va-maxfiy-kalitlar-sanitizatsiyasi)
   - [4. `debug` — Stack Trace Tahlili va Sintaksis Diagnostikasi](#4-debug--stack-trace-tahlili-va-sintaksis-diagnostikasi)
   - [5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing](#5-doc--api-kontraktlar-dto-generator--safe-db-sandbox-probing)
   - [6. `media` — Interoperable Multimodal Razvedka](#6-media--interoperable-multimodal-razvedka)
   - [7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv](#7-super-media--video-reducer-timeline-sync--smart-arxiv)
   - [8. `session` — AGY Sessiyalar va Transkriptlar Tahlili](#8-session--agy-sessiyalar-va-transkriptlar-tahlili)
   - [9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)](#9-face--ultra-yengil-biometrik-yuz-tanish-0-token-cpu-only)
6. [⚙️ Konfiguratsiya Fayllari (.apiignore, .proberc)](#️-konfiguratsiya-fayllari)
7. [🛡️ Xavfsizlik va Server Izolyatsiyasi Qoidalari](#️-xavfsizlik-va-server-izolyatsiyasi-qoidalari)
8. [🧪 Dasturlash va Testlash](#-dasturlash-va-testlash)
9. [👥 Muallif va Litsenziya](#-muallif-va-litsenziya)

---

## 💡 Loyiha Haqida va Falsafasi

AI coding assistantlar va avtonom agentlar (LLM) katta kod bazalarida ishlaganda ikkita ulkan muammoga duch keladi:
1. **Tokenlarning haddan tashqari ko'p sarflanishi:** Butun fayllar yoki repozitoriyalarni o'qib chiqish yuz minglab kontekst tokenlarini va byudjetni yoqib yuboradi.
2. **Sekin ishlash va xatoliklar:** Matnli qidiruvlar sekin bo'lib, noaniq taxminlarga (hallucinations) olib keladi.

`fayzillo-agy-tools` ushbu muammolarni **deterministik lokal tizim dvigatellari** orqali hal qiladi:
- AST parserlar, POSIX tizim utilitalari, Pillow, mutagen, ONNX Runtime va ffmpeg orqali **0 LLM token** sarflanadi;
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

- **Operatsion Tizim:** Linux (Ubuntu 20.04+, Debian, Fedora, Arch) yoki macOS (x86_64 / ARM64 / Apple Silicon).
- **Python:** Versiya `3.10` yoki undan yuqori (`python3 --version`).
- **Tizim Paketlari:**
  - `ffmpeg` — Video va audio tahlili uchun (`sudo apt install ffmpeg`).
  - `sqlite3` — Sessiyalar va audit loglarini boshqarish uchun.
- **Python Kutubxonalari:**
  - `onnxruntime` (yuz tanish va ONNX neyrotarmoq modellari uchun)
  - `pillow` (tasvirlar tahlili va perceptual dHash)
  - `numpy` (vektor hisob-kitoblari va cosine similarity)
  - `mutagen` (audio metadata tahlili)

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
1. Python va `ffmpeg` mavjudligini tekshiradi;
2. `requirements.txt` dagi barcha kutubxonalarni o'rnatadi;
3. `~/.local/bin/agy-tool` ga universal global ishga tushiruvchini ulaydi.

### B. Qo'lda (Manual) O'rnatish:

```bash
cd ~/Desktop/fayzillo-agy-tools

# Python kutubxonalarini o'rnatish:
pip install -r requirements.txt

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

## 🛠 Modullar va CLI Buyruqlar Qo'llanmasi

---

### 1. `sys` — Tizim Monitoringi, Portlar va Audit Jurnali

Server resurslari, foydalanuvchiga ajratilgan portlar (15800-15900), Rootless Docker va bajarilgan buyruqlar tarixini kuzatish.

```bash
# Tizim umumiy holati (CPU, RAM, Disk, Load Avg)
agy-tool sys status

# Xavfsiz foydalanuvchi portlarini skanerlash (15800-15900)
agy-tool sys ports --start 15800 --end 15900

# Rootless Docker konteynerlari monitoringi
agy-tool sys docker

# Disk hajmi taqsimoti va eng katta kataloglar tahlili
agy-tool sys storage /home/fayzillo/Desktop --top=10

# Oxirgi bajarilgan buyruq audit hisoboti (inson o'qiydigan jadval)
agy-tool sys last-run --table

# Audit loglari tarixini ko'rish (oxirgi 20 ta yozuv yoki faqat xatolar)
agy-tool sys logs -n 20 --table
agy-tool sys logs -e --table
agy-tool sys logs -s <session_id>
```

---

### 2. `code` — AST Kod Tahlili, Endpointlar va Signaturalar

Loyiha arxitekturasi, modullari, API endpointlari va kontrollerlarini AST (Abstract Syntax Tree) yordamida **0 LLM token** sarflab bir zumda chiqarish.

```bash
# Loyiha umumiy tuzilishi, ishlatilgan freymvork va asosiy fayllar xaritasi
agy-tool code blueprint /yo'l/loyiha

# NestJS, Express, FastAPI, Django loyihalaridagi barcha marshrutlar (routes/endpoints)
agy-tool code endpoints /yo'l/backend

# Fayl yoki papkadagi barcha class, interfeys va funksiyalar signaturalari
agy-tool code symbols /yo'l/fayl_yoki_papka
```

---

### 3. `secure` — Xavfsizlik va Maxfiy Kalitlar Sanitizatsiyasi

Loglar, konfiguratsiyalar va fayllardagi maxfiy ma'lumotlarni (parollar, tokenlar, API kalitlar) tekshirish va xavfsiz tozalash.

```bash
# Maxfiy sirlarni qidirish (dry-run skaner)
agy-tool secure scan /yo'l/loyiha

# Ko'rsatilgan fayl ichidagi sirlarni [REDACTED_...] bilan xavfsiz almashtirish
agy-tool secure redact /yo'l/fayl.env
```

---

### 4. `debug` — Stack Trace Tahlili va Sintaksis Diagnostikasi

Xatoliklar loglari (stack trace)ni tahlil qilib, muammoli fayl, qator va uning atrofidagi kod kontekstini ajratib berish.

```bash
# Xato stack trace matnini tahlil qilish va muammoli joyni topish
agy-tool debug trace "Traceback (most recent call last): ..."

# Loyihadagi sintaksis va tiplar xatoliklarini (TypeScript / Python) tezkor tekshirish
agy-tool debug check /yo'l/loyiha
```

---

### 5. `doc` — API Kontraktlar, DTO Generator & Safe DB Sandbox Probing

Multi-Framework Zero-Token API Kontrakt & DTO Generator (NestJS, Express, Go, Laravel) va xavfsiz Sandbox Probing.

```bash
# Loyiha kontrollerlari va DTOlaridan Markdown, TypeScript va Postman kontraktlarini generatsiya qilish
agy-tool doc /yo'l/backend --export=md,ts,postman

# Tirik GET endpointlarni xavfsiz sandboxda prob qilish (Dev DB Sandbox orqali)
agy-tool doc /yo'l/backend --probe-db --dev-db=15842

# Asl bazadan xavfsiz minimal ma'lumotlar to'plamini (snapshot) Sandboxga nusxalash
agy-tool doc sync-db --source=postgresql://... --target=postgresql://...
```

---

### 6. `media` — Interoperable Multimodal Razvedka

Video, audio, tasvir, arxiv va matnli hujjatlarni deterministik qayta ishlash vositalari to'plami.

```bash
# Video tahlili, metadata va kadrlarga ajratish (har 5 soniyada)
agy-tool media video sample.mp4 --interval=5s

# Audio tahlili, 30 soniyalik segmentlarga bo'lish va Speech-to-Text
agy-tool media audio speech.m4a --chunk-size=30 --silence-removal --language=uz-UZ

# Rasm tahlili: EXIF, dHash/aHash, 4-rangli dominant palitra, ASCII preview va OCR
agy-tool media image photo.jpg --palette-size=4 --ascii-preview

# ZIP / TAR arxivlarini ochmasdan daraxt (Tree) va ichki faylni xotirada ochib o'qish
agy-tool media archive project.zip --view-file=src/index.ts

# Markdown va hujjatlar strukturasi, 0-token statistik tahlili
agy-tool media text README.md --keywords=10

# Yagona multimodal pipeline (avtomatik fayl turini aniqlaydi)
agy-tool media pipeline presentation.mp4
```

---

### 7. `super-media` — Video Reducer, Timeline Sync & Smart Arxiv

Katta hajmdagi video va arxivlarni deyarli 0-token formatidagi ixcham Timeline Digestga aylantirish.

```bash
# Videodagi deyarli bir xil kadrlarni dHash (<12%) orqali tozalash va audio bilan Timeline jadvaliga sinxronlash
agy-tool super-media video recording.mp4 --format=table

# ZIP/TAR arxivini ochmasdan 5 toifaga (Docs, Config, Code, Media, Build/Trash) ajratish va 0-token blueprint olish
agy-tool super-media archive archive.zip --format=table

# Avtomatik super multimodal pipeline
agy-tool super-media pipeline project.zip --format=json
```

---

### 8. `session` — AGY Sessiyalar va Transkriptlar Tahlili

Antigravity (AGY) sessiyalari va transkriptlarini yuqori tezlikda tahlil qilish, qidirish va eksport qilish.

```bash
# Barcha mavjud AGY sessiyalari ro'yxatini ko'rish
agy-tool session list -n 15 --table

# Ko'rsatilgan sessiyaning barcha muloqotlari, so'rovlari va tool qo'llanish statistikasini tahlil qilish
agy-tool session inspect <session_id> --table

# Sessiya transkripti ichidan kalit so'z bo'yicha tezkor qidirish
agy-tool session query <session_id> "error"

# Sessiya muloqotini toza va xavfsiz (sirlar maskalangan) Markdown formatida eksport qilish
agy-tool session export <session_id>
```

---

### 9. `face` — Ultra-Yengil Biometrik Yuz Tanish (0-Token, CPU-Only)

**UltraFace (1.2MB)** va **MobileFaceNet ONNX (13MB)** neyrotarmoqlari asosidagi, oddiy CPU'da **~58 ms**da 512 o'lchamli biometrik vektor chiqaruvchi, **0 token sarflaydigan** va 100% offline ishlaydigan biometrik yuz tanish moduli.

```bash
# 1. Shaxs yuzini biometrik bazaga ro'yxatga olish (Vector Enrollment)
agy-tool face enroll "Fayzillo Ummatov" /yo'l/fayzillo.jpg

# 2. 180° video orqali ko'p burchakli (Multi-Angle) 3D biometrik profil yaratish
agy-tool face enroll-video "Fayzillo Ummatov" /yo'l/head_rotation.mp4

# 3. Rasm ichidagi barcha yuzlarni aniqlash va bazadagi shaxslar bilan taqqoslash
agy-tool face identify /yo'l/noma'lum_rasm.jpg

# 4. Kadr ko'rsatilgan shaxsga tegishli ekanligini verifikatsiya qilish
agy-tool face verify /yo'l/kadr.jpg "Fayzillo Ummatov"

# 5. Telegram video xabarlari (doiracha / MP4) ichidan yuzlarni skanerlash
agy-tool face video /yo'l/video_note.mp4

# 6. Ro'yxatdan o'tgan shaxslar bazasini ko'rish
agy-tool face list

# 7. CPU tezligi, RAM sarfi va FPS samaradorligini o'lchash (Benchmark)
agy-tool face benchmark /yo'l/foto.jpg
```

---

## ⚙️ Konfiguratsiya Fayllari

Loyihangiz ildiz jildida quyidagi ixtiyoriy konfiguratsiya fayllarini yaratishingiz mumkin:

### 1. `.apiignore` (Maxfiy endpointlarni filtrlash)
```text
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

1. **Jail Izolyatsiyasi (`safe_jail_path`)**: Barcha fayl tahlillari FAQAT `/home/fayzillo/Desktop/`, `~/.local/`, `~/.gemini/antigravity-cli` va `~/Downloads/brains` doirasida bajariladi. Tizim papkalariga (`/root/`, `/srv/`, `/opt/*`, `/etc/`) teginish qat'iy bloklangan.
2. **Xavfsiz Portlar oralig'i (`validate_safe_port`)**: Sandbox va dev serverlar FAQAT **15800 dan 15900 gacha** bo'lgan portlarda ochiladi.
3. **Avtomatik Sirlarni Niqoblash**: Barcha audit loglari va JSON javoblari avtomatik ravishda `[REDACTED_PASSWORD]`, `[REDACTED_TOKEN]` shablonlari bilan himoyalanadi.
4. **Advisory File Lock (`fcntl.flock`)**: Ko'p agentli parallel muhitda audit loglari yozilishi poyga holatlarisiz (race-condition free) kafolatlanadi.

---

## 🧪 Dasturlash va Testlash

Barcha 9 ta modul to'liq avtomatlashtirilgan regressiya unit testlari bilan qoplangan:

```bash
# Barcha testlarni bir vaqtda ishga tushirish:
python3 -m unittest discover -s tests
```

---

## 👥 Muallif va Litsenziya

- **Muallif**: Fayzillo Ummatov & JarvisOS Core AI Engine
- **GitHub**: [@fummatov92](https://github.com/fummatov92)
- **Repozitoriy**: [https://github.com/fummatov92/fayzillo-agy-tools](https://github.com/fummatov92/fayzillo-agy-tools)

*Litsenziya: MIT License — ochiq manbali va tijoriy maqsadlarda erkin foydalanish mumkin.*
