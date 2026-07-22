# WebSocket Protocol Documentation

## Overview

This document describes the WebSocket protocol for the radar system with joystick integration. The protocol supports real-time communication between clients and the server for radar operations and joystick control.

## Connection

- **URL**: `ws://localhost:8765`
- **Protocol**: WebSocket
- **Authentication**: None (internal system)

## Message Format

All messages follow JSON format:

```json
{
  "type": "message_type",
  "timestamp": 1234567890123,
  "user_id": "user_identifier",
  "event_owner": "manual|AI",
  "data": {},
  "parameters": {}
}
```

### Common Fields

- `type` (string, required): Message type identifier
- `timestamp` (number, optional): Unix timestamp in milliseconds
- `user_id` (string, optional): User identifier
- `event_owner` (string, optional): Event source ("manual" or "AI")
- `data` (object, optional): Message-specific data
- `parameters` (object, optional): Additional parameters

## Protocol Categories

### 1. Task Management Messages

#### 1.1 Task Start
```json
{
  "type": "task_start",
  "user_id": "user_123",
  "include_ai": false,
  "is_practice": false,
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "init_settings",
  "task_id": "task_456",
  "settings": {
    "range": 80,
    "scanAngle": 30
  },
  "is_ai_active": false,
  "ai_level": "beginner",
  "audio_enabled": true,
  "repetition_info": {
    "current": 1,
    "total": 10
  },
  "task_type": "RADAR_TARGETING"
}
```

