# IMPLEMENTATION_PLAN

## Быстрый reproduce-first runbook

Ниже не теория, а будущий канонический способ воспроизведения.
Сначала делаем именно так, потом уже улучшаем код и инструкции.

### 1. Подготовить временный пилотный проект

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
PILOT_DIR="$(mktemp -d /tmp/codex-hook-arith-train-XXXXXX)"
printf '%s\n' "$PILOT_DIR"
```

### 2. Запустить headless arithmetic train

Важно: для 10 шагов нельзя просить "ответь только цифрой".
На 10-м шаге ответ уже будет двузначным.
Правильная формулировка: "ответь только числом".

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp exec --json --skip-git-repo-check -C "$PILOT_DIR" \
  "Ответь только числом. Посчитай 1+1 и выведи только результат." \
  --hook stop \
  --hook-prompt "Прибавь к предыдущему результату еще 1 и ответь только числом." \
  --hook-times 10 \
  --hook-target @almazom
```

### 3. Что должно получиться

- В stdout headless run должен идти один и тот же `thread_id`.
- В Telegram должен идти один "поезд" из 10 уведомлений.
- В каждом следующем ответе число должно увеличиваться на 1.
- В `~/.codex/sessions/...jsonl` должна быть одна и та же сессия с 10 turn.

### 4. Что проверить руками сразу после прогона

```bash
SESSION_ID="<подставить из уведомления или stdout>"

find ~/.codex/sessions -type f -name "*${SESSION_ID}*.jsonl"

/home/pets/zoo/cc_chanels_telegram/TOOLS/telega fetch \
  --profile almazomkz --json --wait 3 --limit 20 @almazom
```

### 5. Что проверить полуавтоматом

```bash
SESSION_FILE="$(find ~/.codex/sessions -type f -name "*${SESSION_ID}*.jsonl" | tail -n 1)"

python3 - <<'PY'
import json
import re
from pathlib import Path
import os

session_file = Path(os.environ["SESSION_FILE"])
sid = os.environ["SESSION_ID"]
nums = []
turns = 0
meta_id = None
for line in session_file.read_text(encoding="utf-8").splitlines():
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    if obj.get("type") == "session_meta":
        meta_id = obj.get("payload", {}).get("id")
    if obj.get("type") == "turn_context":
        turns += 1
    if obj.get("type") == "response_item":
        payload = obj.get("payload", {})
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            content = payload.get("content", [])
            if isinstance(content, list):
                text = " ".join(
                    item.get("text", "").strip()
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "output_text"
                )
                m = re.search(r"\b\d+\b", text)
                if m:
                    nums.append(int(m.group(0)))

print("meta_id:", meta_id)
print("expected_session_id:", sid)
print("turns:", turns)
print("assistant_numbers:", nums)
print("same_session:", meta_id == sid)
print("strict_increment:", all(b == a + 1 for a, b in zip(nums, nums[1:])))
PY
```

## Summary

Нужно закончить и проверить headless arithmetic train для `codex_wp` так, чтобы:

1. headless `exec` делал 10 последовательных `resume` в одной сессии;
2. ответы образовывали арифметическую цепочку `2, 3, 4, ...`;
3. уведомления собирались в понятный "поезд" с отдельным `train_id`;
4. ручная русская инструкция позволяла повторить всё в терминале без чтения чата.

## Что уже есть

- Headless hook loop уже реализован в [bin/codex_wp](/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp).
- Интеграционные headless тесты уже есть в [tests/integration/test_codex_wp_green_path.py](/home/pets/TOOLS/cdx_proxy_cli_v2/tests/integration/test_codex_wp_green_path.py).
- Уже проверено живыми прогонами, что один `session_id` может переживать 2 и 10 headless resume.
- Уже исправлена одна хрупкость JSON parser helper'ов: non-dict JSON больше не должен ломать loop.

## Новые продуктовые требования из текущего запроса

### A. Arithmetic train BDD scenario

- Initial prompt:
  считать `1+1`
- Hook prompt:
  прибавить к предыдущему результату ещё `1`
- Длина поезда:
  `10`
- Режим:
  только headless `exec`

### B. Новый train-level observability слой

Нужно отделить:

- `train_id`
  общий id всей серии уведомлений
- `wagon_index/total`
  место текущего уведомления в поезде
- `session_id`
  полный id codex session, не обрезать

### C. Новый CLI alias

- `--hook-times`
  новый более понятный флаг
- `--hook-time`
  оставить как legacy alias ради обратной совместимости

Решение:

- парсить оба флага в одну переменную;
- help и docs делать через `--hook-times`;
- старые тесты и старые вызовы не ломать.

## Notification design

### Обязательные поля

Каждое уведомление headless train должно содержать:

```text
🟡/🔴 статус

🚆🪪🔟 TRAIN-...
📦 wagon 1/10
📁 <project-name>
🔄 <full-session-id> · #001

📊 1/10  █░░░░░░░░░

💬 <assistant-result>
```

### Почему train_id нельзя смешивать с session_id

