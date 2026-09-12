# fayzillo-agy-tools

JarvisOS & AGY Dynamic Autonomous Toolsuite for High-Speed & Token-Efficient Operations.

Ushbu vositalar to'plami AI agentlarining (AGY) token sarfini 95%+ tejash, real vaqtli progress hodisalarini Telegram'ga uzatish (NDJSON) va xavfsiz tizim monitoringi uchun mo'ljallangan.

## 🚀 Modullar

1. **`sys`**:
   - `agy-tool sys status` — Disk, RAM, Uptime va Load Avg ma'lumotlari.
   - `agy-tool sys ports --start 15800 --end 15900` — Foydalanuvchi portlarini xavfsiz skanerlash.
   - `agy-tool sys docker` — Rootless Docker konteynerlari monitoringi.

2. **`code`**:
   - `agy-tool code blueprint [path]` — Loyiha arxitekturasi va fayllar xaritasi.
   - `agy-tool code endpoints [path]` — NestJS, Express, FastAPI marshrutlarini tezkor AST orqali chiqarish.

3. **`secure`**:
   - `agy-tool secure scan [path]` — Sirlar va maxfiy kalitlar sizib chiqishini aniqlash.
   - `agy-tool secure redact [path]` — Maxfiy ma'lumotlarni niqoblash (`[REDACTED_...]`).

4. **`debug`**:
   - `agy-tool debug trace [log]` — Xato stack trace tahlili va kod kontekstini aniqlash.
   - `agy-tool debug check [path]` — TypeScript / Python loyihalari sintaksis va tip diagnostikasi.

5. **`doc`** *(Zero-Token API Kontrakt & DTO Generator)*:
   - `agy-tool doc [path]` — NestJS, Express, Go, Laravel loyihalaridan 3 tomonlama sinxron eksport (`docs/api_contracts.md`, `types/api.contracts.d.ts`, `postman/api_collection.json`).
   - `--export=md,ts,postman` — Eksport formatlarini tanlash.
   - `--output-dir=[dir]` — Hujjatlar saqlanadigan yo'l.
   - `--force` — Incremental Sha256 keshini chetlab o'tish.
   - `--probe` — Xavfsiz GET-only aktiv probing.
   - `.apiignore` — Billing, webhooklar va maxfiy endpointlarni avtomatik filtrlash.

## 🛠 O'rnatish

```bash
git clone git@github.com:fummatov92/fayzillo-agy-tools.git ~/Desktop/fayzillo-agy-tools
cd ~/Desktop/fayzillo-agy-tools
bash install.sh
```