#### 1.2 Settings Update
```json
{
  "type": "settings_update",
  "range": 80,
  "scanAngle": 30,
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

### 2. Radar Operations

#### 2.1 Antenna Adjustment
```json
{
  "type": "antenna_adjusted",
  "elevation": 2.0,
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

#### 2.2 Target Selection
```json
{
  "type": "target_selected",
  "target_id": "target_001",
  "action": "select",
  "iff_mode": false,
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

#### 2.3 Threat Response
```json
{
  "type": "threat_clicked",
  "threat_id": "threat_001",
  "label": "High Priority",
  "priority": 1,
  "is_highest_priority": true,
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

### 3. Joystick Control Messages

#### 3.1 Joystick Connection
```json
{
  "type": "joystick_connect",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "joystick_connect_response",
  "success": true,
  "message": "Joystick connected successfully",
  "device_info": {
    "vendor_id": "0x1234",
    "product_id": "0x5678",
    "device_name": "USB Joystick"
  }
}
```

#### 3.2 Joystick Disconnection
```json
{
  "type": "joystick_disconnect",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "joystick_disconnect_response",
  "success": true,
  "message": "Joystick disconnected successfully"
}
```

#### 3.3 Joystick Data Stream
```json
{
  "type": "joystick_data",
  "data": {
    "main_x": 0.5,
    "main_y": -0.3,
    "sub_x": 0,
    "sub_y": 0,
    "buttons": {
      "button0": false,
      "button1": false,
      "button2": true,
      "button7": false
    }
  },
  "device_status": "connected",
  "timestamp": 1234567890.123
}
```

后台按键字段使用 pygame/DirectInput 的零基索引，因此操杆实体第3键对应 `button2`：`button2=true` 表示按下人工复核键，`button2=false` 表示松开。任一按键状态变化都会触发数据广播，不依赖操纵轴是否移动。

#### 3.4 Joystick Status Request
```json
{
  "type": "joystick_get_status",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "joystick_status_response",
  "status": "connected",
  "device_info": {
    "vendor_id": "0x1234",
    "product_id": "0x5678",
    "device_name": "USB Joystick"
  },
  "is_active": true,
  "last_data_timestamp": 1234567890120
}
```

#### 3.5 Joystick Subscription
```json
{
  "type": "joystick_subscribe",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "joystick_subscribe_response",
  "success": true,
  "message": "Subscribed to joystick data stream"
}
```

#### 3.6 Joystick Unsubscription
```json
{
  "type": "joystick_unsubscribe",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

#### 3.7 Joystick Calibration
```json
{
  "type": "joystick_reset_center",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

**Response:**
```json
{
  "type": "joystick_reset_center_response",
  "success": true,
  "message": "Joystick center position reset",
  "center_position": {
    "axis_x": 0.0,
    "axis_y": 0.0
  }
}
```

#### 3.8 Boundary Detection Control
```json
{
  "type": "joystick_start_boundary",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

```json
{
  "type": "joystick_stop_boundary",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

### 4. SA (Situational Awareness) Operations

#### 4.1 Switch to SA Mode
```json
{
  "type": "SwitchSA",
  "user_id": "user_123",
  "is_practice": false,
  "is_ai_active": false,
  "timestamp": 1234567890123
}
```

#### 4.2 Reset SA Mode
```json
{
  "type": "ResetSA",
  "user_id": "user_123",
  "timestamp": 1234567890123
}
```

### 5. Operation Recording

#### 5.1 Single Operation Recording
```json
{
  "type": "record_operation",
  "operation": {
    "task_id": "task_456",
    "operationType": "target_selected",
    "timestamp": 1234567890123,
    "isActive": true,
    "parameters": {
      "target_id": "target_001"
    },
    "user_id": "user_123",
    "event_owner": "manual"
  }
}
```

#### 5.2 Bulk Operations Recording
```json
{
  "type": "record_bulk_operations",
  "operations": [
    {
      "task_id": "task_456",
      "operationType": "joystick_data",
      "timestamp": 1234567890123,
      "isActive": true,
      "parameters": {
        "axis_x": 0.5,
        "axis_y": -0.3
      },
      "user_id": "user_123",
      "event_owner": "manual"
    }
  ]
}
```

## Error Handling

### Error Response Format
```json
{
  "type": "error",
  "error_code": "INVALID_MESSAGE_TYPE",
  "message": "Unknown message type: invalid_type",
  "timestamp": 1234567890123
}
```

### Common Error Codes
- `INVALID_MESSAGE_TYPE`: Unknown message type
- `MISSING_USER_ID`: Required user_id field missing
- `DEVICE_NOT_CONNECTED`: Joystick device not connected
- `PERMISSION_DENIED`: User lacks permission for operation
- `INVALID_PARAMETERS`: Invalid or missing parameters
- `TASK_NOT_STARTED`: Operation requires active task

## Connection States

### Client Connection Lifecycle
1. **Connect**: Client establishes WebSocket connection
2. **Authentication**: Optional authentication step
3. **Active**: Normal message exchange
4. **Disconnected**: Connection closed

### Joystick Device States
- `disconnected`: No joystick device connected
- `connecting`: Attempting to connect to device
- `connected`: Device connected and ready
- `active`: Device actively sending data
- `error`: Device error state

## Data Flow Architecture

### Joystick Data Flow
1. **Hardware** → SimpleJoystickController → JoystickWebSocketController
2. **Controller** → JoystickEventHandler → WebSocketServer
3. **Server** → Client broadcast → Frontend

### Client Message Flow
1. **Client** → WebSocketServer → JoystickEventHandler
2. **Handler** → JoystickWebSocketController → Hardware
3. **Fallback** → MessageHandler → Database

## Implementation Notes

### Broadcasting
- Joystick data is broadcast to all subscribed clients
- Client filtering is handled server-side
- Rate limiting prevents data flooding

### Session Management
- Each client maintains session state
- Session data includes user_id, task_id, and preferences
- Sessions persist across temporary disconnections

### Error Recovery
- Automatic reconnection for network issues
- Device error handling with retry logic
- Graceful degradation when joystick unavailable

## Security Considerations

- Internal network communication only
- No authentication required (trusted environment)
- Input validation on all message parameters
- Rate limiting to prevent DoS attacks
- Sanitization of user-provided data

## Performance Specifications

- **Maximum Clients**: 50 concurrent connections
- **Message Rate**: Up to 60 messages/second per client
- **Joystick Data Rate**: 30 Hz (33ms intervals)
- **Latency Target**: < 50ms for joystick data
- **Buffer Size**: 1024 messages per client

## Version History

- **v1.0**: Initial protocol design
- **v1.1**: Added joystick control messages
- **v1.2**: Enhanced error handling and state management
- **v1.3**: Added SA operations and bulk recording

## Examples

### Complete Joystick Session
```javascript
// 1. Connect to joystick
ws.send(JSON.stringify({
  type: "joystick_connect",
  user_id: "operator_001",
  timestamp: Date.now()
}));

// 2. Subscribe to data stream
ws.send(JSON.stringify({
  type: "joystick_subscribe",
  user_id: "operator_001",
  timestamp: Date.now()
}));

// 3. Reset center position
ws.send(JSON.stringify({
  type: "joystick_reset_center",
  user_id: "operator_001",
  timestamp: Date.now()
}));

// 4. Handle incoming data
ws.onmessage = function(event) {
  const message = JSON.parse(event.data);
  if (message.type === "joystick_data") {
    // Process joystick data
    console.log("Joystick:", message.data);
  }
};
```

### Radar Task Flow
```javascript
// 1. Start radar task
ws.send(JSON.stringify({
  type: "task_start",
  user_id: "operator_001",
  include_ai: false,
  is_practice: false,
  timestamp: Date.now()
}));

// 2. Update settings
ws.send(JSON.stringify({
  type: "settings_update",
  range: 80,
  scanAngle: 30,
  user_id: "operator_001",
  timestamp: Date.now()
}));

// 3. Adjust antenna
ws.send(JSON.stringify({
  type: "antenna_adjusted",
  elevation: 2.0,
  user_id: "operator_001",
  timestamp: Date.now()
}));

// 4. Select target
ws.send(JSON.stringify({
  type: "target_selected",
  target_id: "target_001",
  action: "select",
  iff_mode: false,
  user_id: "operator_001",
  timestamp: Date.now()
}));
```

---

*This protocol documentation is for the radar system with joystick integration. For implementation details, refer to the source code in the `server/` directory.*
