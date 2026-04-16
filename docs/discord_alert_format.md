# Discord Alert Format

BreakoutBolt sends structured Discord webhook embeds.

## Entry Signal

```json
{
  "username": "BreakoutBolt",
  "embeds": [
    {
      "title": "BUY NVDA",
      "description": "Breakout continuation above VWAP and premarket high",
      "fields": [
        {"name": "Entry", "value": "941.20", "inline": true},
        {"name": "Stop", "value": "933.50", "inline": true},
        {"name": "Target", "value": "959.40", "inline": true},
        {"name": "R/R", "value": "2.35", "inline": true},
        {"name": "Confidence", "value": "79.00%", "inline": true},
        {"name": "AI Review", "value": "Risk approved; AI validation approved", "inline": false}
      ]
    }
  ]
}
```

## Exit Event

```json
{
  "username": "BreakoutBolt",
  "embeds": [
    {
      "title": "EXIT NVDA",
      "description": "TARGET_HIT",
      "fields": [
        {"name": "Entry", "value": "941.20", "inline": true},
        {"name": "Stop", "value": "933.50", "inline": true},
        {"name": "Target", "value": "959.40", "inline": true}
      ]
    }
  ]
}
```
