# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Nguyễn Thị Duyên \
**Ngày chạy:** 25/11/2026 \
**Môi trường:** Windows 10 + WSL2 Ubuntu, Python 3.12, Docker Desktop

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM trả lời ~150–220 ms nên 500 ms còn dư cho retrieval và hàng đợi; quá nửa giây người dùng bắt đầu thấy chậm. Đặt theo p95 (không theo avg) để bắt được tail latency. Đây cũng là ngưỡng `--slo-p95-ms` mặc định của `load_test.py` |
| Error rate `/ask` | < 2 % | Mock LLM cố tình lỗi ~1% (503 upstream), nên 2% cho phép lỗi nền mà vẫn báo động khi lỗi tăng gấp đôi. Error budget = 2% request |
| Accuracy trên golden dataset | ≥ 80 % | Ngưỡng mặc định của quality gate (`--min-accuracy 0.8`): thấp hơn mức này thì agent trả lời sai quá nhiều. Kèm điều kiện **không có regression** so với bản trước |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.48 | 190.3 | 217.4 | 1686.7 | 1.00% (3/300 lỗi 503) | ✅ PASS |
| 10 | 44.30 | 189.3 | 219.6 | 1700.7 | 0.67% (2/300) | ✅ PASS |
| 50 | 106.16 | 192.6 | 244.3 | 1684.2 | 0.67% (2/300) | ✅ PASS |
| 100 | 62.22 | 335.1 | 2782.2 | 2972.5 | 1.00% (3/300) | ❌ FAIL (p95 > 500 ms) |

Nguồn: `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json` (mỗi mức 300 request, SLO p95 ≤ 500 ms, error rate ≤ 2%).

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Từ 1 → 10 gần như tuyến tính** (4.48 → 44.30 RPS, ×9.9) và p50/p95 gần như không đổi (~190 / ~220 ms). Lúc này agent còn dư sức, mỗi request vẫn chỉ tốn thời gian của mock LLM, nên RPS ≈ concurrency / latency (10 / 0.224 s ≈ 45).
- **Từ 10 → 50 không còn tuyến tính:** concurrency tăng 5 lần nhưng RPS chỉ tăng ~2.4 lần (44 → 106). Nếu tuyến tính thì phải ≈ 50 / 0.229 s ≈ 218 RPS. p95 bắt đầu nhích lên (219 → 244 ms) vì request bắt đầu phải xếp hàng trong một process uvicorn duy nhất.
- **Ở 100 thì vượt điểm bão hoà:** RPS còn **giảm** xuống 62, p50 tăng lên 335 ms, p95 vọt lên **2782 ms** và vi phạm SLO. Agent chỉ chạy 1 process, nên 100 request song song chủ yếu nằm chờ trong hàng đợi; thời gian chờ cộng thẳng vào latency, và chi phí chuyển ngữ cảnh làm throughput còn tệ hơn mức 50.
- **p99 luôn ~1.7 s ngay cả ở concurrency 1:** đó là ~3% request bị mock LLM làm chậm bất thường (`MOCK_SLOW_RATE=0.03`), không phải do tải. Tail latency này có sẵn trong hệ thống.
- **Kết luận:** một instance chịu tốt khoảng 10–50 request đồng thời. Muốn phục vụ 100 request đồng thời mà vẫn giữ p95 < 500 ms thì phải scale ngang (thêm worker/instance sau load balancer) hoặc giới hạn concurrency.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.7 | 217.5 | 221.7 |
| 0.03 (mặc định) | 225.2 | 219.8 | 1688.7 |
| 0.1 | 294.4 | 1680.5 | 1710.0 |

