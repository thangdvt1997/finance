# THIRD_PARTY_ALL — giấy phép phần mềm bên thứ ba (hợp nhất)

Cập nhật: 2026-10-14. Hợp nhất từ: `services/web-ui/THIRD_PARTY.md`, `package.json` (web-ui, client-ui), `pyproject.toml` + metadata thực tế của gói Python **đang chạy trong container trên VPS** (đọc bằng `importlib.metadata`), file compose (`image:`), `docs/OSS_REUSE.md`, `services/nlp/README.md`, `services/briefing/README.md`.

> **Đây không phải tư vấn pháp lý.** Mục đích: biết rõ có thành phần nào **không phải giấy phép mở được OSI công nhận** hoặc có **điều kiện đặc biệt** để quyết định trước khi phát hành/thương mại hoá. Hệ thống hiện chạy **nội bộ, cho nhóm nhỏ, không phân phối lại phần mềm**; nhiều ràng buộc copyleft (AGPL/GPL) chủ yếu phát sinh khi **sửa mã rồi cung cấp dịch vụ qua mạng cho người khác** hoặc **phân phối lại**. Trước khi cung cấp cho bên thứ ba/thương mại hoá, hãy nhờ luật sư rà soát danh sách này.

## 1. CẢNH BÁO — cần quyết định hoặc theo dõi

Mức: **ĐỎ** = không phải giấy phép OSS, hoặc cấm sử dụng thương mại/phân phối lại — phải xử lý trước khi thương mại hoá; **CAM** = copyleft mạnh/mạng (AGPL/SSPL/RSAL) — ổn nếu dùng nội bộ nguyên bản, cần xem xét khi sửa đổi hoặc cung cấp dịch vụ; **VÀNG** = giấy phép chưa khai báo hoặc điều kiện nhẹ cần lưu ý.

