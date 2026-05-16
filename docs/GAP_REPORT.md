# تقرير الفجوات — MASTER SPEC مقابل الوضع الحالي

مصدر المتطلبات: `vai-prompt.txt` (أقسام 1–20+).  
مصدر الواقع في المستودع: هيكل الملفات، `pyproject.toml`، `README.md`، `docs/COMPATIBILITY.md`، `PROGRESS.md`، وكود `src/vai_agent/` (استثناء `.venv` وملفات كاش).

**تحقق سريع:** `pytest` — **398 passed** بعد إصلاح معطلات OpenRouter/التوثيق. لا يشغّل CI `benchmark_questions.py` على قاعدة حقيقية افتراضيًا.

---

## ملخص تنفيذي

- المشروع **لا يثبّت حزمة `vanna`** ويعتمد **تجريدات داخلية** (`Agent`, `ToolRegistry`, أدوات، ذاكرة Chroma) موثّقة في `docs/COMPATIBILITY.md` — وهذا **مختلف صراحةً** عن طلب الـ SPEC لاستخدام Vanna كإطار رئيسي مع الالتزام بـ API المثبت.
- **الوكيل مربوط عند startup** عبر `create_app()` → `_initialise_runtime()` في `bootstrap.py` (تحميل profile، بناء agent، فتح memory).
- **OpenRouter / LLM Service** موجود كعميل `httpx` اختياري (`LLM_PROVIDER=openrouter`) ويُخزَّن في `app.state.llm_service`؛ لا يوجد بعد مسار HTTP جاهز يربطه بـ NL→SQL.
- **ملفّات profile الكاملة** موجودة لمثال **`profiles/dbnwind`**؛ مسار **`profiles/default/`** الوارد في الـ SPEC **غير موجود** (اختلف التسمية افتراضيًا إلى `DB_PROFILE_ID=dbnwind`).
- **`security_policy` مطبَّق عمليًا** في مسار `SecureRunSqlTool`: `SqlPolicyEngine` ثم `PiiPolicyEngine` ثم `MssqlRunner`.
- **`benchmark`** ينجح حسب ما ورد في `PROGRESS.md` (150/150 + 30/30 عند تشغيل السكربت محليًا)؛ الوحدة `tests/test_benchmark.py` تعطي تأمينًا في pytest لكن لا تغني عن تشغيل السكربت ضد مرجع SQL حقيقي.
- **`README.md` محدّث** لتعكس المرحلة الفعلية: `/health`، `/ready`، `/agent`، المتطلبات لقاعدة البيانات، أدوات CLI، وتبويب OpenRouter — راجع أيضًا **`PROGRESS.md`** للخط الزمني.

---

## جدول المقارنة