Nguồn: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json` (agent v2, 300 request, concurrency 20). SLO p95 ≤ 500 ms: ✅ ở 0 và 0.03, ❌ ở 0.1. p50 gần như không đổi ở cả ba mức (189.5 / 192.1 / 190.4 ms).

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Avg chỉ tăng từ từ:** 189.7 → 225.2 ms (+19%) → 294.4 ms (+55%). Nhìn avg thì 294 ms vẫn "trông ổn", dưới ngưỡng 500 ms.
- **p99 nhạy nhất:** chỉ cần 3% request chậm, p99 nhảy từ 221.7 lên **1688.7 ms (×7.6)**. Vì 3% > 1%, trong 100 request luôn có ít nhất 1 request rơi vào nhóm chậm (~1.7 s), nên p99 phản ánh đúng trải nghiệm của nhóm này.
- **p95 có ngưỡng gãy:** với 3% request chậm, p95 vẫn ~220 ms vì nhóm chậm nhỏ hơn 5%. Khi tăng lên 10%, nhóm chậm vượt 5% nên p95 nhảy lên **1680.5 ms** và vi phạm SLO, trong khi avg vẫn dưới 300 ms.
- **Vì sao không đặt SLO theo average:** average gộp vài request rất chậm với số đông request nhanh nên che giấu tail latency. Ở mức 0.1, avg = 294 ms vẫn "đạt", nhưng thực tế cứ 10 người thì 1 người phải chờ ~1.7 s. SLO đặt theo p95/p99 mới bảo vệ được phần người dùng gặp trải nghiệm tệ nhất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 57.4 | 109.3 | 113.7 |
| Tổng cost (USD) | 0.000408 | 0.000764 | 0.000790 |
| Cost / câu đúng (USD) | 0.00040815 | 0.00003639 | 0.00003436 |
| Latency p50 / p95 trong eval (ms) | 171.5 / 189.8 | 189.5 / 224.1 | 194.4 / 256.1 |
| Quality gate | ❌ FAIL (accuracy < 80%) | ✅ PASS (≥ 80%, so với v1 không regression) | ✅ PASS (`--min-accuracy 1.0`, so với v2 không regression) |

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json` (`--baseline reports/eval_v1.json`), `reports/eval_v2_fixed.json` (`--baseline reports/eval_v2.json --min-accuracy 1.0`).

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Thêm vào `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) entry khoá `["jwt"]`: tài liệu so sánh API key (chuỗi cố định, không tự hết hạn) với JWT (token có chữ ký số, chứa thời điểm hết hạn, server xác minh chữ ký không cần tra DB) |
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Thêm entry khoá `["hpa", "kubernetes", "autoscal"]`: tài liệu nói HPA scale số pod theo CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi) |

Nguyên nhân sai: ban đầu knowledge base không có tài liệu nào khớp keyword của 2 câu này, nên retrieval trả về rỗng và agent v2 rơi về câu trả lời chung chung ("Đây là câu trả lời từ AI agent (mock)..."). Không sửa `golden_dataset.jsonl`; sau khi tắt/bật lại v2, eval đạt 23/23 và không có câu nào bị regression so với `eval_v2.json`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 có bước retrieval (RAG) nên accuracy tăng từ 4.35% lên 91.3%, rồi 100% sau khi bổ sung tài liệu. v1 chỉ đúng 1 câu nhờ câu trả lời chung về deployment.
- **Chi phí:** v2 tốn gần **gấp đôi token mỗi câu** (57.4 → 109.3) vì prompt có thêm context, nên tổng cost tăng ~1.9 lần (0.000408 → 0.000764 USD). Nhưng **cost / câu đúng giảm ~11 lần** (0.000408 → 0.0000364 USD) vì v2 trả lời đúng nhiều hơn rất nhiều. Đây là chỉ số đúng để so sánh hai phiên bản: trả tiền cho câu trả lời sai là lãng phí.
- **Latency:** v2 chậm hơn một chút (p50 171.5 → 189.5 ms, p95 189.8 → 224.1 ms) do thêm bước retrieval và prompt dài hơn, nhưng vẫn nằm xa dưới SLO 500 ms. Bổ sung 2 tài liệu chỉ tăng nhẹ token (109.3 → 113.7).
- **Kết luận:** đánh đổi đáng giá: tốn thêm token và vài chục ms để chất lượng tăng từ gần 0 lên 100%.

**Quality gate trong CI (chặn merge bằng exit code):** `run_eval.py` trả **exit code 0** khi đạt và **exit code 1** khi accuracy dưới `--min-accuracy` hoặc có câu bị regression so với `--baseline`. Trong GitHub Actions, một bước có exit code khác 0 sẽ làm job fail; đặt job này là *required status check* của nhánh `main` thì PR làm giảm chất lượng sẽ không merge được:

```yaml
# .github/workflows/eval.yml
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Run agent + eval
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```
(`MOCK_ERROR_RATE=0` để lỗi ngẫu nhiên của mock không làm job fail oan.)

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): `screenshots/grafana-dashboard.png` (Locust 30 user, 3 instance: traffic 3.5 req/s ở thời điểm chụp, error rate 1.05%, p95 294.90 ms, Instances = 3)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): `screenshots/jaeger-slow-trace.png` (trace `63fbbfb…`, 1.7 s, span `chat mock-llm-small` chiếm 98.5%)
- [x] Một trace lỗi trong Jaeger (có event `exception`): `screenshots/jaeger-error-trace.png` (trace `4bbd270…`, 503, `exception.type = utils.mock_llm.LLMError`)
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**: `screenshots/prometheus-alert-firing.png` (`AgentHighErrorRate` và `AgentHighLatencyP95` cùng FIRING)

**Trả lời Exercise 7.4:**
1. **p95 vs avg:** p95 khoảng 220–295 ms trong khi p50 ~190 ms và avg chỉ ~230 ms; p99 lại ~1.7 s. Khoảng cách lớn giữa avg/p95 và p99 cho thấy **tail latency**: đa số request nhanh, nhưng một nhóm nhỏ (~3% do `MOCK_SLOW_RATE`) rất chậm. Avg che mất nhóm này.
2. **Requests/s theo instance:** Nginx (`server agent:8000 resolve`, round-robin) chia traffic **gần đều** cho các instance; panel cho thấy các đường ở mức tương đương nhau.
3. **Input tokens/s > output tokens/s:** agent v2 nhét context từ retrieval vào prompt nên prompt (input) dài hơn câu trả lời (output). Ví dụ một request: `input_tokens = 74–91`, `output_tokens = 37–55`.
4. **`curl http://localhost:8080/metrics`:** trả **404**. Nginx không public `/metrics` ra ngoài (tránh lộ thông tin nội bộ và để người ngoài không spam endpoint này). Prometheus scrape trực tiếp từng agent qua mạng Docker nội bộ (`dns_sd_configs`), không đi qua Nginx.

