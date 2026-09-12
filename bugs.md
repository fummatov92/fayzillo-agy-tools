# 🐛 Bug Tracker — fayzillo-agy-tools

Bu fayl loyiha agentlari va ishlab chiquvchilar tomonidan kuzatib boriladigan xatolar jurnali.

---

## BUG-001 — `code endpoints` : Ko'p qatorli parametrli handler nomini noto'g'ri aniqlash

**Holat:** 🔴 Open  
**Muhimlik:** Medium  
**Modul:** `agy_tools/modules/code_tool.py` → `scan_nestjs_endpoints()`  
**Aniqlagan:** Core AI Engine (AGY sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`)  
**Aniqlash sanasi:** 2026-09-12  
**Tayinlangan:** Teamwork Development Agent  

---

### 📋 Tavsif

`agy-tool code endpoints` buyrug'i NestJS controller fayllarini Regex orqali tahlil qilganda, **ko'p qatorga cho'zilgan parametr ro'yxatiga ega handler funksiyalarini** noto'g'ri nom bilan qaytaradi.

---

### 🔬 Ildiz Sabab

`scan_nestjs_endpoints()` funksiyasida `func_regex` quyidagicha ta'riflangan:

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

**Natija:**
```json
{ "method": "POST", "path": "/api/allowed-users", "handler": "if" }  ← XATO
```

**Kutilgan natija:**
```json
{ "method": "POST", "path": "/api/allowed-users", "handler": "addAllowedUser" }  ← TO'G'RI
```

---

### ✅ Taklif Qilingan Tuzatish

**Yondashuv:** Handler nomini aniqlashda yopuvchi `)` ni **kutmay**, faqat `methodName(` pattern ni izlash yetarli.

```python
# HOZIRGI (xato):
func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)")

# TAVSIYA ETILGAN (to'g'ri):
func_regex = re.compile(r"(?:async\s+)?([a-zA-Z0-9_]+)\s*\(")
```

Qo'shimcha shart: `constructor`, `if`, `for`, `while`, `switch` kabi kalit so'zlar **filtrlanishi shart**:

```python
RESERVED_WORDS = {"constructor", "if", "for", "while", "switch", "return", "catch", "try"}

if f_match and f_match.group(1) not in RESERVED_WORDS:
    func_name = f_match.group(1)
    break
```

---

### 📦 Ta'sir Doirasi

| Holat | Ta'sir |
|-------|--------|
| Tekis (single-line) parametrli handlerlar | ✅ Ta'sir yo'q |
| Ko'p qatorli (`@Body()`, `@Param()` dekoratorli) parametrlar | ❌ Noto'g'ri handler nomi |
| `@HttpCode`, `@UseGuards` kabi oraliq dekoratorlar | ✅ To'g'ri skip qilinadi |
| Express endpointlari | ✅ Ta'sir yo'q (boshqa funksiya) |

---

### 📌 Tegishli Fayllar

- [`agy_tools/modules/code_tool.py`](../agy_tools/modules/code_tool.py) — `scan_nestjs_endpoints()`, ~73-satr
- [`tests/test_audit_logger.py`](../tests/test_audit_logger.py) — Yangi test case qo'shilishi kerak
- [`rollback.sh`](../rollback.sh) — O'zgarishdan keyin `--dry-run` tasdiqlanishi shart

---

### 🔗 Qo'shimcha Kontekst

`ORIGINAL_REQUEST.md` (Follow-up 2026-09-12T12:21:49Z) da `nestjs_adapter.py` uchun ko'p qatorli parametr (DTO, `@Body()`, `@Param()`) to'g'ri parse qilinishi talab qilingan edi. Ushbu bug `doc_tool` loyihasiga o'tishdan oldin `code_tool` da ham tuzatilishi maqsadga muvofiq.

---

*Hisobot muallifi: JarvisOS Core AI Engine | Sessiya: `a8b64ff4-d90b-4ac1-9c7c-129824ce21b6`*