| المطلوب في MASTER SPEC (`vai-prompt.txt`) | الموجود حاليًا في المشروع | الناقص | المختلف | Blocker أم Improvement | خطة الإصلاح |
|-------------------------------------------|---------------------------|---------|---------|-------------------------|-------------|
| استخدام **Vanna 2.0** كإطار مع الالتزام بـ API النسخة المثبتة | لا اعتماد على `vanna`: تجريدات في `vai_agent.vai_app` + أدوات + ذاكرة عبر mirror التصميم | حزمة Vanna؛ محوّلات/طبقة توافق فعلية مع مكتبة Vanna | قرار تصميمي موثَّق في `COMPATIBILITY.md` (عكس نص SPEC الواضح بربط الإطار الرسمي) | **Improvement** لمواءمة رسالة المنتج مع SPEC؛ **Blocker** فقط لو كان شرطًا أن يكون استيراد `vanna` إلزاميًا | إما ضبط صياغة SPEC («Vanna-aligned») أو إضافة `vanna` + adapter خلف واجهة `ToolBase` كما في مسودّة التوافق |
| **OpenRouter** (OpenAI-compatible) قابل لتبديل المزوّد | طبقة `src/vai_agent/llm/` مع `OpenRouterChatService` و`build_chat_completion_client`؛ إعدادات أسرار في `Settings` وتوثيق في `.env.example`؛ الربط عند التشغيل إلى `app.state.llm_service` وإغلاق عبر الـ lifespan. | مخطّط لغوي/مسار أسئلة يستهلك هذا العميل لا يوجد ضمن مسارات HTTP الحالية | بدون SDK `openai` — اعتماد `httpx` فقط؛ انظر `COMPATIBILITY.md`. | المتبقي **Improvement** لمسألة «سؤال → SQL كاملاً»؛ **طرف OpenRouter الموصوف في GAP لم يعد حاجزاً لوجود عميل مهيّأ قابلاً للاستدعاء** | مخطّط فوق أدوات الوكيل يستدعي `chat_completion` ويصفّيه عبر سياسات SQL |
| **Rate limiting** (per user / IP في dev / access group / يومي / متزامن) | لم يُعثر على تطبيق واضح في FastAPI أو middleware | السياسات والعدادات ومخازن TTL | — | غالبًا **Improvement** لـ POC؛ **Blocker** عند تعرّض عام أو اشتراطات أمان صارمة | Middleware أو اعتماد `slowapi`/Redis؛ ربط `UserResolver` وبِطاقات IP |
| **ASSUMPTIONS.md** لتوثيق الافتراضات غير المؤكدة | الملف غير موجود | محتوى بأسلوب SPEC | الاعتماد على `COMPATIBILITY.md` + `PROGRESS.md` جزئيًا | **Improvement** | إنشاء `ASSUMPTIONS.md` وربطه من README |
| **pre-commit** (في Definition of Done في SPEC) | لا إعداد `pre-commit` في المستودع | hooks لـ ruff/format اختياري | CI يشغّل `ruff` و`pytest` فقط | **Improvement** | إضافة `.pre-commit-config.yaml` وتوثيق التفعيل |
| **type checker تلقائي** (متوقّع عملياً ضمن الجودة) | غير مضبوط في `pyproject.toml` | `pyright` أو `mypy` مستهدف `src/` | الاعتماد على ruff بدون فحص أنواع كامل | **Improvement** | إضافة إعداد وحدة وتدريجيًا رفع الشدة |
| **مسارات الملفات الدقيقة** مثل `data/input/schema.sql` و **`profiles/default/`** | `data/input/schema.sql` موجود؛ profile فعلي **`profiles/dbnwind`**؛ سكربت يذكر أيضًا `Schema.sql` كمسار بديل بحروف قد تختلف على أنظمة حساسة للحالة | مجلد `profiles/default/` كما في SPEC | اختيار اسم profile افتراضي مخالف للـ SPEC | **Improvement** لتجربة المطور | توحيد المسارات في الوثائق؛ symlink توثيقي أو نسخة `default` |
| **طبقة أمان SCHEMA**: `permissions.py`, `audit_log.py`, `query_limits.py`, `server_factory.py`, `extract_schema_from_mssql.py` | موجود: `sql_policy.py`, `pii_policy.py`, `errors.py`؛ حدود زمنية/صفوف عبر الإعداد وسياسة الأمان والـ runner | الوحدات المفقودة بالاسم كما خطّط الـ SPEC؛ لا `extract_schema_from_mssql.py` ضمن `scripts/` | الصلاحيات مدمجة في `ToolRegistry` + مجموعات المستخدم؛ لا طبقة تدقيق منفصلة قابلة للاستعلام | غالبًا **Improvement**؛ **audit منظم قد يصبح Blocker** للعمليات المنظَّمة | تقسيم تدريجي؛ مخزن تدقيق + حدود استعلام كوحدة إن لزم |
| **`schema_analyzer.py`** والتحليل العميق (30 نقطة+) | منطق توليد في **`profile_generator.py`** و **`schema_extractor.py`** وYAML للعلاقات | وحدة تحليل باسم `schema_analyzer`؛ لا `tests/test_schema_analyzer.py` | عمق الـ SPEC غير مغطّى كليًا بالتوليد الآلي الواضح | **Improvement**؛ **Blocker** لمتطلبات استنتاج معقّدة معتمدة بالكامل على التحليل | استخراج/توسيع المولّد + اختبارات ذهبية |
| **Web UI** مصغّر في SPEC | غير موجود | واجهة أو تكامل لاحق | API فقط | **Improvement** | صفحة بسيطة أو عميل خارجي موثَّق |
| **FastAPI + endpoints الوكيل** | `/health`, `/ready`, `/agent/tools` واستدعاء الأداة؛ في `api/query.py` | — | اسم الملف `query.py` يحوي مسارات agent وليس الاسم الوارد حصريًا في مخطّط SPEC | **Improvement** | إعادة تسمية أو توثيق |
| **ذاكرة دائمة** | Chroma persistent عبر `memory_factory.py` والـ seed | — | ليس نوع `vanna` الرسمي | — (مُلبّى وظيفيًا) | — |
| **UserResolver + مجموعات الوصول** | `users/user_resolver.py`؛ `access_groups` على الأدوات | OIDC/إنتاج كامل كما SPEC «المستقبل» | وضع `dev` افتراضي | **Improvement** | تنفيذ لاحق حسب المرحلة |
| **Benchmarking** | `scripts/benchmark_questions.py`، `docs/BENCHMARKING.md`، `tests/test_benchmark.py` | تشغيل benchmark في CI ضد SQL Server حقيقي | النتيجة المرجعية محليًا وفق `PROGRESS.md` | **Improvement**؛ **Blocker** إذا اشترط الـ Done تشغيل CI على DB | وظيفة اختيارية في CI أو «manual gate» موثَّق |
| **README عملي** | محدَّث لمطابقة التشغيل الحالي والمتغيرات (انظر قسم README و`.env.example`) | عمق أكبر لجميع المتغيرات الاختيارية | — | تم **معالجة** الجانب المتعلّق بـ onboarding؛ المتبقي **Improvement** لمرجع شامل | موسعة عند ظهورة متطلّبات جديدة |
| **Makefile / .venv** | `Makefile` وسلسلة أوامر `.venv` كما SPEC | — | — | — | — |