**Ghi chú sửa lỗi khi dựng stack:** container agent ban đầu crash liên tục (`ModuleNotFoundError: No module named 'uvicorn'`) vì user `agent` có HOME là `/app` (`useradd -d /app`) nên Python tìm package ở `/app/.local`, trong khi package được copy vào `/home/agent/.local`. Đã sửa `production/Dockerfile` bằng `ENV PYTHONUSERBASE=/home/agent/.local`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | **~1 phút 30 giây**: đổi cấu hình lúc 23:09:06 → pending 23:09:36 → **firing 23:10:36** | Golden Signals → *Error rate* chuyển đỏ (đo được 17.6–20.5% so với ngưỡng 5%); *Requests/s theo status code* thấy đường 503 tăng |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | **~2 phút 25 giây**: đổi lúc 23:09:06 → pending 23:09:27 → **firing 23:11:31** | *Latency p95* chuyển đỏ (p95 đo được ~1.89–1.90 s); biểu đồ p50/p95/p99 thấy p95 nhảy lên sát p99 |
| C | `LLM_MODEL=mock-llm-large` | Không chạy riêng thí nghiệm này. Tuy vậy `LLMCostBurnRateHigh` đã **firing từ 22:38:26 đến 23:10:36** chỉ vì tải Locust liên tục (cost ước tính > $2/giờ) | — | *LLM cost* (ô Golden Signals màu cam, ~$0.59 → $1.17 trong 1 giờ) |
| D | `docker pause` 1 instance | Không thực hiện | — | — |
| E | `AGENT_VERSION=v1` | Không thực hiện (theo đề: không alert nào firing) | — | — |

**Cách làm A và B:** chạy cùng lúc trong một lần đổi cấu hình (`cp .env.example .env`, đặt `MOCK_ERROR_RATE=0.2` và `MOCK_SLOW_RATE=0.3`, rồi `docker compose -p k5-day14-observability up -d --scale agent=3`), Locust giữ 30 user. Mốc "đổi cấu hình" lấy theo thời điểm container agent khởi động lại (23:09:06, `docker inspect .State.StartedAt`); thời điểm pending/firing lấy từ series `ALERTS{alertstate=...}` trong Prometheus. Chụp xong thì xoá `.env` và `up -d` lại để trả về cấu hình mặc định.

