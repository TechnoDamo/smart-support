#!/bin/sh
# Устанавливает всё необходимое для GPU-деплоя Smart Support на Linux.
# Требования: Ubuntu 22.04/24.04, root или sudo, NVIDIA GPU с установленным драйвером.

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}[OK]${NC}  %s\n" "$*"; }
info() { printf "${YELLOW}[..]${NC}  %s\n" "$*"; }
err()  { printf "${RED}[ERR]${NC} %s\n" "$*" >&2; exit 1; }

# ── Проверки ────────────────────────────────────────────────────────────────

[ "$(uname -s)" = "Linux" ] || err "Скрипт поддерживает только Linux."

if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=sudo
  else
    err "Нужны права root или sudo."
  fi
else
  SUDO=""
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  err "nvidia-smi не найден. Установите NVIDIA-драйвер перед запуском этого скрипта."
fi
ok "NVIDIA GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

# ── Docker ──────────────────────────────────────────────────────────────────

if command -v docker >/dev/null 2>&1; then
  ok "Docker уже установлен: $(docker --version)"
else
  info "Устанавливаем Docker..."
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker
  ok "Docker установлен: $(docker --version)"
fi

# ── NVIDIA Container Toolkit ─────────────────────────────────────────────────

if command -v nvidia-ctk >/dev/null 2>&1; then
  ok "NVIDIA Container Toolkit уже установлен: $(nvidia-ctk --version | head -1)"
else
  info "Устанавливаем NVIDIA Container Toolkit..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | $SUDO gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed "s#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" \
    | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  $SUDO apt-get -qq update
  $SUDO apt-get -y -qq install --allow-change-held-packages nvidia-container-toolkit
  $SUDO nvidia-ctk runtime configure --runtime=docker
  $SUDO systemctl restart docker
  ok "NVIDIA Container Toolkit установлен: $(nvidia-ctk --version | head -1)"
fi

# ── uv ──────────────────────────────────────────────────────────────────────

if command -v uv >/dev/null 2>&1; then
  ok "uv уже установлен: $(uv --version)"
else
  info "Устанавливаем uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
  ok "uv установлен: $(uv --version)"
fi

# ── huggingface_hub (hf CLI) ─────────────────────────────────────────────────

if command -v hf >/dev/null 2>&1; then
  ok "hf CLI уже доступен: $(hf --version)"
else
  info "Устанавливаем huggingface_hub в /opt/hf-venv..."
  python3 -m venv /opt/hf-venv
  /opt/hf-venv/bin/pip install -q huggingface_hub
  $SUDO ln -sf /opt/hf-venv/bin/hf /usr/local/bin/hf
  ok "hf CLI установлен: $(hf --version)"
fi

# ── Проверка GPU в Docker ────────────────────────────────────────────────────

info "Проверяем доступность GPU внутри Docker..."
if docker run --rm --gpus all ubuntu nvidia-smi >/dev/null 2>&1; then
  ok "GPU доступен в Docker."
else
  err "GPU не доступен в Docker. Проверьте nvidia-container-toolkit и перезапустите Docker."
fi

# ── Итог ────────────────────────────────────────────────────────────────────

printf "\n${GREEN}Все инструменты установлены. Следующие шаги:${NC}\n"
printf "  make -C llm download-model\n"
printf "  make -C embedding download-model\n"
printf "  make up\n\n"