---

## إجابات على نقاط التركيز المطلوبة

1. **Vanna فعليًا أم تجريدات؟** — **تجريدات مخصّصة** داخل الحزمة، بدون تبعية `vanna` في `pyproject.toml`؛ الموثَّق هو «Vanna 2.0–inspired».

2. **هل Agent يُربط عند startup؟** — **نعم** في `bootstrap._initialise_runtime`: تحميل profile، `build_agent(...)`، `create_memory(...)`. يُعبَّأ أيضًا `app.state.readiness`.

3. **هل OpenRouter منفَّذ؟** — **نعم على مستوى العميل والإعداد والربط مع التطبيق** (`vai_agent.llm`؛ `bootstrap`؛ `Settings`)؛ لا يوجد بعد استدعاء تلقائي من مسار أسئلة المستخدم ضمن REST.

4. **هل ملفات profile كاملة؟** — **للمثال `dbnwind` نعم**. **`profiles/default` غير موجود** كما في SPEC.

5. **هل `security_policy` مطبَّق عمليًا؟** — **نعم** في مسار تنفيذ SQL قبل الاتصال بقاعدة البيانات.

6. **هل benchmark ينجح؟** — **`pytest`** نجح (**398**) مع اختبارات LLM المركَّبة؛ **`scripts/benchmark_questions.py`** يحتاج بيئة كما في `PROGRESS.md` ضد مرجع SQL حقيقي.

7. **هل أوامر README تعمل؟** **`ruff` / `pytest` / `uvicorn`** تبقى صالحة عند مهيّأ المشروع؛ تم **تحديث README** لمطابقته مع `/ready`، `/agent`، قاعدة البيانات، وملحق OpenRouter لكن يبقى دائمًا التحقّق بحسب جهاز المطور.

---

## ملاحظة عن «مراجعة ملفًا ملفًا»

تمت مراجعة **الكود المصدري، الإعدادات، الوثائق، ملفّات profiles، السكربتات، والاختبارات** ذات الصلة بالـ SPEC. لم تُنشأ قائمة آلية كل ملف تحت `.venv`/كاش لتجنّب ضوضاء غير ذات علاقة؛ الفجوات في الجدول تقابل **متطلبات وظيفية** من الـ MASTER SPEC.
