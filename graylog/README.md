# Graylog Logging Stack

Centralized logging for Smart Support using Graylog.

## Quick Start

1. **Start Graylog**:
   ```bash
   cd /Users/damir/Desktop/smart-support/graylog
   docker-compose up -d
   ```

2. **Access Graylog Web UI**:
   - URL: http://localhost:19000
   - Username: `admin`
   - Password: `admin`

3. **Configure Input**:
   - Go to System → Inputs
   - Select "GELF TCP" or "GELF UDP"
   - Title: "Smart Support Backend"
   - Port: 12201 (already exposed)
   - Save

## Logging Configuration

The backend sends structured JSON logs in GELF format to Graylog.

### Environment Variables

Add to your `.env` file:
```bash
# Graylog Configuration
GRAYLOG_ENABLED=true
GRAYLOG_HOST=localhost
GRAYLOG_PORT=12201
GRAYLOG_PROTOCOL=tcp  # tcp or udp
LOG_LEVEL=INFO
LOG_FORMAT=json  # json or text
```

### Log Fields

Each log entry includes:
- `timestamp`: ISO 8601 timestamp
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `logger`: Module name
- `message`: Log message
- `service`: "smart-support-backend"
- `environment`: dev/prod/test
- `request_id`: Unique ID for HTTP requests
- `user_id`: Authenticated user ID (if available)
- `endpoint`: HTTP endpoint
- `method`: HTTP method
- `status_code`: HTTP status code
- `duration_ms`: Request duration
- `db_operation`: SQL operation type
- `db_table`: Database table name
- `db_duration_ms`: Query duration
- `error_type`: Exception type (for errors)
- `stack_trace`: Full stack trace (for errors)

## Security Notes

1. **Sensitive Data Masking**:
   - Passwords, tokens, API keys are automatically masked
   - Request/response bodies are sanitized
   - Personal data is redacted

2. **Production**:
   - Change default passwords in `.env`
   - Use TLS for Graylog communication
   - Configure firewall rules
   - Set up retention policies

## Integration with Backend

The backend uses:
- `python-json-logger` for structured JSON logging
- Custom GELF handler for Graylog
- FastAPI middleware for HTTP logging
- SQLAlchemy events for DB logging

## Monitoring

Check logs in Graylog:
1. Search: `service:"smart-support-backend"`
2. Create dashboards for:
   - HTTP request rates
   - Error rates by endpoint
   - Slow database queries
   - Application performance

## Troubleshooting

1. **Graylog not starting**:
   - Check Docker logs: `docker-compose logs graylog`
   - Ensure ports 9000, 12201 are free

2. **Logs not appearing**:
   - Verify input is running in Graylog UI
   - Check backend logs for connection errors
   - Test with: `echo '{"version":"1.1","host":"test","short_message":"Test"}' | nc -w1 localhost 12201`

3. **High memory usage**:
   - Adjust Elasticsearch heap size in docker-compose.yml
   - Configure log retention policies