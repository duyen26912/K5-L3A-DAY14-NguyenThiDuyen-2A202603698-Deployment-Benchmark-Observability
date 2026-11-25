# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production
### Exercise 1.1: Anti-patterns found
- **Secrets hardcode trong source code:** `OPENAI_API_KEY` và `DATABASE_URL` được gán trực tiếp trong mã, có nguy cơ lộ khi chia sẻ hoặc push repository.
- **Cấu hình môi trường hardcode:** `DEBUG = True` và `MAX_TOKENS = 500` đặt trực tiếp trong mã, không đọc từ cấu hình môi trường.
- **Dùng `print()` cho log và làm lộ bí mật:** ứng dụng dùng `print()` thay vì logging; đặc biệt có lệnh ghi cả API key vào log.
- **Thiếu health check:** app chỉ khai báo `/` và `/ask`, không có endpoint `/health` để nền tảng kiểm tra trạng thái.
- **Port cố định:** Uvicorn luôn chạy cổng 8000, không đọc biến môi trường `PORT` mà nền tảng thường cung cấp.
- **Chỉ bind vào localhost:** `host="localhost"` khiến server chỉ nhận kết nối nội bộ máy, khó truy cập từ container hoặc nền tảng triển khai.
- **Bật tự reload khi chạy:** `reload=True` phù hợp phát triển nhưng không phù hợp production.
- **Không khai báo xử lý shutdown/graceful shutdown riêng:** trong file không có signal handler hoặc callback shutdown. Uvicorn vẫn có xử lý tín hiệu mặc định; đây là thiếu xử lý tùy chỉnh cho tài nguyên cần đóng.
### Exercise 1.2: Kết quả chạy bản develop
Lệnh chạy thử:
```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả:
```json
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Nhận xét: Bản develop chạy được trên máy local và trả lời request thành công. Tuy nhiên, bản này chưa production-ready: API key và thông tin database được hardcode trong source code, cấu hình `DEBUG` cũng bị cố định, ứng dụng dùng `print()` để ghi log và có thể làm lộ key, chưa có endpoint `/health`, dùng port 8000 cố định, chỉ bind vào `localhost` và luôn bật `reload=True`. Ứng dụng cũng chưa khai báo xử lý shutdown riêng (Uvicorn vẫn có xử lý tín hiệu mặc định).
### Exercise 1.3: Comparison table
| Feature | Develop | Production | Tại sao quan trọng? |
|---|---|---|---|
| Config | Gán trực tiếp trong `app.py` (`DEBUG`, `MAX_TOKENS`) | Gom trong `production/config.py`, đọc từ environment variables như `DEBUG`, `MAX_TOKENS`, `APP_NAME` | Thay đổi cấu hình theo môi trường mà không sửa mã; dễ quản lý và triển khai nhất quán. |
| Secrets | API key và `DATABASE_URL` hardcode trong source code | Đọc `OPENAI_API_KEY`, `AGENT_API_KEY` từ environment; `config.py` kiểm tra thiếu `AGENT_API_KEY` khi `ENVIRONMENT=production` | Tránh đưa bí mật vào Git và phát hiện cấu hình bảo mật bị thiếu. |
| Port / Host | `localhost:8000` cố định | `settings.host` mặc định `0.0.0.0`, `settings.port` đọc từ `PORT` (mặc định 8000) | Container/cloud có thể truy cập ứng dụng và cấp cổng động cho từng instance. |
| Debug / reload | `reload=True` luôn bật | `settings.debug` đọc từ `DEBUG`; reload chỉ bật khi debug bật | Tránh tự reload ngoài môi trường phát triển và cho phép đặt chế độ phù hợp môi trường. |
| Health check | Không có `/health` | Có `/health`, `/ready` và `/metrics` | Nền tảng/load balancer có thể theo dõi tình trạng, readiness và uptime để định tuyến hoặc khởi động lại phù hợp. |
| Logging | `print()` nội dung request, response và cả API key | Dùng `logging` với log có cấu trúc; ghi độ dài request/response, không ghi secret | Dễ truy vấn trong hệ thống tập trung và giảm nguy cơ lộ thông tin nhạy cảm. |
| Shutdown | Không khai báo signal handler hoặc lifecycle cleanup riêng | Có FastAPI `lifespan` để đánh dấu ngừng sẵn sàng, hoàn tất shutdown; có handler SIGTERM | Cho phép dừng container có trật tự và thực hiện cleanup khi cần, giảm request bị gián đoạn. |
| Input / response | `?question=` query parameter; trả về `answer` | JSON body `{"question":"..."}`; trả về `question`, `answer` và `model` | JSON rõ cấu trúc, thuận tiện mở rộng và client biết nội dung câu hỏi/model đã xử lý. |

