# Launch announcements — ready-to-post (EN + RU)

Repo: https://github.com/NickoScope/nickol-knx-mcp · Site: https://nickoscope.github.io/nickol-knx-mcp/ · Case study: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.md

**Current: v0.6.0** — roadmap complete: **24 MCP tools** that validate (naming · DPT/sub-DPT · status · KNX Secure · Matter), **repair** (propose fixes), **decompose devices**, **diff** two versions, **grade** completeness, and **generate** Home Assistant YAML (colour + climate), ETS exports, an as-built **handover pack** & KNX IoT — all read-only. Plus a spec-PDF → **96%-match** GA-structure case study. The posts below still lead with the colour/climate assembly milestone.

Etiquette reminder: disclose you're the author, lead with value, be online to answer for a few hours after posting. Don't cross-post everything in one hour — space it out (home base → targeted forums → Reddit/Discord → social).

---

## 1) GitHub Discussions — Announcements (canonical home post)

### EN
**Title:** nickol-knx-mcp v0.1.2 — a design-time KNX/ETS assistant as an MCP server (beta, testers wanted)

Hi everyone 👋

I'm releasing **nickol-knx-mcp** — an open-source, **design-time** assistant for KNX/ETS, exposed as an [MCP](https://modelcontextprotocol.io) server. From Claude (or any MCP client) it reads your `.knxproj` **read-only**, validates it, and generates your Home Assistant + ETS files — and it **never touches the bus** (there are no bus/networking libraries in it at all; `bus_access: false`, by design).

**What it does**
- Validates **naming**, **DPT discipline**, and **command↔status pairing** (using the roles in your ETS **Functions**, not guesswork).
- Generates a **Home Assistant KNX package** and **ETS-importable** group-address exports (XML/CSV).
- Writes a **human-readable report you review before importing anything**.

**Proof it's real:** I hammered it on public ETS 4.2 / 5.0 / 5.5 / 6 projects — it immediately found a **critical bug in itself** plus several real-world classification gaps (German shutter naming, `1.001`+`1.017` blinds, dimmer status pairing, datetime DPTs). All fixed, each with a regression test. There's a full **239-GA / 47-Function demo house** with a Home Assistant "brain" (circadian lighting, an 8-factor climate setpoint, presence/season/time logic, statistics) and a 5-view dashboard.

🔗 **Live demo + screenshots:** https://nickoscope.github.io/nickol-knx-mcp/

**It's a beta — and that's the invitation.** It's passed synthetic + public-fixture tests, but real ETS projects are gloriously messy and I've seen only a few. Please **try it on your own `.knxproj`** (read-only, safe) and open a *Real-project test report* — what it got right, what it got wrong. Code contributions and weird regional DPT/naming examples are just as welcome.

MIT · Python 3.10+. Thanks for taking a look 🙏

### RU
**Заголовок:** nickol-knx-mcp v0.1.2 — design-time ассистент KNX/ETS в виде MCP-сервера (бета, нужны тестировщики)

Всем привет 👋

