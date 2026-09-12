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

**Holat:** 🔴 Open  
**Muhimlik:** Medium  
**Modul:** `agy_tools/adapters/nestjs_adapter.py` → `scan()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tayinlangan:** Lead Teamwork Worker  

---

### 📋 Tavsif

NestJS loyihalarida `main.ts` ichida ko'pincha `app.setGlobalPrefix('api/v1')` sozlanadi.  
Hozirgi `nestjs_adapter.py` faqat `@Controller('companies')` ni o'qib, marshrutni `/companies` deb chiqaradi.  
Natijada tirik serverga `curl http://localhost:4000/companies` qilganda `404 Not Found` qaytadi (haqiqiy tirik yo'l: `/api/v1/companies`).

---

### 🔬 Ildiz Sabab

`nestjs_adapter.py` loyihadagi `main.ts` (yoki `bootstrap`) faylida `app.setGlobalPrefix(...)` e'lon qilinganini qidirmaydi va controller prefiksiga global prefiksni qo'shmaydi.

---

### 🧪 Reproduksiya va Curl Testi

**Real loyiha:** `Loyihalar/zdes_backend/src/main.ts` (`const API_PREFIX = 'api/v1'; app.setGlobalPrefix(API_PREFIX);`)

- `curl -s http://localhost:4000/companies` ➔ `404 Not Found` ❌
- `curl -s http://localhost:4000/api/v1/auth/login` ➔ `400 Bad Request (Live Handler Answered)` ✅

---

### ✅ Taklif Qilinayotgan Tuzatish

1. `main.ts` faylini skanerlab, `app.setGlobalPrefix\((?:['"]([^'"]+)['"]|([A-Za-z0-9_]+))\)` va tegishli o'zgaruvchini topish.
2. Agar global prefix topilsa, barcha endpointlar yo'liga bosh prefiks sifatida qo'shish (masalan `/{global_prefix}/{controller_prefix}/{route}`).

---

## BUG-004 — `express_adapter.py` : `server.js` dagi Router Mount Prefikslarini (`app.use('/api/...', router)`) router fayllariga bog'lamaslik

**Holat:** 🔴 Open  
**Muhimlik:** Medium  
**Modul:** `agy_tools/adapters/express_adapter.py` → `scan()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tayinlangan:** Lead Teamwork Worker  

---

### 📋 Tavsif

Express loyihalarida (masalan `sessiya_connector/backend`) marshrut fayllari `statusRoutes.js` da `router.get('/', ...)` va `router.get('/usage', ...)` deb yoziladi va `server.js` da quyidagicha ulanadi:
```javascript
app.use('/api/status', statusRoutes);
```
Hozirgi `express_adapter.py` faqat `statusRoutes.js` ichidagi `GET /` va `GET /usage` ni o'qiydi.  
Natijada `curl http://127.0.0.1:15976/usage` qilganda `404` qaytadi (haqiqiy yo'l: `/api/status/usage`).

---

### 🔬 Ildiz Sabab

`express_adapter.py` `app.use('prefix', routerImport)` bog'lanishlarini AST/Regex orqali tahlil qilmaydi, har bir faylni alohida mustaqil marshrut deb hisoblaydi.

---

### ✅ Taklif Qilinayotgan Tuzatish

1. Asosiy entrypoint (`server.js`, `app.js`, `index.js`) faylidan `const statusRoutes = require('./routes/statusRoutes')` va `app.use('/api/status', statusRoutes)` xaritasini (Router Mount Map) qurish.
2. Router fayllarini tahlil qilayotganda tegishli mount prefiksini yo'l boshiga qo'shish.