Kết quả chạy bản production:
```bash
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
```
```json
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```
Nhận xét: Production nhận JSON request và trả về đủ `question`, `answer`, `model` như thiết kế. Nội dung phản hồi ghi rõ đây là mock response, nên kết quả này xác nhận endpoint chạy được nhưng chưa chứng minh đã gọi LLM thật.

## Part 2: Docker
### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11` — image Python đầy đủ, dễ bắt đầu nhưng có kích thước lớn.
2. **Working directory:** `/app`, được thiết lập bằng `WORKDIR /app`.
3. **Vì sao copy `requirements.txt` trước `COPY . .`?** Docker tạo cache theo từng layer. File requirements thường ít thay đổi hơn mã nguồn, nên Docker có thể dùng lại layer cài dependencies khi chỉ sửa code, giúp build nhanh hơn. Dockerfile này copy các file cần thiết riêng thay vì dùng `COPY . .`, cùng nguyên tắc đó.
4. **Khác nhau giữa `CMD` và `ENTRYPOINT`:** `CMD` đặt lệnh mặc định, có thể thay bằng lệnh truyền vào `docker run`. `ENTRYPOINT` xác định chương trình chính luôn chạy; đối số từ `docker run` thường được nối thêm vào. Có thể dùng `CMD` để cung cấp đối số mặc định cho `ENTRYPOINT`.

### Exercise 2.2: Kết quả chạy container
Build và chạy (từ gốc repo):
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run --rm -p 8000:8000 my-agent:develop
```

Container đang chạy, map cổng `0.0.0.0:8000->8000/tcp`.

Gọi agent:
```bash
curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
```
```json
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Health check:
```bash
curl -i http://localhost:8000/health
```
```text
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"status":"ok","uptime_seconds":194.4,"container":true}
```

Kích thước image (`docker images my-agent:develop`):
```text
IMAGE              ID             DISK USAGE
my-agent:develop   bd608ce19e1d       1.15GB
```
→ `docker image inspect` cho `1154311927` bytes ≈ **1.15 GB (~1101 MB)**.

Nhận xét: container chạy được và trả lời đúng, có `/health` trả 200 với `"container": true`. Tuy nhiên image rất lớn (~1.15 GB) vì dùng base `python:3.11` đầy đủ (có compiler, build tools, nhiều thư viện hệ thống không cần khi chạy) và build một stage. Exercise 2.3 sẽ so sánh với bản multi-stage dùng `python:3.11-slim`.
### Exercise 2.3: Image size comparison
**Stage 1 — Builder:** dùng `python:3.11-slim`, cài các công cụ build như `gcc` và `libpq-dev`, rồi cài dependencies từ `requirements.txt` vào `/root/.local`. Stage này phục vụ việc chuẩn bị thư viện, không được dùng làm image chạy ứng dụng.

**Stage 2 — Runtime:** bắt đầu lại từ image `python:3.11-slim` sạch, chỉ chép thư mục packages đã cài (`COPY --from=builder /root/.local /home/appuser/.local`) cùng `main.py` và `utils/mock_llm.py`. Stage này tạo user không phải root (`appuser`), đặt `HEALTHCHECK` gọi `/health` và khởi động bằng `uvicorn main:app --workers 2`.

**Lệnh build và đo (từ gốc repo):**
```bash
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images | grep my-agent
```
```text
my-agent:advanced   cd83a92eb2d0   163MB
my-agent:develop    bd608ce19e1d   1.15GB
```

**So sánh kích thước thực tế** (số byte chính xác lấy bằng `docker image inspect --format "{{.Size}}"`):

| Image | Base | Kích thước |
|---|---|---|
| `my-agent:develop` | `python:3.11`, 1 stage | 1 154 311 927 bytes ≈ **1.15 GB** (~1154 MB) |
| `my-agent:advanced` | `python:3.11-slim`, multi-stage | 162 882 434 bytes ≈ **163 MB** |
| Chênh lệch | | ≈ **991 MB** |

% giảm = (1154.3 − 162.9) / 1154.3 × 100 ≈ **85.9%**, tức bản advanced nhỏ hơn khoảng **7.1 lần**.

**Vì sao image nhỏ hơn:** image cuối chỉ chứa runtime Python, dependencies và mã ứng dụng. `docker history my-agent:advanced` cho thấy layer dependencies chỉ khoảng **37.8 MB**, còn các layer source code chỉ vài KB. Các công cụ build như `gcc`, `libpq-dev` và apt cache nằm ở Stage 1 và bị bỏ lại, không đi vào image cuối. Phần giảm lớn nhất đến từ base `python:3.11-slim` thay cho `python:3.11` đầy đủ, vì bản đầy đủ có sẵn compiler, header và nhiều thư viện hệ thống không cần khi chạy. Image nhỏ hơn thì pull/deploy nhanh hơn và ít bề mặt tấn công hơn.