Выкладываю **nickol-knx-mcp** — открытый **design-time** ассистент для KNX/ETS в виде [MCP](https://modelcontextprotocol.io)-сервера. Из Claude (или любого MCP-клиента) он **только читает** ваш `.knxproj`, проверяет его и генерирует конфигурацию Home Assistant + файлы для ETS — и **никогда не лезет в шину** (в нём вообще нет сетевых/шинных библиотек; `bus_access: false`, структурно).

**Что умеет**
- Проверяет **именование**, **дисциплину DPT** и **парность команда↔статус** (по ролям из ваших ETS **Functions**, а не наугад).
- Генерирует **HA KNX-пакет** и **ETS-импортируемые** экспорты групповых адресов (XML/CSV).
- Делает **человекочитаемый отчёт, который вы смотрите до импорта**.

**Доказательство, что это работает:** прогнал на реальных публичных проектах ETS 4.2 / 5.0 / 5.5 / 6 — и он сразу нашёл **критический баг в себе** + несколько реальных пробелов классификации (немецкий нейминг штор, жалюзи на `1.001`+`1.017`, парность статуса диммеров, DPT даты/времени). Всё исправлено, на каждое — регресс-тест. Есть полный **демо-дом из 239 GA / 47 Functions** с HA-«мозгом» (циркадный свет, уставка климата из 8 факторов, логика присутствие/сезон/время, статистика) и дашбордом на 5 экранов.

🔗 **Живое демо + скриншоты:** https://nickoscope.github.io/nickol-knx-mcp/

**Это бета — и в этом приглашение.** Синтетику и публичные фикстуры прошёл, но реальные ETS-проекты бесконечно разнообразны, а я видел их немного. Прогоните на **своём `.knxproj`** (только чтение, безопасно) и заведите *Real-project test report* — что поймал, что нет. Контрибуции в код и «странные» региональные примеры DPT/нейминга — тоже очень нужны.

MIT · Python 3.10+. Спасибо, что заглянули 🙏

---

## 2) KNX User Forum (knx-user-forum.de) — English section

### EN
**Subject:** [Open source] Design-time KNX/ETS assistant + a spec-PDF → 96%-match GA-structure experiment — beta, testers wanted

Hi all,

I've built an open-source **design-time** assistant for KNX and I'd value this community's critical eye. It's an MCP server an AI client (Claude) drives — but the important part is what it does to a project, not the AI:

- Reads a `.knxproj` **read-only** — **no bus access at all** (no KNX/IP or networking libraries in the dependency tree; it physically cannot reach an installation).
- Checks **naming**, **DPT consistency** and **missing status objects**; pairs command↔status from **ETS Function roles** (with a name-based fallback for projects that don't use Functions).
- Classifies **reserve / logic / scratch** group addresses so the report stops "crying wolf" on real installs.
- Generates a **Home Assistant** package — now assembling **colour lights (RGBW/RGB/CCT)** and **`climate`** entities — plus **ETS-importable** GA exports (XML/CSV) and a Markdown report to review **before** import.

The experiment that surprised me: from a **42-page project spec (PDF) alone**, an AI assistant grounded in the **KNX Association standard** designed the full GA structure; the tool validated it (**0 errors**) and produced the HA package. Versus a professional reference implementation of the same flat: **96% structural match · 10/10 domain taxonomy · 118 byte-identical names · in minutes**. The routine "skeleton" auto-designs to near-pro quality; the project-specific logic stays the engineer's craft.

It's **beta** and read-only (safe to try on a real `.knxproj`). Honest, technical feedback — including "this is wrong because…" — is exactly what I'm after.

Repo: https://github.com/NickoScope/nickol-knx-mcp · Case study: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.md · Demo: https://nickoscope.github.io/nickol-knx-mcp/ · MIT.

*Not affiliated with the KNX Association; KNX/ETS are trademarks of the KNX Association cc.*

### RU
**Тема:** [Open source] Design-time ассистент KNX/ETS + эксперимент «ТЗ в PDF → GA-структура с 96% совпадения» — бета, нужны тестировщики

Всем привет,

Сделал открытый **design-time** ассистент для KNX и хотел бы критики сообщества. Это MCP-сервер, которым управляет AI-клиент (Claude), но суть — в том, что он делает с проектом, а не в AI:

- Читает `.knxproj` **только на чтение** — **без доступа к шине** (в зависимостях нет KNX/IP и сетевых библиотек; физически не достучится до инсталляции).
- Проверяет **именование**, **согласованность DPT** и **отсутствующие статусы**; паря команда↔статус по ролям **ETS Functions** (с откатом на нейминг для проектов без Functions).
- Классифицирует **резерв / логику / мусор**, чтобы отчёт не «кричал волки» на реальных объектах.
- Генерирует пакет **Home Assistant** — теперь собирает **цветной свет (RGBW/RGB/CCT)** и сущности **`climate`** — плюс **ETS-импортируемые** экспорты GA (XML/CSV) и Markdown-отчёт для ревью **до** импорта.

Что удивило: **из одного 42-страничного ТЗ (PDF)** AI-ассистент, заземлённый на **стандарт KNX Association**, спроектировал полную GA-структуру; инструмент проверил её (**0 ошибок**) и выдал HA-пакет. В сравнении с профессиональной эталонной реализацией той же квартиры — **96% структурного совпадения · 10/10 доменов · 118 дословных имён · за минуты**. Стандартный «скелет» проектируется автоматически почти на уровне профи; проектная логика остаётся ремеслом инженера.

Это **бета**, только чтение (на реальном `.knxproj` пробовать безопасно). Честная техническая критика — в т.ч. «вот тут неправильно, потому что…» — именно то, что нужно.

Репозиторий: https://github.com/NickoScope/nickol-knx-mcp · Кейс: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.ru.md · Демо: https://nickoscope.github.io/nickol-knx-mcp/ · MIT.

---

## 3) Home Assistant Community forum (community.home-assistant.io → Share your Projects)

### EN
**Title:** An MCP server that turns your KNX/ETS project into a Home Assistant package — now with colour lights + climate (open source, read-only)

If you run KNX under Home Assistant, the worst part is the **handoff**: hand-copying hundreds of group addresses into YAML and hoping you didn't miss a status address.

**nickol-knx-mcp** automates that. It's an open-source MCP server that reads your `.knxproj` **read-only** (no bus access at all), validates naming/DPT/missing-status, pairs command↔status from your ETS Functions, and **generates the KNX package YAML for you** — with a review list so nothing is dropped silently. **v0.2.0** now assembles **colour lights (RGBW/RGB/CCT)** and **`climate`** entities (keys verified against the HA KNX docs), and classifies reserve/logic "noise" so the report stays focused on real devices.

There's a demo house with a Home-Assistant **"brain"** (circadian lighting, an 8-factor climate setpoint, presence/season/time logic, statistics) driving a 5-view dashboard — real screenshots on the site. And a fun result: from a project **spec PDF alone** it auto-designed a full GA structure that matched a professional reference **96%** (case study linked).

🔗 Demo + dashboard: https://nickoscope.github.io/nickol-knx-mcp/
💻 Repo (MIT): https://github.com/NickoScope/nickol-knx-mcp · 📐 Case study: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.md

It's beta — I'd love folks with real KNX setups to try it and tell me how the generated YAML compares to your hand-written config. Feedback very welcome!

### RU
**Заголовок:** MCP-сервер, который превращает ваш KNX/ETS-проект в пакет Home Assistant — теперь с цветным светом и климатом (open source, только чтение)

Если у вас KNX под Home Assistant, худшее — это **передача проекта**: вручную перебивать сотни групповых адресов в YAML и надеяться, что не пропустил статусный адрес.

**nickol-knx-mcp** это автоматизирует. Открытый MCP-сервер: читает `.knxproj` **только на чтение** (доступа к шине нет вообще), проверяет именование/DPT/отсутствие статусов, паря команда↔статус по вашим ETS Functions, и **генерирует KNX-пакет YAML за вас** — со списком `review`, чтобы ничего не терялось молча. **v0.2.0** теперь собирает **цветной свет (RGBW/RGB/CCT)** и сущности **`climate`** (ключи сверены по докам HA KNX) и отделяет «шум» (резервы/логику), чтобы отчёт был про реальные устройства.

Есть демо-дом с HA-«мозгом» (циркадный свет, уставка климата из 8 факторов, логика присутствие/сезон/время, статистика) и дашборд на 5 экранов — реальные скриншоты на сайте. И любопытный результат: **из одного ТЗ (PDF)** инструмент сам спроектировал полную GA-структуру, совпавшую с профессиональной эталонной на **96%** (кейс по ссылке).

🔗 Демо + дашборд: https://nickoscope.github.io/nickol-knx-mcp/
💻 Репозиторий (MIT): https://github.com/NickoScope/nickol-knx-mcp · 📐 Кейс: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.ru.md

Это бета — буду рад, если люди с реальным KNX попробуют и сравнят сгенерированный YAML со своим ручным конфигом. Обратная связь очень приветствуется!

---

## 4) Reddit — r/homeassistant (and r/knx)

### EN — r/homeassistant
**Title:** Open-source AI assistant that reviews your KNX/ETS project and writes your Home Assistant config — now does colour lights + climate (read-only, never touches the bus)

Body:
KNX is the wired backbone a lot of us run under HA, but handing the ETS project off to Home Assistant is manual and easy to get wrong (missing status objects, inconsistent DPTs, hand-copying GAs).

**nickol-knx-mcp** is an MCP server that reads your `.knxproj` **read-only**, validates it (naming / DPT / command↔status from ETS Functions), and generates a HA KNX package + ETS exports + a review report. It has **zero bus libraries**, so it physically can't touch your installation. v0.2.0 now assembles **colour lights (RGBW/RGB/CCT)** and **`climate`** entities, and filters out reserve/logic "noise" so the report stays useful on real installs.

Full demo house with a circadian-lighting / 8-factor-climate "brain" + 5-view dashboard (real screenshots). Beta, looking for people to try it on **real** `.knxproj` files. Read-only, MIT.

🔗 Demo: https://nickoscope.github.io/nickol-knx-mcp/ · Repo: https://github.com/NickoScope/nickol-knx-mcp

### EN — r/knx (lead with the design result)
**Title:** [OSS] From a project spec PDF to a 96%-match KNX group-address structure — a design-time ETS assistant

Body:
I built an open-source **design-time** assistant for KNX (an MCP server, read-only on the `.knxproj`, **no bus access at all**). It validates naming / DPT consistency / missing status, pairs command↔status from **ETS Function roles**, classifies reserve/logic noise, and exports ETS-importable GA XML/CSV + a Home Assistant package.

The result I wanted to share: from a **42-page project spec (PDF) alone**, grounded in the **KNX Association standard**, it auto-designed a full group-address structure — **662 GA, 10 domains, 0 validation errors** — and vs a professional reference of the same flat: **96% structural match, 118 byte-identical names, in minutes**. The standard "skeleton" auto-designs to near-pro quality; the project-specific logic stays the engineer's craft.

Beta, MIT. Case study + repo: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.md · https://github.com/NickoScope/nickol-knx-mcp

### RU
**Заголовок:** Open-source AI-ассистент, который проверяет ваш KNX/ETS-проект и пишет конфиг Home Assistant — теперь с цветным светом и климатом (только чтение, к шине не подключается)

Текст:
KNX — проводная основа, которую многие держат под HA, но передавать ETS-проект в Home Assistant — ручная и легко ошибиться (нет статусов, рассогласованные DPT, перебивание GA руками).

**nickol-knx-mcp** — MCP-сервер: читает `.knxproj` **только на чтение**, проверяет (именование / DPT / команда↔статус по ETS Functions) и генерирует HA KNX-пакет + ETS-экспорты + отчёт. **Нет шинных библиотек** — физически не тронет инсталляцию. v0.2.0 собирает **цветной свет (RGBW/RGB/CCT)** и сущности **`climate`**, и отделяет «шум» (резервы/логику).

Есть демо-дом с «мозгом» (циркадный свет, климат из 8 факторов) и дашбордом на 5 экранов (реальные скрины). А ещё: **из одного ТЗ (PDF)** инструмент сам спроектировал GA-структуру, совпавшую с профессиональной эталонной на **96%** (кейс по ссылке). Бета, только чтение, MIT.

🔗 Демо: https://nickoscope.github.io/nickol-knx-mcp/ · Репо: https://github.com/NickoScope/nickol-knx-mcp · 📐 Кейс: https://github.com/NickoScope/nickol-knx-mcp/blob/main/docs/case-study.ru.md

### RU
**Заголовок:** Сделал open-source AI-ассистента, который проверяет ваш KNX/ETS-проект и пишет конфиг Home Assistant (только чтение, к шине не подключается)

Текст:
KNX — проводная основа, которую многие держат под HA, но проектировать его в ETS и передавать в Home Assistant — ручная и легко ошибиться (нет статусных объектов, рассогласованные DPT, перебивание GA руками).

Сделал **nickol-knx-mcp** — MCP-сервер: читает `.knxproj` **только на чтение**, проверяет (именование / DPT / команда↔статус по ETS Functions) и генерирует HA KNX-пакет + ETS-экспорты + отчёт. В нём **нет шинных библиотек**, так что физически не может тронуть инсталляцию.

Есть полный демо-дом с «мозгом» (циркадный свет, климат из 8 факторов) и дашбордом на 5 экранов (реальные скриншоты). Прогнал на публичных фикстурах ETS4/5/6 — нашёл свои же баги (исправлены + регресс-тесты).

Бета, ищу людей попробовать на **реальных** `.knxproj`. Только чтение, MIT.

🔗 Демо: https://nickoscope.github.io/nickol-knx-mcp/ · Репо: https://github.com/NickoScope/nickol-knx-mcp

---

## 5) Discord (HA / KNX / MCP servers) — short

### EN
Built an open-source **MCP server for KNX/ETS** 🏠⚡ It reads your `.knxproj` **read-only** (no bus access at all), checks naming/DPT/missing-status, pairs command↔status from ETS Functions, and generates your **Home Assistant** package + ETS exports + a review report. Full demo house + 5-view dashboard (real screenshots). Beta — would love it tested on real projects. Read-only, MIT.
Demo → https://nickoscope.github.io/nickol-knx-mcp/ · Repo → https://github.com/NickoScope/nickol-knx-mcp

### RU
Сделал open-source **MCP-сервер для KNX/ETS** 🏠⚡ Читает `.knxproj` **только на чтение** (доступа к шине нет), проверяет именование/DPT/статусы, паря команда↔статус по ETS Functions, и генерирует пакет **Home Assistant** + ETS-экспорты + отчёт. Полный демо-дом + дашборд на 5 экранов (реальные скрины). Бета — буду рад тестам на реальных проектах. Только чтение, MIT.
Демо → https://nickoscope.github.io/nickol-knx-mcp/ · Репо → https://github.com/NickoScope/nickol-knx-mcp

---

## 6) Telegram (RU KNX / Умный дом / Home Assistant чаты)

### RU
Привет! Сделал открытый **MCP-сервер для KNX/ETS** 🏠⚡

Он читает `.knxproj` **только на чтение** (к шине не подключается вообще), проверяет именование / DPT / отсутствующие статусы, паря команда↔статус по ролям ETS Functions, и генерирует конфиг **Home Assistant** + ETS-экспорты + отчёт «до импорта».

Прогнал на публичных проектах ETS 4/5/6 — нашёл свои же баги, поправил. Есть полный демо-дом (239 адресов) с «мозгом» (циркадный свет, климат из 8 факторов, статистика) и дашбордом — реальные скриншоты на сайте.

Бета, ищу тех, кто прогонит на реальном `.knxproj` (безопасно — только чтение). MIT.

🔗 Демо: https://nickoscope.github.io/nickol-knx-mcp/
💻 Репозиторий: https://github.com/NickoScope/nickol-knx-mcp

### EN (if the chat is mixed-language)
Made an open-source **MCP server for KNX/ETS** 🏠⚡ Reads `.knxproj` read-only (no bus access), validates naming/DPT/missing-status, pairs command↔status from ETS Functions, generates a Home Assistant package + ETS exports + a review report. Full demo house + dashboard (real screenshots). Beta, looking for real-project testers. MIT.
Demo: https://nickoscope.github.io/nickol-knx-mcp/ · Repo: https://github.com/NickoScope/nickol-knx-mcp

---

## 7) awesome-mcp-servers (catalog PR — EN only)

**List entry (Markdown bullet):**
```markdown
- [NickoScope/nickol-knx-mcp](https://github.com/NickoScope/nickol-knx-mcp) 🐍 🏠 - Design-time KNX/ETS6 assistant: parse `.knxproj` (read-only, no bus access), validate DPT/naming/command-status pairing, generate Home Assistant YAML + ETS XML/CSV exports.
```
*(Place under a Home Automation / IoT category; match the list's emoji legend — 🐍 = Python, 🏠 = local/home.)*

**PR title:** Add nickol-knx-mcp (design-time KNX/ETS6 → Home Assistant)

**PR description:**
> Adds **nickol-knx-mcp**, an MCP server for design-time KNX/ETS6 work: it parses `.knxproj` read-only (no bus/networking access), validates naming/DPT/command-status pairing, and generates Home Assistant packages + ETS-importable exports. MIT, Python 3.10+, has tests/CI and a full demo project. Repo: https://github.com/NickoScope/nickol-knx-mcp

Target lists (open a PR to each): `punkpeye/awesome-mcp-servers`, `appcypher/awesome-mcp-servers`, and the community list linked from `modelcontextprotocol/servers`.
