# Antenna Mock Service (Test Only)

## Start

```bash
python server/test/mock_antenna_service.py
```

## Endpoints

- WebSocket: `ws://127.0.0.1:8081/ws/antenna-adjustment`
- HTTP (compat): `POST http://127.0.0.1:8081/api/antenna-adjustment-status`

## WS behavior

- Client sends `start_round` -> server waits 3 seconds then pushes:
  - `should_flash: true/false` (random)
  - `duration_ms: 3000`
- Client sends `update_bbox` -> server replies `ack`
- Client sends `end_round` -> server replies `ack`

