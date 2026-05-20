# /tobii/hand API

`/tobii/hand` updates the current gaze task attention area when a target prompt appears or disappears. The same payload is supported over WebSocket with `type: "tobii_hand"`.

## Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `box_visible` | boolean | yes | `true` updates attention regions; `false` clears them. |
| `task_id` | string / number | no | Must match the active gaze task when provided. |
| `coordinate_space` | string | no | `display_area_normalized` or `physical_pixel`. Missing values are inferred from coordinate magnitudes. |
| `regions` | array | no | Preferred region list. Supports `rect` and `ellipse`. |
| `bbox` | array | no | Legacy rectangle list: `[[left, top, right, bottom], ...]`. |
| `screen_data` | array | no | Physical screen size `[width, height]`, only needed for `physical_pixel`. Falls back to server `.env`. |

Do not use the old misspelled screen-size field.

## Preferred Normalized Payload

```json
{
  "box_visible": true,
  "task_id": "1",
  "coordinate_space": "display_area_normalized",
  "regions": [
    {
      "shape": "rect",
      "left": 0.12,
      "top": 0.20,
      "right": 0.38,
      "bottom": 0.30
    },
    {
      "shape": "ellipse",
      "cx": 0.50,
      "cy": 0.50,
      "rx": 0.04,
      "ry": 0.07
    }
  ]
}
```

## Physical Pixel Compatibility

```json
{
  "box_visible": true,
  "task_id": "1",
  "coordinate_space": "physical_pixel",
  "regions": [
    {
      "shape": "rect",
      "left": 320,
      "top": 280,
      "right": 780,
      "bottom": 360
    }
  ],
  "screen_data": [2560, 1440]
}
```

## Legacy bbox Compatibility

```json
{
  "box_visible": true,
  "task_id": "1",
  "coordinate_space": "physical_pixel",
  "bbox": [[320, 280, 780, 360]],
  "screen_data": [2560, 1440]
}
```

## Clear Regions

```json
{
  "box_visible": false,
  "task_id": "1"
}
```

## WebSocket

```json
{
  "type": "tobii_hand",
  "box_visible": true,
  "task_id": "1",
  "coordinate_space": "display_area_normalized",
  "regions": [
    {
      "shape": "rect",
      "left": 0.12,
      "top": 0.20,
      "right": 0.38,
      "bottom": 0.30
    }
  ]
}
```

Response type is `tobii_hand_result`.
