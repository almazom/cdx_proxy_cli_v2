# Headless Hook Arithmetic Train: Пошаговая Проверка

Это короткая и практическая инструкция.
Она повторяет именно тот сценарий, который уже успешно прошёл локально.

## Что именно проверяем

Мы хотим доказать сразу 4 вещи:

1. headless `codex_wp exec` умеет сам делать `resume` по stop hook;
2. все 10 шагов идут в одной и той же Codex session;
3. ответ на каждом шаге увеличивается на `+1`;
4. Telegram уведомления собираются в один поезд с `train_id`.

## Что уже успешно прошло

Сценарий уже был успешно проверен локально.
В репо оставляем не реальные live id, а безопасный шаблон того, что нужно увидеть:

- `run_dir`: `/tmp/codex-hook-arith-live-XXXXXX`
- `session_id`: `<full-session-id>`
- `session_file`: `~/.codex/sessions/...<full-session-id>.jsonl`
- `Telegram ids`: `<10 linked message ids>`
- `train_id`: `TRAIN-YYYYMMDD-HHMMSS-ABCD`
- `assistant numbers`: `2 3 4 5 6 7 8 9 10 11`

## Важно до запуска

Для 10 шагов нельзя писать "ответь только цифрой".
На последних шагах ответ уже двузначный.

Нужно писать:

```text
ответь только числом
```

## Шаг 1. Создай временный проект

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2
RUN_DIR="$(mktemp -d /tmp/codex-hook-arith-live-XXXXXX)"
PILOT_DIR="$RUN_DIR/project"
mkdir -p "$PILOT_DIR"
printf 'RUN_DIR=%s\nPILOT_DIR=%s\n' "$RUN_DIR" "$PILOT_DIR"
```

## Шаг 2. Запусти headless train

```bash
cd /home/pets/TOOLS/cdx_proxy_cli_v2

bin/codex_wp exec --json --skip-git-repo-check -C "$PILOT_DIR" \
  "Ответь только числом. Посчитай 1+1 и выведи только результат." \
  --hook stop \
  --hook-prompt "Прибавь к предыдущему результату еще 1 и ответь только числом." \
  --hook-times 10 \
  --hook-target @almazom | tee "$RUN_DIR/codex_stdout.jsonl"
```

Что ожидаем в stdout:

- сначала `thread.started`
- потом `2`
- потом `3`
- потом `4`
- ...
- в конце `11`

## Шаг 3. Найди session_id

Самый простой способ:

```bash
python3 - <<'PY'
import json
from pathlib import Path
import os

stdout_file = Path(os.environ["RUN_DIR"]) / "codex_stdout.jsonl"
for line in stdout_file.read_text(encoding="utf-8").splitlines():
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    if obj.get("type") == "thread.started":
        print(obj.get("thread_id"))
        break
PY
```

Сохрани результат:

```bash
SESSION_ID="<подставь сюда найденный id>"
export SESSION_ID
```

## Шаг 4. Найди session file

```bash
SESSION_FILE="$(find ~/.codex/sessions -type f -name "*${SESSION_ID}*.jsonl" | tail -n 1)"
export SESSION_FILE
printf 'SESSION_FILE=%s\n' "$SESSION_FILE"
```

Ожидаем:

- найден ровно один `.jsonl`
- в имени файла есть тот же `SESSION_ID`

## Шаг 5. Проверь same-session и арифметику

```bash
python3 - <<'PY'
import json
import re
import os
from pathlib import Path

session_file = Path(os.environ["SESSION_FILE"])
expected_session_id = os.environ["SESSION_ID"]

meta_id = None
turns = 0
numbers = []

for line in session_file.read_text(encoding="utf-8").splitlines():
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue

    if obj.get("type") == "session_meta":
        payload = obj.get("payload", {})
        if isinstance(payload, dict):
            meta_id = payload.get("id")

    if obj.get("type") == "turn_context":
        turns += 1

    if obj.get("type") != "response_item":
        continue

    payload = obj.get("payload", {})
    if not isinstance(payload, dict):
        continue
    if payload.get("type") != "message":
        continue
    if payload.get("role") != "assistant":
        continue

    content = payload.get("content", [])
    if not isinstance(content, list):
        continue

    text = " ".join(
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("type") == "output_text"
    )

    match = re.search(r"\b\d+\b", text)
    if match:
        numbers.append(int(match.group(0)))

print("meta_id:", meta_id)
print("expected_session_id:", expected_session_id)
print("turns:", turns)
print("numbers:", numbers)
print("same_session:", meta_id == expected_session_id)
print("strict_increment:", all(b == a + 1 for a, b in zip(numbers, numbers[1:])))
PY
```

Ожидаем:

- `turns: 10`
- `numbers: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]`
- `same_session: True`
- `strict_increment: True`

## Шаг 6. Проверь Telegram поезд

```bash
/home/pets/zoo/cc_chanels_telegram/TOOLS/telega fetch \
  --profile almazomkz --json --wait 3 --limit 20 @almazom
```

Что искать:

- все сообщения с твоим `SESSION_ID`
- один и тот же `train_id`
- `wagon 1/10`, `wagon 2/10`, ..., `wagon 10/10`
- полный `session_id`, не обрезанный

Пример удачного train header:

```text
🚆🪪🔟 TRAIN-YYYYMMDD-HHMMSS-ABCD
🚃 wagon 4/10
📁 cdx_proxy_cli_v2
🔄 <full-session-id> · #004
```

## Шаг 7. Что считать успехом

Сценарий успешен, если одновременно выполнены все пункты:

- в stdout одна и та же session
- в `.jsonl` один и тот же `meta_id`
- `turn_context == 10`
- числа идут строго `2..11`
- в Telegram 10 связанных уведомлений
- у уведомлений один и тот же `train_id`
- `wagon X/10` идёт от `1/10` до `10/10`
- `session_id` полный

## Короткая диагностика, если что-то сломалось

### Если нет train в Telegram

- проверь, что fetch идёт именно через `--profile almazomkz`
- не используй `default`, иначе можно смотреть не в тот маршрут

### Если numbers пустые

- читай `response_item`
- не полагайся на `event_msg`, там в реальной session часто `content=None`

### Если ответы перестали увеличиваться

- значит resume потерял контекст
- смотри:
  - stdout `thread_id`
  - `session_meta.id`
  - extracted numbers

## Текущий статус

На момент подготовки этой инструкции сценарий уже прошёл успешно.