### Exercise 2.4: Docker Compose architecture
```mermaid
flowchart LR
    client[Client / Host]
    subgraph internal["Docker bridge network: internal"]
        nginx["Nginx\n80 / 443"]
        agent["FastAPI Agent\nagent:8000"]
        redis["Redis\nredis:6379"]
        qdrant["Qdrant\nqdrant:6333"]
        redisvol[("redis_data\n/ data")]
        qdrantvol[("qdrant_data\n/ qdrant / storage")]
        nginx -->|proxy_pass| agent
        agent -->|REDIS_URL| redis
        agent -->|QDRANT_URL| qdrant
        redis --- redisvol
        qdrant --- qdrantvol
    end
    client -->|HTTP :80 / HTTPS :443| nginx
```

Nginx là điểm vào duy nhất được publish ra host; agent, Redis và Qdrant giao tiếp qua network `internal`. Hai named volume giữ dữ liệu Redis và Qdrant bền vững khi container được tạo lại.

Lệnh chạy (trong `02-docker/production/`, đặt tên project riêng bằng `-p` để không trùng các thư mục `production` khác):
```bash
touch .env.local
docker compose -p k5-day14-docker up -d --build
docker compose -p k5-day14-docker ps
```
```text
SERVICE   IMAGE                   STATUS                 PORTS
agent     k5-day14-docker-agent   Up (healthy)           8000/tcp
nginx     nginx:alpine            Up                     0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    qdrant/qdrant:v1.9.0    Up (healthy)           6333-6334/tcp
redis     redis:7-alpine          Up (healthy)           6379/tcp
```

**Các service được start (4):**

| Service | Vai trò | Cổng |
|---|---|---|
| `nginx` | Reverse proxy / load balancer, cửa vào duy nhất từ bên ngoài, thêm security headers | Mở ra host `80`, `443` |
| `agent` | FastAPI AI agent, build từ `02-docker/production/Dockerfile` (stage `runtime`) | `8000`, chỉ trong mạng nội bộ |
| `redis` | Cache session và rate limiting (`maxmemory 256mb`, `allkeys-lru`), volume `redis_data` | `6379`, chỉ trong mạng nội bộ |
| `qdrant` | Vector database cho RAG, volume `qdrant_data` | `6333-6334`, chỉ trong mạng nội bộ |

**Sơ đồ kiến trúc:**
```text
                    ┌───────── Docker network "internal" (bridge) ──────────┐
 Client ──:80/443──▶│  nginx ──proxy_pass──▶ agent:8000 ──REDIS_URL──▶ redis:6379
 (host)             │                            │                          │
                    │                            └──QDRANT_URL──▶ qdrant:6333  │
                    └────────────────────────────────────────────────────────┘
   Volumes: redis_data → /data (redis),  qdrant_data → /qdrant/storage (qdrant)
```

**Các service giao tiếp thế nào:**
- Tất cả nằm chung network `internal` (Docker tạo thành `k5-day14-docker_internal`). Docker có DNS nội bộ, nên các service gọi nhau **bằng tên service**: Nginx dùng `upstream agent_backend { server agent:8000; }`, agent nhận `REDIS_URL=redis://redis:6379/0` và `QDRANT_URL=http://qdrant:6333` qua biến môi trường.
- Chỉ `nginx` publish cổng ra host. `agent`, `redis`, `qdrant` không mở cổng ra ngoài, nên client bắt buộc đi qua Nginx.
- Thứ tự khởi động dùng `depends_on` + healthcheck: `agent` chỉ start khi `redis` và `qdrant` đã `healthy`; `nginx` start sau `agent`.
- Ghi chú: trong bài này `main.py` dùng mock LLM nên chưa thực sự đọc/ghi Redis hay Qdrant. Hai service này minh hoạ cách một stack agent thật được ghép lại.

