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
