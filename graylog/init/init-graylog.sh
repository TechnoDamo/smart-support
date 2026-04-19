#!/bin/sh
set -eu

GRAYLOG_URL="${GRAYLOG_URL:-http://graylog:9000}"
GRAYLOG_USER="${GRAYLOG_USER:-admin}"
GRAYLOG_ADMIN_PASSWORD="${GRAYLOG_ADMIN_PASSWORD:-admin}"
GRAYLOG_INPUT_TITLE="${GRAYLOG_INPUT_TITLE:-Smart Support Backend GELF TCP}"
GRAYLOG_INPUT_PORT="${GRAYLOG_INPUT_PORT:-12201}"
GRAYLOG_REQUESTED_BY="${GRAYLOG_REQUESTED_BY:-smart-support-graylog-init}"
GRAYLOG_INPUTS_TMP="/tmp/graylog-inputs.json"
GRAYLOG_PAYLOAD_TMP="/tmp/graylog-input-payload.json"

fetch_inputs_status() {
  curl -sS \
    -o "$GRAYLOG_INPUTS_TMP" \
    -w "%{http_code}" \
    -u "$GRAYLOG_USER:$GRAYLOG_ADMIN_PASSWORD" \
    -H "X-Requested-By: $GRAYLOG_REQUESTED_BY" \
    "$GRAYLOG_URL/api/system/inputs"
}

echo "Ожидание готовности Graylog API..."
attempt=1
status=""
while [ "$attempt" -le 60 ]; do
  status="$(fetch_inputs_status || true)"
  if [ "$status" = "200" ]; then
    break
  fi

  echo "Graylog API ещё не готов (попытка $attempt/60, статус=${status:-n/a})"
  attempt=$((attempt + 1))
  sleep 5
done

if [ "$status" != "200" ]; then
  echo "Не удалось дождаться Graylog API"
  exit 1
fi

if grep -Fq "\"title\":\"$GRAYLOG_INPUT_TITLE\"" "$GRAYLOG_INPUTS_TMP"; then
  echo "Graylog input уже существует: $GRAYLOG_INPUT_TITLE"
  exit 0
fi

cat > "$GRAYLOG_PAYLOAD_TMP" <<EOF
{"title":"$GRAYLOG_INPUT_TITLE","global":true,"type":"org.graylog2.inputs.gelf.tcp.GELFTCPInput","configuration":{"bind_address":"0.0.0.0","port":$GRAYLOG_INPUT_PORT,"recv_buffer_size":1048576,"number_worker_threads":2,"override_source":null,"tls_enable":false,"tls_cert_file":"","tls_key_file":"","tls_key_password":"","use_null_delimiter":true,"max_message_size":2097152}}
EOF

curl -sS \
  -u "$GRAYLOG_USER:$GRAYLOG_ADMIN_PASSWORD" \
  -H "X-Requested-By: $GRAYLOG_REQUESTED_BY" \
  -H "Content-Type: application/json" \
  -X POST \
  "$GRAYLOG_URL/api/system/inputs" \
  --data @"$GRAYLOG_PAYLOAD_TMP" >/tmp/graylog-input-created.json

echo "Graylog input создан: $GRAYLOG_INPUT_TITLE"