| Mức | Thành phần | Dùng ở đâu | Giấy phép | Vấn đề và khuyến nghị |
|---|---|---|---|---|
| ĐỎ | **vnstock** 4.0.9 + **vnai** 2.6.3 | `market-collector` (provider vnstock tuỳ chọn, cài khi build với `WITH_VNSTOCK=1` — **đang có trong image chạy**) và seed của `vn-market` (ngành/rổ chỉ số) | "Custom (Personal Use)" — **không phải OSI**; vnai: "proprietary" | Bản Cộng đồng miễn phí cho **cá nhân/học tập**, cấm phân phối lại và dựng sản phẩm bán truy xuất dữ liệu nếu không có thỏa thuận (`OSS_REUSE.md`). Dùng nội bộ cá nhân thì ổn; **không** thương mại hoá/chia sẻ dữ liệu. Phương án thay: build lại với `WITH_VNSTOCK=0` (provider tự tắt, dữ liệu VN dùng VNDirect finfo) hoặc SSI FastConnect/DNSE khi có hợp đồng. |
| ĐỎ | **TimescaleDB** (image `timescale/timescaledb:2.30.2-pg16`) — phần nén, continuous aggregate | DB chính (nén bật ở migration 009) | Nhân Apache-2.0; tính năng nén/continuous aggregate/… thuộc **Timescale License (TSL)** — không phải OSI | TSL cho phép dùng/sửa nội bộ, **cấm** cung cấp TimescaleDB như dịch vụ DB (DBaaS). Dự án chỉ dùng như thành phần nội bộ: ổn. Cần đọc lại bản TSL hiện hành khi thương mại hoá (`OSS_REUSE.md`: "chưa đọc lại bản hiện hành"). Phương án: bản Apache-only (mất nén) hoặc PostgreSQL thuần. |
| ĐỎ | **Mô hình ViSoBERT** `5CD-AI/Vietnamese-Sentiment-visobert` (và base `uitnlp/visobert`) | `nlp` — cảm xúc tiếng Việt | **Không khai báo license** trên thẻ Hugging Face | Không có quyền sử dụng rõ ràng. `nlp/README.md` cảnh báo "kiểm tra trước khi dùng thương mại". Phương án: liên hệ tác giả, hoặc chuyển tiếng Việt sang từ điển VADER+tài chính (đã có `fallback`, cấu hình `NLP_MODEL_VI` — xem `nlp/README.md`). |
| CAM | **Redis 7.4.5** (container `redis-cache`, image `redis:7-alpine`) | Cache gateway | Redis 7.4+: **RSALv2 hoặc SSPLv1** — không phải OSI | Dùng nội bộ ổn; không cung cấp Redis như dịch vụ cho bên khác. Phương án: **Valkey** (BSD-3, cùng giao thức) hoặc Redis 8 chọn AGPLv3. |
| CAM | **Redis 8.10.2** (container `redis`, bus) | Bus Redis Streams | Redis 8: tri-license RSALv2 / SSPLv1 / **AGPLv3** | Có lựa chọn AGPLv3 (OSI). Dùng nguyên bản nội bộ: ổn. Sửa mã Redis và cung cấp qua mạng cho người khác → phải công bố mã sửa. Phương án: Valkey. |
| CAM | **Grafana 12.4** | Dashboard (`127.0.0.1:3300`) | **AGPL-3.0** | Chỉ dùng nguyên bản như công cụ vận hành, không sửa mã: ổn. Nếu sửa và cung cấp cho người ngoài → phải công bố mã. Không nhúng vào sản phẩm phân phối. |
| CAM | **Dịch vụ ghi trong tài liệu nhưng không nhúng**: Loki, Renovate, Ghostfolio, Wealthfolio, FinceptTerminal, backtesting.py, Metabase (AGPL); Redpanda (BSL 1.1); Airbyte (Elastic 2.0); vectorbt (Apache-2.0 + **Commons Clause**); FreqUI (GPL-3.0); HashiCorp Vault (BSL) | **Không dùng trong mã/dịch vụ chạy** (chỉ khảo sát hoặc dùng làm tham khảo thiết kế, hoặc chạy ngoài repo như nghiên cứu) | Như ghi | **Không đưa vào repo/image.** vectorbt chỉ được phép quét ý tưởng nội bộ; tuyệt đối không bán sản phẩm/dịch vụ có giá trị chính là vectorbt. Renovate nếu dùng chỉ là công cụ PR. |
| VÀNG | **pyphen** (phụ thuộc của WeasyPrint — `reporter`) | PDF báo cáo | GPLv2+ **hoặc** LGPLv2.1+ **hoặc** MPL-1.1 (đa giấy phép) | Chọn LGPL/MPL → phù hợp dùng như thư viện không sửa. Nếu phân phối image `reporter`, kèm thông báo giấy phép. |
| VÀNG | **MPL-2.0** gói: `pywebpush`, `py-vapid`, `certifi`, `orjson` (MPL-2.0 AND (Apache-2.0 OR MIT)), `tqdm` (MPL-2.0 AND MIT) | `alert-rules`, `api-gateway`, nhiều service | MPL-2.0 (copyleft theo từng file) | Dùng nguyên bản: ổn. Nếu sửa chính các file MPL → phải công bố các file đó. |
| VÀNG | **llama.cpp** (image `ghcr.io/ggml-org/llama.cpp:server`, ghim digest) + mô hình **Qwen3.5-9B** GGUF | `briefing-llm` | llama.cpp MIT; Qwen3.5: **Apache-2.0** theo bảng đo trong `briefing/README.md` | Hợp lệ. Mô hình khác (Gemma/Llama) **không dùng** vì giấy phép hạn chế. Xác nhận lại giấy phép mô hình khi đổi `BRIEFING_LLM_FILE`. |
| VÀNG | **FinBERT** (`ProsusAI/finbert` qua `Xenova/finbert` ONNX) | `nlp` tiếng Anh | Apache-2.0 theo repo GitHub ProsusAI/finBERT; **thẻ HF không khai báo** | Chấp nhận theo repo gốc; nên lưu bằng chứng giấy phép repo gốc. |
| VÀNG | **lightweight-charts** (TradingView) | Biểu đồ nến (web-ui, client-ui) | Apache-2.0 **kèm yêu cầu attribution**: giữ logo/liên kết TradingView trên biểu đồ | Giữ nguyên logo như đang làm. Không gỡ. |
| VÀNG | **Dữ liệu và điều khoản nguồn** (không phải giấy phép phần mềm): `yfinance` (Apache-2.0 nhưng dữ liệu Yahoo chỉ cho cá nhân), VNDirect finfo (không chính thức), Dukascopy, GDELT, các feed RSS, nguồn chuyên gia | Collector | Điều khoản từng nguồn (`FREE_STACK.md`: "chỉ dùng cá nhân/nội bộ, không phân phối lại") | Đây là lý do của ADR-009 (ẩn tên nguồn) và ADR-010. Không bán/chia sẻ lại dữ liệu thô. Free tier có thể đổi điều khoản bất cứ lúc nào. |
| VÀNG | **Image Linux nền** (`python:3.12-slim` Debian, `alpine`) | Hầu hết container | Nhiều giấy phép (GPL/LGPL cho tiện ích hệ thống Debian/Alpine) | Chuẩn cho container; không phân phối lại thì không phát sinh nghĩa vụ. |