**Test qua Nginx:**
```bash
curl -i http://localhost/health
```
```text
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":70.6,"version":"2.0.0","timestamp":"2026-11-25T09:37:33.113180"}
```
```bash
curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
```
```text
HTTP/1.1 200 OK
Server: nginx
...
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
Header `Server: nginx` và các security header (`X-Frame-Options`, `X-Content-Type-Options`) cho thấy request đã đi qua Nginx rồi mới tới agent.

Dọn stack sau khi xong: `docker compose -p k5-day14-docker down`.

## Part 3: Cloud Deployment
### Exercise 3.1/3.2: URL + nền tảng
Lớp K5 deploy chính agent Part 6 (`06-lab-complete/`), không deploy app mẫu `03-cloud-deployment/`.

- **Nền tảng chính:** Render (Exercise 3.2): Web Service runtime Docker, Root Directory `06-lab-complete`, health check `/health`, cộng thêm Render Key Value (Redis).
- **Public URL:** https://day14-production-agent-b1rf.onrender.com
- **Biến môi trường đặt trên Render** (không ghi trong code): `AGENT_API_KEY`, `REDIS_URL`, `ENVIRONMENT=production`, `RATE_LIMIT_PER_MINUTE=10`, `DAILY_BUDGET_USD=10`; `PORT` do Render cấp.
- **Railway (Exercise 3.1):** đã cài Railway CLI, đăng nhập, `railway init` / `railway up` từ `06-lab-complete/`, nhưng tài khoản bị chặn: `Your trial has expired. Please select a plan to continue using Railway.` Vì không dùng gói trả phí nên chuyển sang Render.

**4 lệnh tự kiểm (CP6)** (`BASE` = URL trên, key che bằng biến):
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```
Kết quả: `200`, `200`, `401`, `200` (ảnh `screenshots/test.png`). Nội dung trả về: `/health` → `{"status":"ok"}`, `/ready` → `{"ready":true}` (Redis trên Render đã kết nối). Gửi key sai cũng trả `401`.

Script chấm với URL public:
```text
python check_production_ready.py --public-url https://day14-production-agent-b1rf.onrender.com
✅ Public URL: GET https://day14-production-agent-b1rf.onrender.com/health → 200
Result: 12/12 tiêu chí đạt · 44/44 checks passed
```

Log trên Render cũng là JSON (`{"ts":"...","level":"INFO","message":"Agent startup","event":"startup"}`). Các dòng `GET /` → 404 trong log là do agent không có route trang chủ (chỉ có `/health`, `/ready`, `/ask`), không phải lỗi.

Ảnh: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`. Chi tiết trong `DEPLOYMENT.md`.

### So sánh railway.toml vs render.yaml
`06-lab-complete/railway.toml`:
```toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/health"
restartPolicyType = "ON_FAILURE"
```
`06-lab-complete/render.yaml`:
```yaml
services:
  - type: web
    name: day14-production-agent
    runtime: docker
    healthCheckPath: /health
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: AGENT_API_KEY
        generateValue: true
      - key: REDIS_URL
        sync: false
      - key: RATE_LIMIT_PER_MINUTE
        value: "10"
      - key: DAILY_BUDGET_USD
        value: "10"
```

| Điểm so sánh | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML | YAML |
| Phạm vi | Cấu hình build/deploy cho **một service đã có** (project và service tạo bằng CLI/dashboard) | **Blueprint (Infrastructure as Code):** khai báo cả danh sách `services`, mỗi service có `type: web`, `name`, `runtime` |
| Cách build | `builder = "DOCKERFILE"` | `runtime: docker` |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Khi lỗi | Có `restartPolicyType = "ON_FAILURE"` | Không khai báo (Render tự restart khi health check fail) |
| Biến môi trường | Không nằm trong file, đặt bằng `railway variables` hoặc dashboard | Khai báo trong `envVars`; giá trị thường ghi thẳng, secret dùng `generateValue: true` (Render tự sinh `AGENT_API_KEY`) hoặc `sync: false` (người dùng nhập `REDIS_URL` trên dashboard, không lưu trong repo) |
| Redis | Không khai báo; CLI chỉ phát hiện "service dependencies: redis" nhưng không tự tạo | Có thể khai báo thêm service Key Value trong cùng blueprint (file hiện tại chưa có nên tạo Redis bằng dashboard) |

**Vì sao khác nhau:** Railway coi file config là phần bổ sung cho project được quản lý chủ yếu qua CLI/dashboard, nên file ngắn và chỉ lo build/deploy. Render Blueprint muốn mô tả toàn bộ hạ tầng trong repo để tạo lại được bằng một lần "New → Blueprint", nên có cả loại service và biến môi trường, kèm cơ chế để **không ghi secret vào file**. Cả hai đều dùng Dockerfile và health check `/health`, nên cùng một image chạy được trên cả hai nền tảng.

Trải nghiệm thực tế: Railway yêu cầu gói trả phí khi hết trial; Render có gói Free nhưng service tự ngủ sau ~15 phút không có request (cold start 30–60 giây).

### Exercise 3.3: Cloud Run CI/CD pipeline
Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml` (không cần tài khoản GCP):
1. **Trigger:** khi push lên nhánh `main`, Cloud Build chạy pipeline trong `cloudbuild.yaml`.
2. **Test:** bước `test` chạy trong `python:3.11-slim`, cài requirements và chạy `pytest`; test fail thì dừng pipeline, không build.
3. **Build:** build Docker image, gắn 2 tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest`, dùng `--cache-from` image cũ để tận dụng layer cache.
4. **Push:** đẩy image lên Container Registry.
5. **Deploy:** `gcloud run deploy` image theo đúng `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), `min-instances=1` để tránh cold start, `max-instances=10`, 512Mi RAM, secret lấy từ **Secret Manager** (`--set-secrets`), không hardcode.

