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

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