Đã **loại có chủ đích** vì giấy phép: Loughran-McDonald (thương mại hạn chế), Gemma/Llama (hạn chế), Redpanda/Airbyte/Vault (không OSS thật), mã nguồn của FreqUI/Ghostfolio/Wealthfolio (copyleft — chỉ xem ý tưởng, **không lấy mã**; xem `services/web-ui/THIRD_PARTY.md`).

## 2. Hạ tầng và image Docker (từ compose)

| Thành phần | Phiên bản | Giấy phép | Ghi chú |
|---|---|---|---|
| TimescaleDB / PostgreSQL 16 | 2.30.2 / 16.15 | Apache-2.0 + **TSL**; PostgreSQL License | Xem cảnh báo ĐỎ |
| Redis (bus) | 8.10.2 | RSALv2 / SSPLv1 / AGPLv3 | CAM |
| Redis (cache) | 7.4.5 | RSALv2 / SSPLv1 | CAM |
| Prometheus | v3.13.4 | Apache-2.0 | |
| Alertmanager | v0.34.1 | Apache-2.0 | |
| node_exporter | v1.9.1 | Apache-2.0 | `textfile-exporter` + host |
| postgres_exporter | v0.18.1 | Apache-2.0 | |
| redis_exporter | v1.80.1 | MIT | |
| cAdvisor | v0.53.0 | Apache-2.0 | |
| Grafana | 12.4.12 | **AGPL-3.0** | CAM |
| Jaeger | 2.11.0 | Apache-2.0 | |
| Gatus | v5.37.0 | Apache-2.0 | |
| Dozzle | v11.3.1 | MIT | |
| ntfy | v2.29.0 | Apache-2.0 / GPLv2 (đa giấy phép) | |
| docker-socket-proxy (Tecnativa) | 0.3.0 | Apache-2.0 | |
| nginx-unprivileged (web-ui, client-ui) | 1.27 | BSD-2-Clause | |
| llama.cpp server | build 11552 (ghim digest) | MIT | |
| cloudflared (host, quick tunnel) | — | Apache-2.0 | dịch vụ Cloudflare theo điều khoản của Cloudflare |
| Wine + MT4/MT5 (lab `mtlab-*`, ngoài project) | — | MetaQuotes: **phần mềm độc quyền** | chỉ dùng cho lab biên dịch/kiểm thử EA; không phân phối lại |

## 3. Frontend (web-ui và client-ui) — từ `package.json` + `services/web-ui/THIRD_PARTY.md`

Phiên bản cố định trong `app/package-lock.json`; bản build đóng gói sẵn, **không tải gì từ CDN lúc chạy**.

| Thành phần | Giấy phép | Dùng cho |
|---|---|---|
| lightweight-charts 5.x | Apache-2.0 (+attribution) | biểu đồ nến, công cụ vẽ (Series Primitive API) |
| Apache ECharts 6.x | Apache-2.0 | biểu đồ equity, heatmap |
| indicatorts 2.2.2 | MIT | chỉ báo (phần còn lại tự viết) |
| React 19, react-dom | MIT | UI |
| TanStack Query 5 / Table 8 | MIT | dữ liệu, bảng |
| Radix UI (Tabs, Tooltip) | MIT | thành phần truy cập được |
| react-grid-layout 2.x (+react-draggable, react-resizable) | MIT | lưới widget Terminal |
| html-to-image | MIT | xuất ảnh PNG widget |
| qrcode-generator 1.4.4 | MIT | QR TOTP (vẽ trong trình duyệt) |
| Tailwind CSS 4 | MIT | CSS |
| Vite 8 (+ @vitejs/plugin-react, @tailwindcss/vite) | MIT | build |
| lucide-react | ISC | icon |
| clsx, tailwind-merge | MIT | tiện ích class |
| Inter (`@fontsource-variable/inter`), JetBrains Mono (`@fontsource/jetbrains-mono`) | OFL-1.1 | font |

Đã xem xét nhưng không dùng: `technicalindicators`, `trading-signals`, `lightweight-charts-indicators`. Không có thành phần GPL/AGPL nào trong gói frontend.

## 4. Mô hình AI