`service.yaml` là bản khai báo IaC của chính service Cloud Run: autoscaling 1–10 instance, `containerConcurrency: 80`, giới hạn CPU/RAM, biến môi trường và secret (`secretKeyRef`), `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready`. Mỗi bước có `waitFor`, nên thứ tự luôn là test → build → push → deploy.

## Part 4: API Security
### Exercise 4.1–4.3: Test results (401 / 200 / 429)

#### Exercise 4.1: API Key authentication (`04-api-gateway/develop/`)
Chạy server với key tự đặt (key này là "mật khẩu" của agent, không phải key LLM):
```bash
cd 04-api-gateway/develop
pip install -r requirements.txt
AGENT_API_KEY=secret-key-123 python app.py
```

**Trả lời câu hỏi:**
1. **API key được check ở đâu?** Trong hàm dependency `verify_api_key` (`app.py`, dòng 39–54). Header được đọc bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 36) và gắn vào endpoint `/ask` bằng `Depends(verify_api_key)` (dòng 70). Endpoint `/` vẫn public, không cần key.
2. **Sai key thì sao?** Thiếu header → `401 Unauthorized` (`Missing API key...`); có header nhưng sai giá trị → `403 Forbidden` (`Invalid API key.`). Request bị chặn trước khi gọi LLM.
3. **Rotate key thế nào?** Key không hardcode mà đọc từ biến môi trường `AGENT_API_KEY` (dòng 35). Muốn đổi key chỉ cần đặt giá trị mới cho biến này (hoặc trên dashboard của nền tảng) rồi restart app, không phải sửa code; sau đó báo key mới cho client. Hạn chế của cách này: key cũ hết hiệu lực ngay, nên muốn đổi không gián đoạn thì phải cho phép tạm thời nhận cả key cũ và key mới.

**Kết quả test:**

Không có key → **401**
```bash
curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
```
```text
HTTP/1.1 401 Unauthorized
server: uvicorn
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Key đúng → **200**
```bash
curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
```
```text
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Key sai → **403**
```bash
curl -i http://localhost:8000/ask -X POST -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
```
```text
HTTP/1.1 403 Forbidden
server: uvicorn
content-type: application/json

{"detail":"Invalid API key."}
```

Nhận xét: bản này phân biệt 401 (chưa xác thực) và 403 (xác thực sai). Ở Part 6, script chấm yêu cầu cả thiếu key lẫn sai key đều trả **401**, nên `06-lab-complete/app/auth.py` sẽ không dùng 403.

#### Exercise 4.2: JWT authentication (`04-api-gateway/production/`)
Tắt bản develop (cùng cổng 8000), rồi:
```bash
cd ../production
pip install -r requirements.txt
python app.py
```

**JWT flow (đọc `auth.py`):**
1. Client gửi `POST /auth/token` với username/password. `authenticate_user` kiểm tra trong `DEMO_USERS` (sai → 401 `Invalid credentials`).
2. `create_token` ký một JWT bằng thuật toán `HS256` với `JWT_SECRET` (đọc từ env). Payload gồm `sub` (username), `role`, `iat`, `exp` (hết hạn sau 60 phút).
3. Client gửi token trong header `Authorization: Bearer <token>` ở mỗi request.
4. `verify_token` giải mã và kiểm tra chữ ký + hạn dùng, **không cần tra database**. Thiếu token → 401, token hết hạn → 401, token sai chữ ký → 403. Từ payload lấy ra `username` và `role` để dùng cho rate limit và cost guard.

