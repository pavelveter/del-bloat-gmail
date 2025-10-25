#!/usr/bin/env bash
set -e

# === CONFIG ===
APP="delete_bloat_mail.py"
VENV=".venv"
REQS=("google-api-python-client" "google-auth-httplib2" "google-auth-oauthlib" "colorama")

# === COLORS ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# === FUNCTIONS ===
say() { echo -e "${CYAN}›${NC} $1"; }
ok() { echo -e "${GREEN}✔${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✖${NC} $1"; exit 1; }

# === CHECKS ===

say "Проверяем наличие uv…"
if ! command -v uv &>/dev/null; then
    warn "uv не найден в системе."
    read -rp "Установить uv (y/N)? " REPLY
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        say "Скачиваю и устанавливаю uv…"
        curl -LsSf https://astral.sh/uv/install.sh | sh || fail "Не удалось установить uv"
        export PATH="$HOME/.local/bin:$PATH"
        ok "uv установлен."
    else
        fail "Без uv установка невозможна."
    fi
else
    ok "uv найден: $(uv --version)"
fi

# === VENV ===

if [[ ! -d "$VENV" ]]; then
    say "Создаю виртуальное окружение $VENV…"
    uv venv "$VENV" || fail "Не удалось создать виртуальное окружение"
else
    ok "Виртуальное окружение уже существует."
fi

# === ACTIVATE VENV ===
say "Активирую окружение…"
# shellcheck source=/dev/null
source "$VENV/bin/activate"

# === INSTALL DEPENDENCIES ===
say "Устанавливаю зависимости…"
for pkg in "${REQS[@]}"; do
    uv pip install "$pkg" || fail "Ошибка установки пакета $pkg"
done
ok "Все зависимости установлены."

# === CLIENT SECRET CHECK ===
if [[ ! -f "client_secret.json" ]]; then
    warn "Файл client_secret.json не найден!"
    echo "Скачай его из Google Cloud Console:"
    echo "https://console.cloud.google.com/apis/credentials"
    fail "Без client_secret.json Gmail API не заработает."
fi

# === RUN APP ===
say "Запускаю $APP…"
python "$APP" run || fail "Ошибка при выполнении $APP"

ok "Скрипт завершён успешно!"