**Phân tích:**
- Thời gian tới khi firing = thời gian chờ metric phản ánh sự cố (cửa sổ `rate(...[1m])` cần ~30 giây để vượt ngưỡng) **cộng** thời gian `for` của rule (1 phút với error rate, 2 phút với p95). Alert không kêu ngay lập tức là có chủ đích: tránh báo động vì một spike ngắn (alert fatigue).
- `AgentHighErrorRate` firing trước vì `for` ngắn hơn: lỗi làm hỏng request ngay, cần phản ứng nhanh. Latency đặt `for` dài hơn vì p95 dao động nhiều hơn.
- `LLMCostBurnRateHigh` firing chỉ vì tải liên tục, không phải sự cố. Ngưỡng $2/giờ hợp với traffic thật của lab, nhưng khi load test thì nên tạm silence hoặc chỉnh ngưỡng theo traffic dự kiến. Nó tự hết firing lúc 23:10:36, khi lỗi + chậm làm throughput (và cost) giảm.
- **Unit test alert rules** (alert cũng là code, cần test như code): kiểm tra logic rule bằng dữ liệu giả lập, không cần chờ sự cố thật.

  ```text
  $ docker run --rm -v "$PWD/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml
  Processing test file: /p/alert_rules_test.yml
    SUCCESS
  ```

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi sang v1 làm **chất lượng câu trả lời** giảm mạnh (accuracy 4.35% so với 91.3–100% ở mục 3), nhưng request vẫn trả 200 nhanh và rẻ hơn, nên các metric hạ tầng (error rate, latency, instance up) đều xanh. Cần thêm lớp giám sát **chất lượng**:
1. **Quality gate trong CI/CD** (`run_eval.py --min-accuracy ... --baseline ...`, exit code 1): chặn phiên bản kém trước khi deploy.
2. **Eval định kỳ / synthetic check trên production:** chạy golden dataset vào endpoint thật (ví dụ mỗi giờ), xuất accuracy thành metric và đặt alert khi accuracy giảm.
3. **Theo dõi metric gián tiếp của chất lượng:** ví dụ `retrieval hit ratio` giảm về 0, token/câu giảm đột ngột, bảng "version đang chạy" đổi; gắn label `version` để so sánh trước và sau deploy.
4. **Tín hiệu từ người dùng:** thumbs up/down, tỉ lệ hỏi lại; với LLM thật có thể dùng LLM-as-judge chấm một phần traffic.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `63fbbfbacc28ce59181aff0f32f7ad3f` (ảnh `screenshots/jaeger-slow-trace.png`)
- Tổng thời gian: **1681.2 ms** (span gốc `POST /ask`, HTTP 200)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small` (1656.8 ms, ≈ 98.5%)**, tức lệnh gọi LLM (`gen_ai.request.model = mock-llm-small`, `gen_ai.usage.input_tokens = 74`, `output_tokens = 37`)

| Span | Thời gian | % tổng |
|---|---:|---:|
| `POST /ask` | 1681.2 ms | 100% |
| └ `agent.run` | 1679.2 ms | 99.9% |
| &nbsp;&nbsp;&nbsp;├ `agent.retrieve_context` | 21.8 ms | 1.3% |
| &nbsp;&nbsp;&nbsp;└ `chat mock-llm-small` | 1656.8 ms | 98.5% |

- Dòng log tương ứng (grep theo `trace_id`):

```bash
docker compose -p k5-day14-observability logs agent --no-log-prefix | grep 63fbbfbacc28ce59181aff0f32f7ad3f
```

```json
{"ts": "2026-11-25T15:58:59.866321+00:00", "level": "INFO", "service": "observable-agent", "instance": "422a707656de", "event": "llm_call", "trace_id": "63fbbfbacc28ce59181aff0f32f7ad3f", "span_id": "9d8f5b7adcb5b530", "request_id": "34151c86ff48", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1656.7}
{"ts": "2026-11-25T15:58:59.866871+00:00", "level": "INFO", "service": "observable-agent", "instance": "422a707656de", "event": "http_request", "trace_id": "63fbbfbacc28ce59181aff0f32f7ad3f", "span_id": "9d8f5b7adcb5b530", "request_id": "34151c86ff48", "method": "POST", "route": "/ask", "status": 200, "ms": 1680.6}
```

**Kết luận:** log và trace khớp nhau (`llm_ms = 1656.7` ≈ span `chat` 1656.8 ms; `ms = 1680.6` ≈ span gốc 1681.2 ms). Request chậm vì **lệnh gọi LLM upstream chậm bất thường** (thuộc ~3% request bị `MOCK_SLOW_RATE` làm chậm); code của agent (retrieval 21.8 ms) không phải nguyên nhân. Hướng xử lý nằm ở phía LLM: đặt timeout/retry, fallback sang model khác, hoặc streaming để người dùng thấy phản hồi sớm.

**Trace lỗi** (ảnh `screenshots/jaeger-error-trace.png`, tìm bằng attribute `error=true`):

- `trace_id`: `4bbd270a3e07063a4baa11702a3e238b`, tổng **864.3 ms**, `http.status_code = 503`
- Span `chat mock-llm-small` (843.0 ms) có status **ERROR** và event **`exception`**:
  - `exception.type = utils.mock_llm.LLMError`
  - `exception.message = Upstream LLM error: 503 Service Unavailable (mock)`
- Lỗi lan lên `agent.run` (cũng có event `exception`) rồi tới span gốc `POST /ask` → agent trả 503 cho client. `agent.retrieve_context` (19.2 ms) không lỗi.
- Log cùng `trace_id`:

```json
{"ts": "2026-11-25T16:03:32.979940+00:00", "level": "INFO", "service": "observable-agent", "instance": "3fde384aa5b0", "event": "llm_error", "trace_id": "4bbd270a3e07063a4baa11702a3e238b", "span_id": "bf08be7d74437c3d", "request_id": "84b33d76a8d9", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T16:03:32.980187+00:00", "level": "INFO", "service": "observable-agent", "instance": "3fde384aa5b0", "event": "http_request", "trace_id": "4bbd270a3e07063a4baa11702a3e238b", "span_id": "bf08be7d74437c3d", "request_id": "84b33d76a8d9", "method": "POST", "route": "/ask", "status": 503, "ms": 863.9}
```

→ Lỗi đến từ LLM upstream (mock cố tình lỗi ~1% với `MOCK_ERROR_RATE=0.01`), không phải từ code agent. Nhờ `trace_id` có trong cả log lẫn trace, đi từ dòng log `llm_error` sang đúng trace trong Jaeger chỉ mất một lần tìm.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 60.30 | 190 | 230 | 1700 | 61 / 7197 (0.85%), toàn bộ là 503 |
| 3 | 59.99 | 190 | 220 | 1700 | 65 / 7160 (0.91%), toàn bộ là 503 |

Nguồn: dòng `POST /ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv` (Locust headless `-u 100 -r 10 -t 2m`); số lỗi lấy từ `scale_1_failures.csv` và `scale_3_failures.csv`. Tính cả `GET /health`, Locust đo tổng (Aggregated) 65.98 và 65.95 RPS.

**Ghi chú về cách đo:** lần đo đầu bị sai vì `docker compose run --rm locust` (không có `--no-deps`) tự khởi động lại service phụ thuộc theo `deploy.replicas: 2`, ghi đè `--scale`. Truy vấn Prometheus `count(up{job="agent"}==1)` cho thấy cả hai lần chạy đều chỉ có 2 instance. Đã chạy lại bằng `docker compose run --rm --no-deps locust ...`; Prometheus xác nhận **1 instance** suốt lần `scale_1` (22:47:28–22:49:26) và **3 instance** suốt lần `scale_3` (22:51:35–22:53:20).

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance gần như không thay đổi gì:** RPS ~60 ở cả hai lần, p50 190 ms, p95 230 → 220 ms (chỉ giảm 10 ms, nằm trong sai số), p99 1700 ms.
- **Lý do 1: tải bị giới hạn bởi Locust, không phải bởi agent.** Mỗi user Locust chờ `between(0.5, 2)` giây (trung bình 1.25 s) giữa hai request. Với latency ~0.23 s, mỗi user gửi khoảng 1 / (1.25 + 0.23) ≈ 0.68 request/s, nên 100 user chỉ tạo khoảng **68 request/s**, đúng bằng mức ~66 RPS đo được. Ở tải này một instance chưa bão hoà (p95 220 ms, xa dưới SLO 500 ms), nên thêm instance không có gì để cải thiện.
- **Lý do 2: latency do LLM quyết định.** p50 ~190 ms gần như bằng độ trễ của mock LLM (`MOCK_LATENCY_MS=120` cộng phần ngẫu nhiên); p99 ~1700 ms là ~3% request bị mock làm chậm (`MOCK_SLOW_RATE=0.03`). Thêm instance không làm từng lệnh gọi LLM nhanh hơn, nên **nút thắt về latency nằm ở LLM (upstream)**, không ở agent hay Nginx.
- **Lỗi ~1%** đều là `503 Service Unavailable` do mock LLM cố tình lỗi (`MOCK_ERROR_RATE=0.01`): 61/7197 ≈ 0.85% và 65/7160 ≈ 0.91%. Đây không phải lỗi do quá tải và vẫn dưới SLO 2%.
- **Khi nào scale mới có ích:** khi một instance bị bão hoà (như load test develop ở concurrency 100: p95 lên 2782 ms). Muốn thấy hiệu quả scale ở đây phải tăng số user hoặc bỏ thời gian chờ của Locust. Lúc đó 3 instance sẽ chia hàng đợi và giữ p95 thấp hơn, nhưng vẫn không thể nhanh hơn giới hạn của LLM.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Phải nhìn percentile, không nhìn trung bình.** Với `MOCK_SLOW_RATE=0.1`, avg chỉ 294 ms (trông vẫn "đạt"), nhưng p95 đã 1680 ms; ngay cả khi chỉ 3% request chậm, p99 cũng tăng gấp ~7.6 lần (221 → 1689 ms). SLO và alert phải đặt theo p95/p99 thì mới bảo vệ được nhóm người dùng gặp trải nghiệm tệ nhất.
  2. **Hiệu năng và chất lượng là hai phép đo khác nhau, cần cả hai.** Load test cho biết agent nhanh tới đâu (1 instance bão hoà quanh 50–100 request đồng thời: p95 2782 ms ở concurrency 100). Eval cho biết agent đúng tới đâu (v1 4.35% → v2 91.3% → 100% sau khi sửa knowledge base). Đổi sang v1 thì mọi metric hạ tầng vẫn xanh, chỉ eval mới bắt được, nên quality gate (exit code của `run_eval.py`) phải nằm trong CI. So sánh hai phiên bản nên dùng **cost / câu đúng** (v2 tốn gần gấp đôi token nhưng rẻ hơn ~11 lần trên mỗi câu đúng).
  3. **Metrics, traces và logs bổ sung cho nhau, và số liệu phải được kiểm chứng.** Dashboard báo p95 tăng → Jaeger chỉ ra span `chat mock-llm-small` chiếm 98.5% thời gian → grep `trace_id` trong log JSON thấy `llm_ms = 1656.7` khớp với trace: nút thắt là LLM upstream, không phải code agent. Cũng nhờ hỏi lại Prometheus (`count(up{job="agent"}==1)`) mà phát hiện lần benchmark scale đầu tiên thực ra chạy với 2 instance (do `docker compose run` thiếu `--no-deps`), phải đo lại. Scale 1 → 3 instance không cải thiện p95 (230 → 220 ms) vì tải bị giới hạn bởi Locust và latency do LLM quyết định: thêm instance chỉ có ích khi một instance đã bão hoà.

- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - **Giám sát chất lượng:** chạy eval định kỳ trên golden dataset vào endpoint production, xuất `agent_eval_accuracy` thành metric và alert khi giảm dưới 85% hoặc giảm so với phiên bản trước; theo dõi `retrieval hit ratio` và alert khi về 0 (dấu hiệu knowledge base/retrieval hỏng, như thí nghiệm E).
  - **Giám sát từ bên ngoài:** synthetic check gọi `/health` và một câu `/ask` mẫu từ ngoài cloud mỗi phút, cộng metric ở tầng load balancer (tỉ lệ 502/504 của Nginx). Theo mô tả thí nghiệm D trong README (không chạy trong bài này), lỗi 504 xảy ra ở Nginx không hiện trên metric của agent vì agent chưa từng xử lý xong request đó.
  - **LLM upstream:** alert riêng cho tỉ lệ lỗi và p95 của `llm_request_duration_seconds` theo model, để phân biệt "LLM chậm/lỗi" với "agent lỗi"; kèm timeout, retry và fallback model.
  - **Chi phí và tài nguyên:** alert ngân sách theo ngày/tháng (không chỉ burn rate mỗi giờ), alert khi gần chạm cost guard; theo dõi saturation (`agent_in_flight_requests`, CPU/RAM container) để autoscale trước khi p95 vượt SLO.
  - **Vận hành alert:** dùng Alertmanager gửi Slack/PagerDuty, chia mức `warning`/`critical`, silence khi chạy load test, và tính error budget burn rate theo SLO 30 ngày thay vì chỉ ngưỡng tức thời.