Lấy token (lớp K5 dùng `/auth/token` với tài khoản `student` / `demo123`):
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" \
  -d '{"username": "student", "password": "demo123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```
```text
{"access_token":"eyJhbGciOiJI...<đã che>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}
```

Không có token → **401**
```bash
curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
```
```text
HTTP/1.1 401 Unauthorized
server: uvicorn
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

Có token → **200**
```bash
curl -i http://localhost:8000/ask -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question": "Test 1"}'
```
```text
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"question":"Test 1","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000205}}
```

#### Exercise 4.3: Rate limiting
**Trả lời câu hỏi (đọc `rate_limiter.py`):**
- **Thuật toán:** *sliding window* (dạng sliding window log). Mỗi user có một `deque` lưu timestamp các request; mỗi lần check thì bỏ các timestamp cũ hơn 60 giây, đếm số còn lại, đủ limit thì trả 429.
- **Limit:** user thường **10 request / 60 giây** (`rate_limiter_user`), admin **100 request / 60 giây** (`rate_limiter_admin`).
- **Bypass cho admin:** không có bypass hoàn toàn. `app.py` chọn limiter theo `role` trong JWT (`rate_limiter_admin if role == "admin" else rate_limiter_user`), nên user có role `admin` (tài khoản demo `teacher`) được hạn mức cao hơn 10 lần.
- Khi vượt limit, response có header `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- Hạn chế: state nằm trong RAM của process, nên restart là mất và chạy nhiều instance thì mỗi instance đếm riêng. Ở Part 6 phải chuyển sang Redis.

Vòng lặp gọi liên tục bằng cùng token:
```bash
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" http://localhost:8000/ask -X POST \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"question\": \"Test $i\"}"
done
```
```text
Request 1: 200
Request 2: 200
Request 3: 200
Request 4: 200
Request 5: 200
Request 6: 200
Request 7: 200
Request 8: 200
Request 9: 200
Request 10: 429
Request 11: 429
Request 12: 429
Request 13: 429
Request 14: 429
Request 15: 429
Request 16: 429
Request 17: 429
Request 18: 429
Request 19: 429
Request 20: 429
```
Kết quả lần chạy bạn cung cấp: 9 request đầu trả `200`, từ request 10 đến 20 trả `429`. Điều này phù hợp với giới hạn 10 request trong cửa sổ 60 giây: bộ đếm sliding window tính cả request thành công trước đó trong cùng cửa sổ, nên lượt giới hạn đã gần hết khi bắt đầu vòng lặp. Khi vượt giới hạn, các request tiếp theo bị chặn cho đến khi request cũ hết khỏi cửa sổ. Vì vậy, ví dụ kết quả cũ trong mục này (chỉ request 1 trả `200`) không khớp với terminal output mới và đã được thay thế.

Response khi bị chặn → **429**
```text
HTTP/1.1 429 Too Many Requests
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795600637
retry-after: 6
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":6}}
```
### Exercise 4.4: Cost guard
**Cách làm trong `04-api-gateway/production/cost_guard.py`:**
- Mỗi user có một `UsageRecord` theo **ngày** (`day = "YYYY-MM-DD"`), đếm `input_tokens`, `output_tokens`, `request_count`. Sang ngày mới thì tạo record mới, tức là tự reset hằng ngày.
- Chi phí tính theo giá token: `input/1000 × $0.00015 + output/1000 × $0.0006` (giá tham khảo GPT-4o-mini).
- Trong `/ask`, thứ tự là: `verify_token` → `rate_limiter.check` → **`cost_guard.check_budget` trước khi gọi LLM** → gọi LLM → **`record_usage` sau khi gọi** để cộng chi phí thật.
- Hai tầng ngân sách:
  - Mỗi user **$1/ngày**: vượt → **402 Payment Required** (`Daily budget exceeded`).
  - Toàn hệ thống **$10/ngày**: vượt → **503** (tạm ngưng dịch vụ).
  - Dùng tới 80% budget thì ghi log cảnh báo.
- Kiểm tra thực tế: `GET /me/usage` của `student` sau khi test trả `{"requests":11,"input_tokens":44,"output_tokens":330,"cost_usd":0.000205,"budget_usd":1.0,"budget_remaining_usd":0.999795,"budget_used_pct":0.0}`, nên chưa thể chạm ngưỡng 402 bằng vài request mock.
- Lỗi nhỏ phát hiện được: trong `/ask`, field `usage.budget_remaining_usd` thực ra trả về `usage.total_cost_usd` (chi phí **đã dùng** 0.000205), không phải phần còn lại (0.999795 như `/me/usage`).

**Hạn chế và cách làm production (theo yêu cầu đề: $10/tháng, lưu Redis, reset đầu tháng):** bản mẫu lưu trong dict RAM nên restart là mất số liệu và nhiều instance không cộng chung được. Cách làm đúng là lưu trong Redis với key theo tháng:
```python
import redis
from datetime import datetime

r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"     # sang tháng mới → key mới → tự reset
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:          # $10/tháng
        return False                           # → endpoint trả 402
    r.incrbyfloat(key, estimated_cost)         # cộng nguyên tử, an toàn khi nhiều instance
    r.expire(key, 32 * 24 * 3600)              # tự xoá sau ~1 tháng
    return True
```

**Vì sao cần cả rate limit lẫn cost guard:** rate limit bảo vệ **tốc độ** (chặn spam, giữ server không quá tải trong ngắn hạn), còn cost guard bảo vệ **tiền** (tổng chi phí tích luỹ theo ngày/tháng). Một user gọi đều đặn dưới rate limit nhưng với câu hỏi rất dài vẫn có thể đốt hết ngân sách, nên phải có cả hai.

## Part 5: Scaling & Reliability
### Exercise 5.1: Health checks
`GET /health` là liveness probe: kiểm tra process còn phản hồi không. `GET /ready` là readiness probe: báo instance đã sẵn sàng nhận traffic chưa. Nền tảng có thể restart instance khi liveness fail; load balancer nên ngừng gửi traffic khi readiness trả `503`.

Kết quả terminal:
```text
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":1.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:09:02.885669+00:00","checks":{"memory":{"status":"ok","used_percent":11.9}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```
`in_flight_requests` bằng 1 vì middleware cũng đếm chính request `/ready`. Lưu ý: mã hiện tại vẫn trả HTTP 200 cho `/health` khi phần memory check ghi `degraded`; platform chỉ dựa vào mã HTTP sẽ không restart vì riêng trạng thái memory này.

### Exercise 5.2: Graceful shutdown
Khi nhận SIGTERM, Uvicorn ngừng nhận request mới, chờ request đang xử lý tối đa 30 giây rồi chạy phần shutdown trong lifespan. Lifespan hạ `_is_ready`, chờ `_in_flight_requests` về 0 (tối đa 30 giây) và ghi log hoàn tất. Handler SIGTERM trong app chỉ ghi log; Uvicorn đảm nhiệm quá trình shutdown.

Kết quả test đã ghi nhận: hai request `/ask` đều trả `HTTP 200`, mỗi request mất khoảng **6.06 giây**, và server thoát với **exit code 0** sau SIGTERM. Log cho thấy Uvicorn chờ các kết nối và chạy lifespan shutdown trước khi thoát.

```mermaid
sequenceDiagram
    participant P as Platform
    participant U as Uvicorn
    participant A as FastAPI app
    participant R as In-flight requests
    P->>U: SIGTERM
    U->>U: Ngừng nhận request mới, chờ request hiện tại (tối đa 30s)
    R-->>U: Hoàn thành response
    U->>A: Chạy lifespan shutdown
    A->>A: Đặt readiness = false, chờ số request về 0
    A-->>U: Shutdown complete
    U-->>P: Process thoát (exit code 0)
```

Kết quả đo được mất ~6 giây thay vì ~3 giây vì handler `async` gọi mock đồng bộ có `time.sleep(3)`, chặn event loop khiến requests chạy nối tiếp. Vì vậy, kết quả lần chạy có hai phản hồi 200 không đảm bảo mọi lịch trình sẽ giữ được mọi request: đã có lần chạy khác request thứ hai bị đóng trước khi được xử lý (curl báo HTTP 000). Để tăng độ tin cậy, không gọi hàm blocking trực tiếp trong handler async; dùng hàm sync `def` trong thread pool hoặc client async phù hợp.

### Exercise 5.3: Stateless design
Nếu lưu `conversation_history` trong RAM, mỗi instance có state riêng; request tiếp theo đến instance khác có thể không thấy lịch sử, và dữ liệu mất khi instance restart. Cách production lưu lịch sử trong Redis bằng key `session:<session_id>` với TTL **3600 giây**, nên bất kỳ instance nào cũng có thể đọc/ghi cùng session.

```mermaid
flowchart LR
    c[Client / session_id]
    subgraph instances["Agent instances — stateless"]
        a1[Agent 1]
        a2[Agent 2]
        a3[Agent 3]
    end
    r[(Redis\nsession:<id>\nTTL 1 hour)]
    c --> a1
    c --> a2
    c --> a3
    a1 <--> r
    a2 <--> r
    a3 <--> r
```

Lưu ý: ứng dụng có fallback về dictionary trong RAM nếu Redis không kết nối. Khi fallback đó được dùng, session không còn dùng chung giữa instances và không còn stateless; kết quả test bên dưới là bằng chứng về Redis/shared storage trong lần chạy đã ghi.

### Exercise 5.4: Load balancing với Nginx
Stack mở cổng **8080** ra host; client gọi `POST /chat` qua Nginx. Kết quả `docker compose ps` cho thấy ba agent đều `Up (healthy)`, Redis healthy và Nginx map `0.0.0.0:8080->80/tcp`.

```mermaid
flowchart LR
    c[Client\nlocalhost:8080]
    n[Nginx\nreverse proxy]
    subgraph net["Docker network: agent_net"]
        a1[Agent 1\n:8000]
        a2[Agent 2\n:8000]
        a3[Agent 3\n:8000]
        r[(Redis\nredis:6379)]
        a1 <--> r
        a2 <--> r
        a3 <--> r
    end
    c --> n
    n -->|proxy_pass / round robin| a1
    n --> a2
    n --> a3
```

Kết quả 10 request: `instance-5457ae` nhận 3, `instance-8686c2` nhận 3, `instance-bc4705` nhận 4. Đây là phân phối gần đều trong lần chạy đó. Nginx có `proxy_next_upstream error timeout http_503` và tối đa 3 lần thử để chuyển request khi upstream lỗi, timeout hoặc trả 503.

### Exercise 5.5: Test stateless
Kết quả `test_stateless.py`: gửi 5 câu hỏi trong cùng session; các request được phục vụ lần lượt bởi ba instance `instance-5457ae`, `instance-bc4705` và `instance-8686c2`. Khi đọc conversation history, kết quả có đủ **10 messages** (5 câu hỏi và 5 câu trả lời) đúng thứ tự.

Điều này cho thấy lịch sử hội thoại được lưu ở shared storage thay vì RAM riêng của một agent. Nếu state chỉ nằm trong RAM, request gửi tới instance khác sẽ không thấy toàn bộ lịch sử. Script kiểm tra phân phối giữa nhiều instance và lịch sử dùng chung; nó không tự dừng instance trong lúc test.

Dọn stack sau khi hoàn tất: `docker compose -p k5-day14-scaling down`.

## Part 6: Output check_production_ready.py
Chạy đầy đủ trong môi trường WSL:
```bash
cd 06-lab-complete
../.venv/bin/python check_production_ready.py
```

Kết quả: **PASS 12/12 tiêu chí · 43/43 checks passed**.

| Tiêu chí | Kết quả |
|---|---|
| Dockerfile multi-stage, dưới 500 MB | ✅ Build thành công; image **160 MB**; container chạy và `/health` trả 200 |
| Docker Compose (agent + Redis) | ✅ |
| `.dockerignore` | ✅ |
| Health check `/health` | ✅ |
| Readiness `/ready` | ✅; Redis mất kết nối thì trả 503, `/health` vẫn 200 |
| API key authentication | ✅ Key thiếu/sai trả 401; key đúng trả 200 |
| Rate limiting | ✅ Vượt giới hạn trả 429; state còn sau khi restart agent |
| Cost guard | ✅ Hết budget trả 402 |
| Cấu hình environment | ✅ |
| Structured logging | ✅ 17 dòng log JSON hợp lệ |
| Graceful shutdown | ✅ Request đang chạy vẫn trả 200; process thoát mã 0; `docker stop` thoát mã 0 trong **0,7–0,9 giây** (qua các lần chạy) |
| Railway / Render deploy config | ✅ |

Lệnh chạy `--static-only` hoặc `--skip-docker` chỉ kiểm tra một phần; kết quả trên lấy từ chế độ đầy đủ.

**Output "📋 Checklist Deliverable" (nguyên văn, chạy đầy đủ trong WSL với `os.name = posix`, Docker 29.9.3):**
```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một số dòng chi tiết đáng chú ý trong output:
```text
✅ Docker: image < 500 MB — 160 MB
✅ Khi chạy: vượt giới hạn → 429 — 429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)
✅ Khi chạy: state nằm trong Redis — restart agent vẫn bị 429
✅ Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200)
✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0
✅ Docker: `docker stop` tắt êm (exit code 0, < 10s) — exit code 0, 0.9s
```

**Vì sao `/health` trả 200 khi Redis chết còn `/ready` trả 503:** `/health` là liveness: process vẫn sống thì không nên bị platform restart, vì restart cũng không làm Redis sống lại mà còn làm mất các request đang xử lý. `/ready` là readiness: khi mất Redis, agent không làm được rate limit/cost guard/state, nên báo 503 để load balancer tạm ngừng gửi traffic vào cho tới khi Redis kết nối lại.

**Xử lý input sai:** body `/ask` được validate bằng Pydantic (`AskRequest.question: str = Field(..., min_length=1, max_length=2000)`), nên thiếu hoặc rỗng `question` thì FastAPI trả **422** với thông báo rõ ràng, không lộ stack trace.

## AI log
Công cụ: Claude (Claude Code). Không có số đo nào do AI tự đặt ra; mọi số liệu lấy từ lệnh chạy thật trên máy tôi.

| Phần | Tôi nhờ AI | AI đã làm | 
|---|---|---|
| Part 1 | Vì sao `/ask` bản production lỗi 500 | Giải thích: bản này nhận JSON body, không nhận query 
| Part 2, 4, 5 | Ghi kết quả vào bài | Tự chạy lệnh (curl, docker, `test_stateless.py`) lấy output thật và viết câu trả lời; sửa % kích thước image thành 85,9% |
| Part 6 | Hoàn thiện các TODO | Viết code (auth, rate limit, cost guard, config, log JSON, health/ready, shutdown, Dockerfile, compose, deploy config); chạy checker | 
| Part 3 | Deploy lên cloud | Hướng dẫn Railway (bị hết trial), chuyển sang Render |
| Part 7 | Đọc kết quả load test/eval, sửa KB | Đọc file JSON, điền bảng 2.1/2.2/3, chỉ ra keyword thiếu và gợi ý entry KB |