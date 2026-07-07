# HA Git Backup — двухконтурная система (русская версия; каноническая — [SKILL.md](SKILL.md))

Философия: **git даёт историю, бэкап даёт восстановление. Это разные задачи — их решают разные
контуры.** Проекты типа GithubConfigSync смешивают их и реализуют git поверх Contents API — мы
используем настоящий git.

## Архитектура

```
КОНТУР 1: ИСТОРИЯ КОНФИГА (что изменилось и когда)
/config (git repo) ──deploy key──▶ GitHub private repo (ha-config)
  ├── триггеры: daily 03:30 / pre-update / кнопка / рестарт HA
  ├── защита секретов: .gitignore → pre-commit scan → age-зеркало
  └── коммит: "[trigger] N files | HA 2026.7.1" + список файлов

КОНТУР 2: ВОССТАНОВЛЕНИЕ (полное состояние, включая .storage)
HA native backup (.tar) ──age──▶ GitHub Releases (ha-config)
  ├── расписание: еженедельно + перед обновлениями
  ├── ротация: 8 релизов
  └── restore drill: 1-е число месяца (обязательный)
```

Правило 3-2-1: конфиг живёт (1) на хосте HA, (2) в git-репо GitHub, (3) полный тарбол в
Releases + локальный NAS при наличии.

## ЖЕЛЕЗНЫЕ ПРАВИЛА

1. **Deploy key, не PAT.** Fine-grained доступ на ЗАПИСЬ в ОДИН репозиторий. Classic-токен со
   scope `repo` = доступ ко всем приватным репо → запрещён.
2. **Секрет в diff = коммит блокируется.** Pre-commit hook вызывает `secret_scan.sh`. Обход
   через `--no-verify` — только осознанно и с записью причины в лог.
3. **`.storage/` НЕ идёт в git** (auth, токены), кроме whitelist `lovelace*` — дашборды.
   Полное `.storage` живёт только в шифрованном тарболе Контура 2.
4. **Бэкап без restore drill — не бэкап.** Раз в месяц: скачать релиз → `age -d` → `tar -t` →
   проверить наличие `.storage/core.config_entries`.
5. **Не переписывать скрипты с нуля.** Логика (lock, retry, notify, ротация) уже в `scripts/`
   — читать и использовать их.

## Быстрый старт (новая установка)

1. Создать приватный репо `ha-config` на GitHub (пустой).
2. Прочитать `references/setup.md` — там пошагово: deploy key, установка через SSH add-on.
3. Запустить `scripts/install.sh` внутри HA — он делает git init, .gitignore, hook, remote,
   первый dry-run.
4. Добавить `assets/configuration_snippet.yaml` в configuration.yaml и `assets/automations.yaml`
   в автоматизации. **Нужен ПОЛНЫЙ перезапуск HA** (quick-reload не грузит
   `shell_command`/`command_line`).
5. Контур 2: `scripts/backup_offsite.sh` требует fine-grained PAT + age-ключ.
   См. `references/setup.md` §4.
6. Провести первый restore drill СРАЗУ — до того, как система понадобится.

## Карта симптомов → действия

| Симптом | Действие |
|---|---|
| «Вчера работало, сегодня нет» | `git log --oneline -10`, `git diff HEAD~1` в /config |
| Сломал YAML, HA не стартует | `git checkout -- <file>` или `git reset --hard <good_sha>`, рестарт |
| Утёк секрет в репо | `references/incident-secret-leak.md` — ротация секрета ПЕРВОЙ |
| Push молчит/падает | `/config/.git-sync/log`; типовое: deploy key read-only, протух known_hosts |
| Переезд на новое железо | `scripts/restore.sh` — тарбол Контура 2, НЕ git-репо (в git нет .storage) |
| Sync-сенсор = error | Смотреть лог; автоматизация шлёт persistent_notification |
| Репо распух | Бинарники (db, tar) в .gitignore; история чистится `git gc` |

## УРОКИ (зафиксированы, не повторять)

- **УРОК-01**: GithubConfigSync-подход (файлы по одному через Contents API) = коммит на файл,
  rate limits, снапшоты-дубли. Настоящий git решает всё это бесплатно.
- **УРОК-02**: .gitignore — НЕ защита. Файл, добавленный до правила, продолжает трекаться.
  Отсюда обязательный pre-commit scan.
- **УРОК-03**: git-репо конфига ≠ бэкап: без .storage восстановление даёт голый HA без entity
  registry, авторизаций и дашбордов из UI.
- **УРОК-04**: restore drill в спокойное время стоит 10 минут. Первое восстановление во время
  аварии без drill стоит вечер и нервы.
- **УРОК-05**: BusyBox-grep принимает паттерн, начинающийся с `-`, за опцию — паттерны сканера
  передавать только как `grep -E -e "$pattern"`. Сканер молча пропускал проверку приватных
  ключей, пока это не поймал тест с подсадной уткой. Проверяй сканер подсадными секретами.
