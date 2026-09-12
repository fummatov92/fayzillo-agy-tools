# 🐛 Bug Tracker — fayzillo-agy-tools

Bu fayl loyiha agentlari va ishlab chiquvchilar tomonidan kuzatib boriladigan xatolar jurnali.

---

## BUG-001 — `code endpoints` : Ko'p qatorli parametrli handler nomini noto'g'ri aniqlash

**Holat:** 🟢 Fixed  
**Muhimlik:** Medium  
**Modul:** `agy_tools/modules/code_tool.py` → `scan_nestjs_endpoints()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Lead Teamwork Worker (`0d0071d7-17eb-43aa-bcfe-d77d4c83ee92`)  

---

### 📋 Tavsif

`agy-tool code endpoints` buyrug'i NestJS controller fayllarini Regex orqali tahlil qilganda, **ko'p qatorga cho'zilgan parametr ro'yxatiga ega handler funksiyalarini** noto'g'ri nom bilan qaytaradi.

---

### 🔬 Ildiz Sabab

`scan_nestjs_endpoints()` funksiyasida `func_regex` quyidagicha ta'riflangan edi:

```python
# Muammoli satr (code_tool.py, ~73-satr):
func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)")
```

`([^)]*)` qismi yopuvchi `)` gacha bo'lgan matnni **bitta satr ichida** izlaydi.  
Agar handler funksiyaning parametrlari **bir necha satrga** cho'zilgan bo'lsa (NestJS da keng tarqalgan uslub), yopuvchi `)` shu satrda topilmaydi → `f_match` `None` qaytaradi → regex keyingi satrlarni tekshirishda davom etib, **birinchi mos kelgan boshqa iborani** (masalan `if`, `return`, yoki xizmat chaqiruvi) handler nomi sifatida belgilaydi.

---

### 🧪 Reproduksiya

**Test fayli:** `bot_post_using/src/modules/users/users.controller.ts`

```typescript
// Ko'p qatorli parametr → BUG chiqaradi
@Post()
@HttpCode(HttpStatus.OK)
async addAllowedUser(        // ← ')' yo'q, keyingi satrlarda
    @Body()
    body: {
      telegramId: string | number;
      firstName?: string;
    },
  ) {
    if (!body || !body.telegramId) {  // ← Regex "if" ni handler nomi deb oladi ❌
```

**Oldingi Xato Natija:**
```json
{ "method": "POST", "path": "/api/allowed-users", "handler": "if" }  ← XATO
```

**Kutilgan va Yangi Natija:**
```json
{ "method": "POST", "path": "/api/allowed-users", "handler": "addAllowedUser" }  ← TO'G'RI
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `func_regex` yopuvchi `)` ni kutmasdan metod nomini ochuvchi qavs bilan izlaydigan qilindi:
```python
func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(")
```

2. Tilning zahiralangan operator/konstruksiyalari (`constructor`, `if`, `for`, `while`, `switch`, `return`, `catch`, `try`) handler nomi sifatida olinishining oldini oluvchi filtr qo'shildi:
```python
RESERVED_WORDS = {"constructor", "if", "for", "while", "switch", "return", "catch", "try"}

if f_match and f_match.group(1) not in RESERVED_WORDS:
    func_name = f_match.group(1)
    break
```

3. `tests/test_audit_logger.py` fayliga regressiya testi (`test_scan_nestjs_endpoints_multiline`) qo'shildi va to'liq testlar muvaffaqiyatli o'tdi.
4. `install.sh` orqali `~/.local/bin/agy-tool` qayta o'rnatildi va real loyiha (`bot_post_using`) orqali tekshirildi.

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| Tekis (single-line) parametrli handlerlar | ✅ To'g'ri ishlaydi |
| Ko'p qatorli (`@Body()`, `@Param()` dekoratorli) parametrlar | ✅ To'g'ri handler nomi aniqlanadi |
| `@HttpCode`, `@UseGuards` kabi oraliq dekoratorlar | ✅ To'g'ri skip qilinadi |
| Express endpointlari | ✅ Ta'sir yo'q (mustaqil skaner) |

---

### 📌 Tegishli Fayllar

- [`agy_tools/modules/code_tool.py`](../agy_tools/modules/code_tool.py) — `scan_nestjs_endpoints()` tuzatildi
- [`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — `test_scan_nestjs_endpoints_multiline` qo'shildi
- [`install.sh`](../install.sh) — `~/.local/bin/agy-tool` ga deploy qilindi

---

*Hisobot muallifi: Lead Teamwork Worker | Sessiya: `0d0071d7-17eb-43aa-bcfe-d77d4c83ee92`*

---

## BUG-002 — `nestjs_adapter.py` : Ko'p qatorli dekoratorlar va `!` (definite assignment) maydonlarini DTO da xato tahlil qilish

**Holat:** 🟢 Fixed  
**Muhimlik:** High  
**Modul:** `agy_tools/adapters/nestjs_adapter.py` → `_parse_dto_class_body()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Lead Teamwork Worker (`9f412e22-79b0-4b97-8fc0-92385148675c`)  

---

### 📋 Tavsif

`agy-tool doc generate` buyrug'i NestJS DTO fayllarini tahlil qilganda:
1. Ko'p qatorli `@ApiProperty({...})` yoki `@ApiPropertyOptional({...})` dekoratorlarining ichidagi parametrlarini (masalan `example: '...'`, `default: '...'`, `description: '...'`) alohida DTO property deb o'ylab, soxta maydonlar yaratib yuboradi.
2. TypeScriptning definite assignment assertion (`!`) belgisi bilan e'lon qilingan maydonlar (masalan `name!: string;`) regexga tushmasdan DTO dan butunlay tushib qoladi.

---

### 🔬 Ildiz Sabab

1. `_parse_dto_class_body()` qator-ba-qator (`lines = body.split("\n")`) o'qigan va faqat `@` bilan boshlangan satrlarni dekorator deb hisoblagan. Ko'p qatorli dekoratorning 2-va keyingi satrlari (`example: '...'`) `@` bilan boshlanmagani uchun property regexiga to'g'ri kelib qolib, soxta maydon sifatida qo'shilgan.
2. Property regexi `([a-zA-Z0-9_]+)(\?)?\s*:\s*([^;=]+)` faqat `?` ni tekshirgan, `!` belgisi bo'lsa regex mos kelmagan.

---

### 🧪 Reproduksiya

**Test fayli:** `src/modules/company/dto/create-company.dto.ts` (`Loyihalar/zdes_backend`)

```typescript
export class CreateCompanyDto {
  @ApiProperty({
    example: 'ZDES',
  })
  @IsString()
  @MinLength(1)
  @MaxLength(255)
  name!: string;

  @ApiPropertyOptional({
    example: 'Asia/Tashkent',
    default: 'Asia/Tashkent',
    description:
      'IANA timezone used to compute attendance schedules for this company',
  })
  @IsOptional()
  @IsTimeZone()
  timezone?: string;
}
```

**Oldingi Xato Natija:**
```json
{
  "example": { "type": "'Asia/Tashkent',", "required": true },
  "default": { "type": "'Asia/Tashkent',", "required": true },
  "timezone": { "type": "string", "required": false }
}
// ❌ 'name' maydoni yo'q, 'example' va 'default' soxta maydonlar mavjud
```

**Kutilgan va Yangi Natija:**
```json
{
  "name": {
    "type": "string",
    "required": true,
    "minLength": 1,
    "maxLength": 255
  },
  "timezone": {
    "type": "string",
    "required": false
  }
}
// ✅ 'name' to'g'ri o'qildi, soxta maydonlar yo'q
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `_parse_dto_class_body` oqimli token/blok parsing mexanizmiga o'tkazildi:
   - `@` dekoratorlari ochuvchi `(` va yopuvchi `)` qavslari balansi bo'yicha to'liq bitta blok sifatida tanib olinadi va ko'p qatorli bo'lsa ham ichki satrlari property deb hisoblanmaydi.
2. Property regexi `([a-zA-Z0-9_$]+)([\?!])?\s*:\s*([^;=]+)` shakliga keltirilib, `!` (definite assignment) va `?` (optional) to'g'ri ajratildi (`!` bo'lsa `required = true`, `?` bo'lsa `required = false`).
3. `@MinLength` va `@MaxLength` kabi qo'shimcha dekoratorlar ham qo'llab-quvvatlandi.
4. `tests/test_doc_tool.py` da yangi test (`test_nestjs_dto_multiline_and_exclamation`) qo'shildi.
5. `install.sh` orqali yangilandi va `zdes_backend` real loyihasida tekshirildi.

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| Bir qatorli `@IsString()`, `@IsNumber()` kabi dekoratorlar | ✅ To'g'ri ishlaydi |
| Ko'p qatorli `@ApiProperty({...})`, `@ApiPropertyOptional({...})` dekoratorlari | ✅ Soxta maydonlar kirmaydi |
| `!` (definite assignment) bilan yozilgan maydonlar (`name!: string;`) | ✅ To'g'ri aniqlanadi (`required: true`) |
| `?` (optional) maydonlar (`age?: number;`) | ✅ To'g'ri aniqlanadi (`required: false`) |
| Boshqa freymvork adapterlari | ✅ Ta'sir yo'q (izolyatsiyalangan) |

---

### 📌 Tegishli Fayllar

- [`agy_tools/adapters/nestjs_adapter.py`](../agy_tools/adapters/nestjs_adapter.py) — `_parse_dto_class_body()` yangilandi
- [`tests/test_doc_tool.py`](../tests/test_doc_tool.py) — Yangi test qo'shildi
- [`bugs.md`](./bugs.md) — Hujjatlashtirildi

---

*Hisobot muallifi: Lead Teamwork Worker | Sessiya: `9f412e22-79b0-4b97-8fc0-92385148675c`*

---

## BUG-003 — `nestjs_adapter.py` : `main.ts` dagi Global API Prefix (`app.setGlobalPrefix`) ni inobatga olmaslik

**Holat:** 🟢 Fixed  
**Muhimlik:** Medium  
**Modul:** `agy_tools/adapters/nestjs_adapter.py` → `_find_global_prefix()`, `scan()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Lead Teamwork Worker (`d5d4f06d-e743-40da-922b-d75b1d37bdf0`)  

---

### 📋 Tavsif

NestJS loyihalarida `main.ts` ichida ko'pincha `app.setGlobalPrefix('api/v1')` sozlanadi.  
Oldingi `nestjs_adapter.py` faqat `@Controller('companies')` ni o'qib, marshrutni `/companies` deb chiqarar edi.  
Natijada tirik serverga `curl http://localhost:4000/companies` qilganda `404 Not Found` qaytgan (haqiqiy tirik yo'l: `/api/v1/companies`).

---

### 🔬 Ildiz Sabab

`nestjs_adapter.py` loyihadagi `main.ts` (yoki `bootstrap`) faylida `app.setGlobalPrefix(...)` e'lon qilinganini qidirmagan va controller prefiksiga global prefiksni qo'shmagan edi.

---

### 🧪 Reproduksiya va Real Loyiha Tekshiruvi

**Real loyiha:** `Loyihalar/zdes_backend/src/main.ts` (`const API_PREFIX = 'api/v1'; app.setGlobalPrefix(API_PREFIX);`)

**Oldingi Xato Natija:**
```
GET /companies
POST /auth/login
```

**Yangi To'g'ri Natija:**
```
GET /api/v1/companies
POST /api/v1/auth/login
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `NestJSAdapter` ga `_find_global_prefix()` metodi qo'shildi:
   - `main.ts`, `main.js`, `bootstrap.ts`, `app.ts` kabi kirish fayllaridan `app.setGlobalPrefix(...)` chaqiruvini topadi.
   - String literal (`'api/v1'`), expression fallback (`process.env.API_PREFIX || 'api/v1'`) va o'zgaruvchi deklaratsiyalari (`const API_PREFIX = 'api/v1'`) avtomatik tahlil qilinadi.
2. `scan()` da controller prefikslari va sub-yo'llar bilan birlashtiriladi (agar controller marshruti allaqachon prefiks bilan boshlangan bo'lsa, takrorlanish oldi olinadi).
3. `code_tool.py` dagi `scan_nestjs_endpoints()` funksiyasiga ham mos ravishda global prefix tahlili qo'shildi.
4. `tests/test_doc_tool.py` ga `test_nestjs_global_prefix_discovery` unit testi kiritildi va 100% muvaffaqiyatli o'tdi.

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| `app.setGlobalPrefix('api/v1')` mavjud loyihalar | ✅ Barcha marshrutlar boshiga `/api/v1` qo'shiladi |
| `app.setGlobalPrefix(API_PREFIX)` o'zgaruvchili | ✅ O'zgaruvchi qiymati topilib ulanadi |
| Global prefix belgilanmagan loyihalar | ✅ Standart controller prefiksi bilan ishlayveradi |
| `@Controller('api/v1/...')` kabi qo'lda yozilgan yo'llar | ✅ Duplikatsiyasiz `/api/v1/...` saqlanadi |

---

### 📌 Tegishli Fayllar

- [`agy_tools/adapters/nestjs_adapter.py`](../agy_tools/adapters/nestjs_adapter.py) — `_find_global_prefix()` va `scan()` yangilandi
- [`agy_tools/modules/code_tool.py`](../agy_tools/modules/code_tool.py) — `_find_nestjs_global_prefix()` va `scan_nestjs_endpoints()` yangilandi
- [`tests/test_doc_tool.py`](../tests/test_doc_tool.py) — `test_nestjs_global_prefix_discovery` qo'shildi

---

## BUG-004 — `express_adapter.py` : `server.js` dagi Router Mount Prefikslarini (`app.use('/api/...', router)`) router fayllariga bog'lamaslik

**Holat:** 🟢 Fixed  
**Muhimlik:** Medium  
**Modul:** `agy_tools/adapters/express_adapter.py` → `_build_router_mount_map()`, `scan()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Lead Teamwork Worker (`d5d4f06d-e743-40da-922b-d75b1d37bdf0`)  

---

### 📋 Tavsif

Express loyihalarida (masalan `sessiya_connector/backend`) marshrut fayllari `statusRoutes.js` da `router.get('/', ...)` va `router.get('/usage', ...)` deb yoziladi va `server.js` da quyidagicha ulanadi:
```javascript
app.use('/api/status', statusRoutes);
```
Oldingi `express_adapter.py` faqat `statusRoutes.js` ichidagi `GET /` va `GET /usage` ni o'qigan edi.  
Natijada `curl http://127.0.0.1:15976/usage` qilganda `404` qaytgan (haqiqiy yo'l: `/api/status/usage`).

---

### 🔬 Ildiz Sabab

`express_adapter.py` `app.use('prefix', routerImport)` bog'lanishlarini tahlil qilmagan, har bir router faylini alohida mustaqil marshrut deb hisoblagan.

---

### 🧪 Reproduksiya va Real Loyiha Tekshiruvi

**Real loyiha:** `sessiya_connector/backend`

**Oldingi Xato Natija:**
```
GET /
GET /usage
POST /login
```

**Yangi To'g'ri Natija:**
```
GET /
GET /api/status
GET /api/status/usage
POST /api/auth/login
GET /api/sessions
GET /api/approval/pending
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `ExpressAdapter` ga `_build_router_mount_map()` metodi qo'shildi:
   - Loyihadagi kirish va router fayllaridan `const statusRoutes = require('./routes/statusRoutes')` va `import ... from ...` bog'lanishlarini xaritalaydi.
   - `app.use('/api/status', statusRoutes)` va inline `app.use('/api/status', require('./routes/statusRoutes'))` deklaratsiyalarini tahlil qiladi.
   - 3-bosqichli ko'p o'tishli (multi-pass) zanjir orqali ichma-ich (nested) router ulanishlarini to'liq qo'llab-quvvatlaydi.
   - Nisbiy yo'llar va barcha kengaytmalar (`.js`, `.ts`, `.mjs`, `index.js`) uchun alias xaritasini hosil qiladi.
2. `scan()` da router faylidagi har bir yo'l boshiga mount prefiksi ulanadi.
3. `code_tool.py` dagi `scan_express_endpoints()` ga ham mos mount xaritasi integratsiya qilindi.
4. `tests/test_doc_tool.py` ga `test_express_router_mount_map` unit testi kiritildi va 100% muvaffaqiyatli o'tdi.

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| `app.use('/api/status', statusRoutes)` kabi Router Mountlar | ✅ `router.get('/usage')` ➔ `/api/status/usage`, `router.get('/')` ➔ `/api/status` |
| `app.use('/api/auth', require('./auth'))` inline mountlar | ✅ To'g'ri prefiks ulanadi |
| To'g'ridan-to'g'ri `app.get('/')` (server.js dagi) | ✅ `/` prefikssiz to'g'ri qoladi |
| Next.js App / Pages router marshrutlari | ✅ Standart `/api/...` marshrutlash saqlanadi |

---

### 📌 Tegishli Fayllar

- [`agy_tools/adapters/express_adapter.py`](../agy_tools/adapters/express_adapter.py) — `_build_router_mount_map()` va `scan()` yangilandi
- [`agy_tools/modules/code_tool.py`](../agy_tools/modules/code_tool.py) — `_build_express_mount_map()` va `scan_express_endpoints()` yangilandi
- [`tests/test_doc_tool.py`](../tests/test_doc_tool.py) — `test_express_router_mount_map` qo'shildi
- [`bugs.md`](./bugs.md) — BUG-003 va BUG-004 yopildi (Fixed)

---

*Hisobot muallifi: Lead Teamwork Worker | Sessiya: `d5d4f06d-e743-40da-922b-d75b1d37bdf0`*

---

## BUG-005 — `debug_tool.py` : `debug check` da `node_modules` yoki `tsc` bo'lmaganda noto'g'ri bo'sh xatolar qaytarish

**Holat:** 🟢 Fixed  
**Muhimlik:** Low  
**Modul:** `agy_tools/modules/debug_tool.py` → `find_tsc_binary()`, `run_debug_check()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Lead Teamwork Worker (`a3061121-b8c5-45fb-9f27-f3f0c81ed890`)  

---

### 📋 Tavsif

Agar loyiha jildida `node_modules` o'rnatilmagan bo'lsa (yoki `tsc` global o'rnatilmagan bo'lsa), `npx tsc` buyrug'i `exit code 1` qaytaradi va stdout'da `error TS` bo'lmaydi.  
`debug_tool.py` bu holatda `status: "Errors Found", error_count: 0, errors: []` qaytarar edi.

---

### 🔬 Ildiz Sabab

1. `npx tsc` tsc ni topa olmaganida npm stub paketi matnini chiqaradi va `res.returncode != 0` bo'ladi.
2. `debug_tool.py` faqat `error TS` qatorlarini filtrlaydi, stderr va compiler topilmagan holatlarni alohida kompilyator xatosi sifatida qayd etmagan.
3. Loyihada lokal yoki ota jilddagi `node_modules/.bin/tsc` mavjud bo'lsa ham, faqat shunchaki `npx tsc` ga murojaat qilingan.

---

### 🧪 Reproduksiya

**Oldingi Xato Natija:**
```json
{
  "project_path": "/path/to/project",
  "checks": [
    {
      "type": "TypeScript",
      "status": "Errors Found",
      "error_count": 0,
      "errors": []
    }
  ]
}
```

**Kutilgan va Yangi To'g'ri Natija:**
```json
{
  "project_path": "/path/to/project",
  "checks": [
    {
      "type": "TypeScript",
      "status": "Compiler Execution Failed",
      "compiler": "npx tsc",
      "error_count": 1,
      "errors": ["npm ERR! could not determine executable to run"]
    }
  ]
}
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `debug_tool.py` ga `find_tsc_binary(target_path)` funksiyasi qo'shildi:
   - 1) Lokal `target_path/node_modules/.bin/tsc` ni tekshirish.
   - 2) Ota jildlar (monorepo / parent packages) bo'ylab `node_modules/.bin/tsc` ni rekursiv izlash.
   - 3) Tizim `PATH` dagi `tsc` (`shutil.which("tsc")`) ni tekshirish.
   - 4) Oxirgi fallback sifatida `npx tsc` ni ishlatish.
2. `run_debug_check` da agar `res.returncode != 0` bo'lsa va `error TS` topilmasa, `status: "Compiler Execution Failed"` deb belgilanib, stderr/stdout dagi real xato xabari `errors` ro'yxatida qaytarilishi ta'minlandi.
3. `tests/test_audit_logger.py` fayliga `test_debug_check_compiler_fallback` unit testi qo'shildi va to'liq testlar 100% muvaffaqiyatli o'tdi.
4. `install.sh` orqali `~/.local/bin/agy-tool` yangilandi.

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| Lokal `node_modules/.bin/tsc` mavjud loyihalar | ✅ To'g'ridan-to'g'ri lokal binary orqali tezkor tahlil |
| Monorepo / parent `node_modules` loyihalar | ✅ Ota papkadagi binary topilib ishlatiladi |
| `tsc` yoki `node_modules` o'rnatilmagan loyihalar | ✅ Soxta bo'sh xato o'rniga aniq `Compiler Execution Failed` va sababi qaytadi |
| Tiplar xatosi mavjud TypeScript loyihalar | ✅ `Errors Found` va aniq xato satrlari saqlanadi |
| Toza loyihalar | ✅ `Clean (No Type Errors)` to'g'ri qaytadi |

---

### 📌 Tegishli Fayllar

- [`agy_tools/modules/debug_tool.py`](../agy_tools/modules/debug_tool.py) — `find_tsc_binary()` va `run_debug_check()` tuzatildi
- [`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — `test_debug_check_compiler_fallback` qo'shildi
- [`bugs.md`](./bugs.md) — BUG-005 yopildi (Fixed)

---

*Hisobot muallifi: Lead Teamwork Worker | Sessiya: `a3061121-b8c5-45fb-9f27-f3f0c81ed890`*

---

## BUG-006 — `code symbols` : `symbols` buyrug'i CLI parserida ro'yxatdan o'tmagani va funksiyalar signaturalari ajratgichi yetishmasligi

**Holat:** 🟢 Fixed  
**Muhimlik:** Medium  
**Modul:** `agy_tools/modules/code_tool.py`, `bin/agy-tool`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tuzatilgan sana:** 2026-09-12  
**Mas'ul Agent:** Core AI Engine (`a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  

---

### 📋 Tavsif

`agy-tool --describe` chiqishida va hujjatlarda `code symbols` buyrug'i e'lon qilingan bo'lsa-da, `bin/agy-tool` subparsers ro'yxatida `symbols` qo'shilmagan edi. Natijada `agy-tool code symbols <path>` chaqirilganda `argument action: invalid choice: 'symbols'` xatoligi yuz bergan. Shuningdek `code_tool.py` da barcha dasturlash tillari (TS/JS, Python, Go, PHP) uchun AST/Regex signaturalarni ajratish funksiyasi to'liq ulanmagan edi.

---

### 🔬 Ildiz Sabab

1. `bin/agy-tool` da `code_p` subparseriga faqat `blueprint` va `endpoints` qo'shilgan, `symbols` subparseri qolib ketgan edi.
2. `code_tool.py` da `extract_symbols_from_file()`, `extract_symbols()` va `run_code_symbols()` funksiyalari mavjud emas edi.

---

### 🧪 Reproduksiya

**Oldingi Xato Natija:**
```
usage: agy-tool code [-h] {blueprint,endpoints} ...
agy-tool code: error: argument action: invalid choice: 'symbols' (choose from 'blueprint', 'endpoints')
```

**Yangi To'g'ri Natija:**
```json
{
  "target_path": "/path/to/module",
  "scanned_files_count": 7,
  "total_symbols_count": 18,
  "kinds_breakdown": { "type": 3, "class": 7, "method": 8 },
  "symbols": [
    { "name": "CompanyService", "kind": "class", "line": 31, "file": "company.service.ts", "signature": "export class CompanyService" },
    { "name": "create", "kind": "method", "line": 34, "file": "company.service.ts", "signature": "async create(dto: CreateCompanyDto)" }
  ]
}
```

---

### ✅ Amalga Oshirilgan Tuzatish

1. `code_tool.py` ga ko'p tilli (TypeScript, JavaScript, Python, Go, PHP) AST/Regex asosidagi `extract_symbols_from_file()`, `extract_symbols()` va `run_code_symbols()` funksiyalari kiritildi.
2. `bin/agy-tool` ga `code symbols` subparseri va handleri ulandi.
3. `tests/test_audit_logger.py` ga `test_code_symbols_bug_006` regressiya testi kiritildi va to'liq testlardan 100% muvaffaqiyatli o'tdi.
4. `install.sh` orqali yangilandi va jonli deploy qilindi.

---

### 📌 Tegishli Fayllar

- [`agy_tools/modules/code_tool.py`](../agy_tools/modules/code_tool.py) — `extract_symbols()` va `run_code_symbols()` qo'shildi
- [`bin/agy-tool`](../bin/agy-tool) — `symbols` subparser va marshruti ulandi
- [`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — `test_code_symbols_bug_006` qo'shildi
- [`bugs.md`](./bugs.md) — BUG-006 yopildi (Fixed)

---

*Hisobot muallifi: Core AI Engine | Sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`*





