> 🌍 **English version:** [README.md](README.md) · Русская версия ниже.

# nickol-knx-mcp

**Design-time ассистент KNX/ETS6 в виде MCP-сервера.**
Читает `.knxproj` и **валидирует** его (именование · DPT и sub-DPT · команда↔статус · KNX Secure · Matter-готовность), **чинит** (предлагает конкретные фиксы — выводит DPT, синтезирует недостающие status-адреса), **раскладывает устройства** на рецепты групповых адресов, **диффит** две версии проекта, **грейдит** полноту, и **генерирует** Home Assistant YAML, ETS-импортируемые экспорты (XML/CSV), **пакет сдачи** (as-built), протокол приёмки и KNX IoT-экспорт — **никогда не подключаясь к живой шине KNX.**

[![nickol-knx-mcp MCP server](https://glama.ai/mcp/servers/NickoScope/nickol-knx-mcp/badges/score.svg)](https://glama.ai/mcp/servers/NickoScope/nickol-knx-mcp)
[![Кейс](https://img.shields.io/badge/📐_кейс-ТЗ_PDF_→_KNX_(96%25)-0b3d2e)](docs/case-study.ru.md)

> ⚠️ **Статус: BETA.** Сервис проверен на синтетическом проекте (16 GA) и проходит end-to-end тест, но **на реальных `.knxproj` пока тестировался ограниченно**. Нужны тестировщики — см. [CONTRIBUTING.md](CONTRIBUTING.md).
>
> 💬 **[Присоединяйтесь к обсуждению →](https://github.com/NickoScope/nickol-knx-mcp/discussions/1)** — вопросы, идеи, и что инструмент нашёл на вашем проекте.

---

<p align="center">
  <a href="https://nickoscope.github.io/nickol-knx-mcp/">
    <img src="docs/assets/banner.svg" alt="nickol-knx-mcp — живое интерактивное демо и дашборд" width="100%">
  </a>
</p>

<h3 align="center">🎬 <a href="https://nickoscope.github.io/nickol-knx-mcp/">Живое интерактивное демо и дашборд&nbsp;→</a></h3>

> **Новое — целый демо-дом.** В [`examples/demo-home`](examples/demo-home) лежит синтетический проект
> на **239 GA / 47 Functions**, сгенерированные тулом отчёт + конфиг Home Assistant + ETS-экспорт, и полноценный
> **«мозг»** умного дома — циркадный свет, **уставка климата из 8 факторов**, машина режимов
> присутствие/сезон/время и статистика — с **дашбордом на 5 страниц**. Всё на
> **[живом сайте&nbsp;↗](https://nickoscope.github.io/nickol-knx-mcp/)**.

---

## 🖥️ Дашборд — вживую в Home Assistant

Реальные скриншоты из живого Home Assistant с демо-домом. Видны собранные инструментом сущности:
**цветной свет RGBW / RGB / CCT**, **6 климат-зон тёплого пола** (уставка, режим, % клапана), **циркадная**
кривая освещения и **вычисляемая** уставка климата — не заданная вручную.

<p align="center">
  <img src="docs/assets/screenshots/overview.png" alt="Overview" width="78%">
</p>

| Climate | Lighting |
|:---:|:---:|
| [<img src="docs/assets/screenshots/climate.png" width="100%">](docs/assets/screenshots/climate.png) | [<img src="docs/assets/screenshots/lighting.png" width="100%">](docs/assets/screenshots/lighting.png) |
| **Energy & stats** | **Presence** |
| [<img src="docs/assets/screenshots/energy.png" width="100%">](docs/assets/screenshots/energy.png) | [<img src="docs/assets/screenshots/presence.png" width="100%">](docs/assets/screenshots/presence.png) |

▶ **[Открыть интерактивно на сайте →](https://nickoscope.github.io/nickol-knx-mcp/)** · конфиг в [`examples/demo-home/ha-brain`](examples/demo-home/ha-brain)

---

## 1. Зачем это и где оно в общей схеме

На июнь 2026 готового официального **ETS6 ↔ Claude / MCP** инструмента не существует.
KNX Community в мае 2026 прямо просит такую интеграцию (изменение проектов, добавление/переименование устройств и group addresses через Claude/CLI). Этот пакет закрывает именно **design-time** слой — самый недостающий.

Полная рекомендованная схема — четыре слоя, и собирать с нуля нужно только один:

| Слой | Назначение | Что использовать | Собирать? |
|------|-----------|------------------|-----------|
| 1. Live | состояния, управление, отладка автоматизаций живого дома | **официальный Home Assistant MCP Server** + KNX (XKNX) integration | нет, уже есть |
| 2. **Design-time** | парсинг `.knxproj`, проверка DPT/именования/статусов + классификация назначения GA (снижение шума), генерация HA YAML (сборка цветного света + климата) и ETS XML/CSV | **`nickol-knx-mcp` (этот пакет)** | **ДА — это и есть пробел** |
| 3. Files + Git | YAML/CSV/XML, версионирование схемы адресов | стандартные filesystem + git MCP | нет, уже есть |
| 4. Skill | правила проектирования (структура GA, naming, DPT, сцены) | `CLAUDE.md` из этого пакета | нет, готов |

> **Принцип безопасности:** слой 2 (этот сервер) **физически не умеет** подключаться к шине. У него нет ни одной сетевой/bus-зависимости — только чтение `.knxproj` и запись файлов в изолированный workspace. Требование «никогда не писать в живую шину» выполнено **структурно**, а не «честным словом». Любое реальное взаимодействие с домом идёт только через слой 1 (Home Assistant).

---

## 2. Что умеет сервер

- **Парсит** запароленные ETS5/ETS6 `.knxproj` через `xknxproject` (3.9.x).
- **Извлекает** group addresses, DPT, устройства, топологию, описания, функции (Functions).
- **Классифицирует** каждый GA: категория (lighting / shutter / hvac / sensor / scene / energy / diagnostics) и вид (command / status / sensor) — по DPT + многоязычным (EN/DE/RU) ключевым словам в имени.
- **Проверяет именование** по 3-уровневой структуре и регэкспу.
- **Находит отсутствующие статусные адреса** — приоритетно по ролям из ETS Functions, как fallback — по парности имён (token-overlap).
- **Ловит проблемы DPT**: отсутствующий DPT, рассогласование DPT между Communication Object и GA, одинаковое имя с разными DPT.
- **Классифицирует назначение GA, чтобы убрать шум** — каждый адрес помечается `functional` / `reserve` / `logic` / `scratch`. Намеренно нефункциональные GA (запасные «Резерв», внутренние логические сигналы, мусорные остатки) исключаются из проверок ошибок и missing-status, чтобы отчёт не «кричал волки» на реальных проектах (на боевом 685-GA Zennio: ложных ошибок 29 → 6).
- **Генерирует Home Assistant KNX YAML** — категорийно, консервативно: обложки → **цветной / диммируемый свет** → выключатели → **климат** → датчики. Многоадресные сущности **собираются**: свет — вкл/выкл + яркость + **RGBW / RGB / цветовая температура** + их статусы; `climate` — текущая t°, статус уставки, режим (operation/controller) и % клапана (эмитится только при наличии обязательных HA-ключей, иначе → в `review`). Неоднозначные элементы уходят в `review`, а не угадываются вслепую.
- **Генерирует ETS-импортируемые** group addresses: **XML** (схема `knx.org/xml/ga-export/01`) и **CSV** (родная раскладка ETS).
- **Пишет Markdown-отчёт** (инвентаризация + находки 🔴🟡🔵 + превью HA-маппинга + следующие шаги).

Все записи идут только в каталог workspace (`NICKOL_KNX_WORKSPACE`, по умолчанию `./knx-workspace`); запись за его пределы отклоняется.

---

## 3. Установка

Требуется Python 3.10+.

```bash
git clone https://github.com/NickoScope/nickol-knx-mcp.git
cd nickol-knx-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Зависимости: `mcp>=1.10`, `xknxproject>=3.8`, `PyYAML>=6.0`.

> Если на Debian/Ubuntu система ругается на externally-managed окружение — используйте venv, либо `pip install -e . --break-system-packages`. При конфликте `PyJWT` помогает `pip install mcp --ignore-installed PyJWT`.

Проверка:

```bash
python tests/test_pipeline.py     # синтетический проект из 16 GA, end-to-end smoke test
nickol-knx-mcp                    # запустить MCP-сервер (stdio)
```

---

## 4. Подключение к Claude

### Claude Desktop

`examples/claude_desktop_config.json` уже сводит вместе nickol-knx + filesystem + git + home-assistant. Минимальный фрагмент:

```json
{
  "mcpServers": {
    "nickol-knx": {
      "command": "nickol-knx-mcp",
      "env": { "NICKOL_KNX_WORKSPACE": "/path/to/your/knx-workspace" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add nickol-knx -e NICKOL_KNX_WORKSPACE="$HOME/knx-workspace" -- /abs/path/to/.venv/bin/nickol-knx-mcp
```

Положите `CLAUDE.md` в корень проекта — он работает как ETS Assistant skill (правила проектирования, safety-rules, 3-уровневая структура GA, command/status, DPT-дисциплина, naming, KNX Secure keyring, рабочий процесс).

---

## 5. Инструменты MCP (24)

**Чтение:** `load_project` · `list_group_addresses` · `get_devices` · `get_topology`

**Валидация:** `check_naming` · `check_missing_status` · `check_dpt` (+ **sub-DPT** проверка) · `check_secure` (KNX Secure posture + keyring-чеклист) · `check_matter` (Matter-готовность) · `check_energy` (энергодомен) · `analyze_all`

**Починка и дизайн:** `suggest_repairs` (**предлагает фиксы, а не только флагает**) · `suggest_names` · `decompose_device` (устройство → рецепт декомпозиции) · `list_device_recipes` (device-library: Zennio + ABB) · `grade_completeness` (скелет vs as-built) · `diff_projects` (семантический дифф двух версий)

**Генерация:** `generate_ha_package` (цвет + климат + expose) · `generate_ets_group_addresses` · `generate_handover_pack` (пакет сдачи) · `generate_test_protocol` (протокол приёмки) · `generate_knx_iot` (Turtle/RDF) · `project_report` · `workspace_info`

<details><summary>Полная таблица (сигнатуры)</summary>

| Инструмент | Назначение |
|-----------|-----------|
| `load_project(path, password?, language?)` | загрузить и распарсить `.knxproj` (read-only), закэшировать |
| `list_group_addresses(category?, kind?)` | список GA с классификацией, фильтры |
| `get_devices()` | устройства + их communication objects |
| `get_topology()` | топология (areas / lines / devices) |
| `check_naming(name_regex?)` | проверка именования/структуры |
| `check_missing_status()` | актуаторы без статусного объекта |
| `check_dpt()` | отсутствующие/несогласованные DPT + sub-DPT |
| `check_secure()` | KNX Data Secure posture + keyring-чеклист |
| `check_matter()` | Matter-готовность функций |
| `check_energy()` | метеринг/энергодомен |
| `analyze_all(name_regex?)` | все проверки разом |
| `suggest_repairs()` | предложить фиксы для находок |
| `suggest_names()` | гигиена именования |
| `decompose_device(order_number, channels?)` | устройство → рецепт декомпозиции GA |
| `list_device_recipes()` | встроенная device-library |
| `grade_completeness()` | грейд полноты (скелет vs as-built) |
| `diff_projects(path_a, path_b, …)` | семантический дифф двух `.knxproj` |
| `generate_ha_package(output_path?)` | HA KNX YAML + список review |
| `generate_ets_group_addresses(fmt="xml"\|"csv", output_path?)` | ETS-импортируемые GA |
| `generate_handover_pack(output_dir?)` | пакет сдачи (as-built) |
| `generate_test_protocol(output_path?)` | протокол приёмки |
| `generate_knx_iot(output_path?)` | KNX IoT (Turtle/RDF) |
| `project_report(output_path?, name_regex?)` | Markdown-отчёт |
| `workspace_info()` | путь и содержимое workspace |

</details>

---

## 6. Типовой рабочий процесс

1. `load_project` → указать `.knxproj` (+ пароль, если запаролен).
2. `analyze_all` или `project_report` → прочитать находки, **сначала ревью человеком**.
3. Исправить именование/DPT/статусы в ETS (импортом сгенерированных GA или вручную).
4. `generate_ets_group_addresses(fmt="xml")` → импортировать в ETS как недостающие GA.
5. `generate_ha_package` → положить YAML в Home Assistant; разобрать `review`-элементы руками.
6. Всё (экспорт `.knxproj`, HA-конфиги, схема адресов) держать в Git.
7. Живой дом — только через Home Assistant MCP (слой 1).

---

## 7. Ограничения (честно)

- Классификация command/status и категорий — **эвристика** (DPT + имена + ETS Functions). На «грязных» проектах без Functions и с нестандартными именами возможны пропуски/ложные срабатывания — поэтому отчёт всегда для ревью человеком.
- DPT 5.001 структурно неоднозначен (яркость vs позиция) — разводится по ключевым словам; при нестандартном нейминге проверяйте вручную.
- Генератор HA консервативен: лучше отдать элемент в review, чем сгенерировать неверную сущность.
- Сервер не пишет в шину и не подключается к ETS напрямую — обмен с ETS только через файловый импорт/экспорт GA.
- **Тест пока только на синтетическом проекте.** Реальные `.knxproj` очень разнообразны — поэтому и нужны тестировщики.

---

## 8. Структура пакета

```
nickol-knx-mcp/
├── nickol_knx_mcp/
│   ├── dpt_map.py        # DPT → категория/вид/HA-платформа/value_type
│   ├── project.py        # ЕДИНСТВЕННЫЙ модуль, читающий .knxproj (read-only)
│   ├── pairing.py        # парность command↔status по токенам имени
│   ├── analyze.py        # naming / missing-status / DPT проверки
│   ├── generate_ha.py    # генерация HA KNX YAML
│   ├── generate_ets.py   # генерация ETS XML + CSV
│   ├── report.py         # Markdown-отчёт
│   └── server.py         # FastMCP сервер, 24 инструмента, confined writes
├── tests/test_pipeline.py
├── examples/claude_desktop_config.json
├── CLAUDE.md             # ETS Assistant skill / playbook
├── pyproject.toml
└── README.md
```

---

## Лицензия

[MIT](LICENSE) © 2026 Nikolay Miroshnichenko
