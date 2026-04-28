#!/bin/sh

set -eu

model_alias="${LLM_MODEL_LOCAL:-qwen2.5-0.5b-instruct}"
model_path="/models/${model_alias}"
max_model_len="${LLM_CTX_SIZE:-2048}"
dtype="${LLM_DTYPE:-bfloat16}"

if [ ! -e /dev/nvidiactl ] && [ ! -e /dev/nvidia0 ]; then
  echo "Ошибка: NVIDIA GPU не обнаружен. Деплой поддерживает только CUDA." >&2
  exit 1
fi

if [ ! -f "${model_path}/config.json" ]; then
  echo "Ошибка: модель не найдена по пути ${model_path}." >&2
  echo "Выполните: make -C llm download-model" >&2
  exit 1
fi

exec python3 -m vllm.entrypoints.openai.api_server \
  --model "$model_path" \
  --served-model-name "$model_alias" \
  --host 0.0.0.0 \
  --port 8080 \
  --dtype "$dtype" \
  --max-model-len "$max_model_len" \
  --trust-remote-code