| Mô hình | Dùng ở | Giấy phép | Ghi chú |
|---|---|---|---|
| FinBERT int8 ONNX | nlp (en) | Apache-2.0 (repo gốc) | thẻ HF không khai báo |
| ViSoBERT sentiment int8 ONNX | nlp (vi) | **không khai báo** | ĐỎ — xem trên |
| VADER + từ vựng tài chính tự biên | nlp (dự phòng) | MIT / tự viết | không dùng Loughran-McDonald |
| Qwen3.5-9B GGUF Q4_K_M | briefing-llm | Apache-2.0 | xác nhận lại khi đổi mô hình |

## 5. Mã tự viết trong repo
`libs/common`, các `services/*`, `mt-agent` (EA MQL4/MQL5), `infra/` là mã của dự án (chưa gắn tệp LICENSE — **cần chủ sở hữu quyết định giấy phép trước khi chia sẻ**). EA biên dịch bằng MetaEditor của MetaQuotes.

## 6. Python — toàn bộ gói đang chạy trong container (đọc từ VPS 2026-10-14)

| Gói | Phiên bản | Giấy phép |
|---|---|---|
| aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT |
| aiohttp-fast-zlib | 0.3.0 | Apache-2.0 |
| aiosignal | 1.4.0 | Apache 2.0 |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| apprise | 2.0.1 | BSD-2-Clause |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.1.0 | MIT |
| asgiref | 3.12.1 | BSD-3-Clause |
| asyncpg | 0.32.0 | Apache-2.0 |
| attrs | 26.1.0 | MIT |
| beautifulsoup4 | 4.15.0 | MIT License |
| Bottleneck | 1.6.0 | Simplified BSD |
| brotli | 1.2.0 | MIT |
| ccxt | 4.5.85 | MIT |
| certifi | 2026.6.17 / 2026.7.22 | MPL-2.0 (MPL, xem mục 1) |
| cffi | 2.0.0 / 2.1.1 | MIT |
| charset-normalizer | 3.4.7 / 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| coincurve | 21.0.0 | MIT OR Apache-2.0 |
| contourpy | 1.4.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| cssselect2 | 0.10.1 | BSD License |
| cycler | 0.12.1 | BSD License |
| defusedxml | 0.7.1 | PSFL |
| empyrical-reloaded | 0.5.12 | Apache License |
| et_xmlfile | 2.0.0 | MIT |
| fastapi | 0.143.0 | MIT |
| feedparser | 6.0.14 | BSD-2-Clause |
| feedparser-sgmllib | 2.1.0 | PSF-2.0 |
| filelock | 4.1.1 | MIT |
| flatbuffers | 25.12.19 | Apache 2.0 |
| fonttools | 4.66.1 | MIT |
| frozenlist | 1.8.0 | Apache-2.0 |
| fsspec | 2026.9.0 | BSD-3-Clause |
| googleapis-common-protos | 1.75.5 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| hf-xet | 1.7.0 | Apache-2.0 |
| hiredis | 3.4.2 | MIT |
| http_ece | 1.2.1 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.13.1 | BSD-3-Clause |
| huggingface_hub | 2.2.0 | Apache-2.0 |
| icalendar | 7.3.0 | BSD-2-Clause |
| idna | 3.18 / 3.20 | BSD-3-Clause |
| importlib_metadata | 9.0.1 | Apache-2.0 |
| Jinja2 | 3.1.6 | BSD License |
| kiwisolver | 1.5.1 | BSD License |
| Markdown | 3.11 | BSD-3-Clause |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| matplotlib | 3.11.2 | PSF-based (matplotlib License) |
| mplfinance | 0.12.10b0 | BSD-style |
| multidict | 6.7.1 / 7.1.0 | Apache License 2.0 |
| numpy | 2.2.6 / 2.5.4 | BSD-3-Clause (+0BSD/MIT/Zlib/CC0 bundled) |
| oauthlib | 4.0.0 | BSD-3-Clause |
| onnxruntime | 1.31.0 | MIT License |
| openpyxl | 3.1.5 | MIT |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| opentelemetry-exporter-http-transport | 0.66b1 | Apache-2.0 |
| opentelemetry-exporter-otlp-common | 0.66b1 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-common | 1.45.1 | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-http | 1.45.1 | Apache-2.0 |
| opentelemetry-instrumentation | 0.66b1 | Apache-2.0 |
| opentelemetry-instrumentation-asgi | 0.66b1 | Apache-2.0 |
| opentelemetry-instrumentation-asyncpg | 0.66b1 | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | 0.66b1 | Apache-2.0 |
| opentelemetry-instrumentation-httpx | 0.66b1 | Apache-2.0 |
| opentelemetry-instrumentation-redis | 0.66b1 | Apache-2.0 |
| opentelemetry-proto | 1.45.1 | Apache-2.0 |
| opentelemetry-sdk | 1.45.1 | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b1 | Apache-2.0 |
| opentelemetry-util-http | 0.66b1 | Apache-2.0 |
| orjson | 3.11.9 / 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) (MPL, xem mục 1) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 2.3.3 / 3.0.6 | BSD 3-Clause License |
| peewee | 3.17.3 | MIT License |
| pillow | 12.3.0 | MIT-CMU |
| pip | 25.0.1 | MIT |
| prometheus_client | 0.26.0 | Apache-2.0 AND BSD-2-Clause |
| propcache | 0.5.2 / 0.5.4 | Apache-2.0 |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psutil | 7.2.2 | BSD-3-Clause |
| py-vapid | 1.9.4 | MPL-2.0 (MPL, xem mục 1) |
| pycparser | 3.0 / 3.11 | BSD-3-Clause |
| pydantic | 2.14.0 / 2.14.1 | MIT |
| pydantic_core | 2.50.0 / 2.50.1 | MIT |
| pydyf | 0.12.1 | BSD License |
| PyOTP | 2.10.0 | MIT |
| pyparsing | 3.3.3 | MIT |
| pyphen | 0.18.1 | GNU General Public License v2 or later (GPLv2+) **(đa giấy phép, xem mục 1)** |
| python-dateutil | 2.9.0.post0 | Dual License |
| pytz | 2026.5 | MIT |
| pywebpush | 2.5.0 | MPL-2.0 (MPL, xem mục 1) |
| PyYAML | 6.0.3 | MIT |
| redis | 8.1.0 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| requests-oauthlib | 2.0.0 | ISC |
| scipy | 1.18.1 | BSD License |
| seaborn | 0.13.2 | BSD License |
| six | 1.17.0 | MIT |
| soupsieve | 3.0.1 / 3.0.2 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| TA-Lib | 0.8.1 | (không khai báo; upstream BSD-3-Clause) |
| tenacity | 9.2.1 | Apache-2.0 |
| tinycss2 | 1.5.1 | BSD License |
| tinyhtml5 | 2.1.0 | MIT License |
| tokenizers | 0.23.3 | Apache Software License |
| tqdm | 4.70.1 | MPL-2.0 AND MIT (MPL, xem mục 1) |
| truststore | 0.10.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.5 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| uvloop | 0.22.1 | MIT License |
| vaderSentiment | 3.3.2 | MIT License |
| vnai | 2.6.3 | proprietary **ĐỎ** |
| vnstock | 4.0.9 | Custom (Personal Use) - see https://vnst **ĐỎ** |
| vnstock_ezchart | 1.0.2 | MIT |
| weasyprint | 70.0 | BSD License |
| webencodings | 0.6.1 | BSD License |
| websockets | 17.2 | BSD-3-Clause |
| wrapt | 2.5.0 | BSD-2-Clause |
| yarl | 1.25.1 | Apache-2.0 |
| zipp | 4.1.1 | MIT |
| zlib-ng | 1.0.0 | PSF-2.0 |
| zopfli | 0.4.3 | Apache-2.0 |
| zstandard | 0.25.0 | BSD-3-Clause |

Ghi chú: bảng gộp 19 image dịch vụ (cùng gói ở nhiều image chỉ hiện một dòng, khác phiên bản gộp bằng "/"). `TA-Lib` không khai báo giấy phép trong metadata; upstream: BSD-3-Clause (thư viện C TA-Lib cũng BSD). Mục "giấy phép" lấy từ trường `License`/`License-Expression`/classifier của gói; gói ghi nhiều giấy phép nghĩa là đa giấy phép. Để tái tạo: `docker exec <container> python -c "import importlib.metadata as m; ..."` (chỉ đọc) hoặc `pip-licenses` trong container tạm.

## 7. Cách giữ danh sách này đúng
1. Thêm gói/image mới → thêm vào bảng tương ứng và, nếu không phải MIT/BSD/Apache/ISC/OFL/PSF, vào mục 1.
2. Renovate/Dependabot cập nhật phiên bản → chạy lại bước đọc metadata (mục 6) để thấy gói nào đổi giấy phép.
3. Trước khi phát hành cho bên thứ ba: xử lý toàn bộ dòng ĐỎ và CAM ở mục 1.
