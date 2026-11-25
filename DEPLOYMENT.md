# Deployment Information

## Public URL
https://day14-production-agent-b1rf.onrender.com

> Gói Free của Render tự "ngủ" sau khoảng 15 phút không có request. Lần gọi đầu tiên sau khi ngủ có thể mất 30–60 giây để khởi động lại.

## Platform
**Render** (Web Service, runtime Docker, gói Free, region Singapore) + **Render Key Value** (Redis) làm nơi lưu state.

- Code deploy: thư mục `06-lab-complete/` của repo này (Root Directory = `06-lab-complete`), build theo `06-lab-complete/Dockerfile` (multi-stage, `python:3.11-slim`, user non-root).
- Health check path cấu hình trên Render: `/health`.
- File cấu hình nền tảng trong repo: `06-lab-complete/render.yaml` (và `06-lab-complete/railway.toml`).
- Ghi chú: ban đầu chọn Railway nhưng tài khoản Railway đã hết thời gian dùng thử (`Your trial has expired. Please select a plan to continue using Railway.`), nên chuyển sang Render.

## Test Commands

Đặt biến (thay `YOUR_KEY` bằng API key đã cấu hình trên Render; không ghi key thật vào repo):
```bash
BASE=https://day14-production-agent-b1rf.onrender.com
AGENT_API_KEY=YOUR_KEY
```

### Health check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl "$BASE/health"
# {"status":"ok"}
```

### Readiness (Redis đã kết nối)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl "$BASE/ready"
# {"ready":true}
```

### API không có key → 401
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
```

### API có key → 200
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'   # 200
```

Kết quả thực tế (ảnh `screenshots/test.png`): `200`, `200`, `401`, `200`.

### Kiểm tra bằng script chấm
```bash
cd 06-lab-complete
python check_production_ready.py --public-url https://day14-production-agent-b1rf.onrender.com
# ✅ Public URL: GET https://day14-production-agent-b1rf.onrender.com/health → 200
# Result: 12/12 tiêu chí đạt · 44/44 checks passed
```

## Environment Variables Set
Đặt trong **Render → Service → Environment**, không ghi trong code (chỉ liệt kê tên, không ghi giá trị):

| Biến | Ghi chú |
|---|---|
| `AGENT_API_KEY` | Secret, chuỗi ngẫu nhiên tạo bằng `secrets.token_urlsafe(32)` |
| `REDIS_URL` | Internal URL của Render Key Value (Redis) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `10` |
| `PORT` | Render tự cấp; app đọc qua biến `PORT` |

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