- `session_id` нужен для `exec resume`
- `session_id` нужен для поиска `.jsonl`
- `train_id` нужен только для человека и Telegram stream grouping
- несколько train могут идти параллельно из разных проектов, а человек должен глазами различать поезд

### Формат train marker

Рекомендуемый постоянный префикс:

```text
🚆🪪🔟
```

Рекомендуемый id:

```text
TRAIN-YYYYMMDD-HHMMSS-<short-rand>
```

Пример:

```text
🚆🪪🔟 TRAIN-YYYYMMDD-HHMMSS-ABCD
📦 wagon 4/10
📁 cdx_proxy_cli_v2
🔄 <full-session-id> · #004
```

## Parallel verifier role

Во время live arithmetic train нужен отдельный параллельный verifier.

Его задачи:

1. читать `stdout` headless run;
2. найти `session_id`;
3. найти session file;
4. вытащить последовательность чисел из assistant events;
5. доказать:
   - same session
   - strict increment by 1
   - ровно 10 вагонов

На практике это может быть:

- spawned subagent в read-only режиме;
- или локальный python verifier после завершения run;
- но в live-прогоне лучше использовать именно отдельный subagent.

## Implementation phases

### Phase 1. CLI clarity

Файлы:

- [bin/codex_wp](/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp)
- [tests/integration/test_codex_wp_green_path.py](/home/pets/TOOLS/cdx_proxy_cli_v2/tests/integration/test_codex_wp_green_path.py)

Сделать:

1. добавить `--hook-times` alias;
2. оставить `--hook-time` рабочим;
3. обновить `--help`;
4. покрыть alias интеграционным тестом.

### Phase 2. Notification train identity

Файлы:

- [bin/codex_wp](/home/pets/TOOLS/cdx_proxy_cli_v2/bin/codex_wp)
- [tests/integration/test_codex_wp_green_path.py](/home/pets/TOOLS/cdx_proxy_cli_v2/tests/integration/test_codex_wp_green_path.py)

Сделать:

1. генерировать `train_id` один раз на весь headless loop;
2. добавить в каждое уведомление header:
   - `🚆🪪🔟 TRAIN-...`
   - `📦 wagon X/N`
3. не трогать полный `session_id`;
4. проверить обычный и error path.

### Phase 3. Arithmetic train live scenario

Файлы:

- временный pilot dir в `/tmp`
- session file в `~/.codex/sessions/...`
- Telegram fetch output

Сделать:

1. запустить live headless train на 10 вагонов;
2. параллельно запустить verifier;
3. сохранить:
   - stdout
   - session file path
   - telega fetch JSON
   - short verify report

### Phase 4. Manual Russian handoff

Файлы:

- repo-root [IMPLEMENTATION_PLAN.md](/home/pets/TOOLS/cdx_proxy_cli_v2/IMPLEMENTATION_PLAN.md)
- отдельная reproduce note / report artifact

Сделать:

1. подготовить очень подробную русскую инструкцию;
2. отправить её через `notify-me`;
3. приложить:
   - точную команду запуска
   - как найти `session_id`
   - как найти `.jsonl`
   - как проверить арифметическую цепочку
   - как проверить поезд уведомлений

## Acceptance criteria

### Core behavior

- Headless run с `--hook-times 10` создаёт 10 последовательных вагонов.
- Все 10 вагонов используют один и тот же `session_id`.
- Assistant results образуют строгую арифметическую цепочку с шагом `+1`.

### Notification behavior

- Во всех уведомлениях есть `train_id`.
- Во всех уведомлениях есть `wagon X/N`.
- Полный `session_id` нигде не обрезается.
- Train marker использует фиксированный 3-emoji префикс.

### Reproduce behavior

- Пользователь может повторить всё одной пошаговой инструкцией в терминале.
- После повтора он может увидеть те же доказательства в:
  - stdout
  - `.jsonl`
  - Telegram

## Risks

### R1. "Только цифрой" ломается на 10-м шаге

Смягчение:

- везде заменить на "ответь только числом"

### R2. Первый intent block может не всегда успеть к первому уведомлению

Смягчение:

- не считать это blocker для arithmetic train;
- отдельно пометить как live timing caveat

### R3. Codex может ответить не только числом

Смягчение:

- использовать очень жёсткий prompt;
- verifier проверяет именно extract integer sequence

### R4. Одновременные поезда из 3 проектов визуально путаются

Смягчение:

- отдельный `train_id`
- фиксированный 3-emoji marker
- явный `wagon X/N`
- project line оставлять сразу под train header

## Verification commands

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
pytest -q tests/integration/test_codex_wp_green_path.py
make test-integration-codex-wp
make test-e2e
```

## Manual checklist

- [ ] Есть alias `--hook-times`
- [ ] Train header виден в уведомлении
- [ ] `session_id` полный
- [ ] 10 wagon notification train виден как связанная цепочка
- [ ] `.jsonl` один и тот же
- [ ] arithmetic increments by `+1`
- [ ] русская reproduce-инструкция готова для отправки через notify-me
