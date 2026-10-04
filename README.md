# 📲 ipa-push

Đẩy file `.ipa` lên iPhone của bạn qua web app — agent gọi MCP tool là xong.

## Chạy nhanh (cho agent)

```bash
git clone https://github.com/tuoitrevohoc/ipa-push.git ~/ipa-push
cd ~/ipa-push
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Sửa .env: đặt IPA_PUSH_BASE_URL=https://<domain-public-cua-ban>
#           và IPA_PUSH_TOKEN=<chuoi-ngau-nhien>
nano .env   # hoặc dùng editor tùy ý
# Chạy nền:
nohup ./run-web.sh > ipa-push.log 2>&1 &
# Kiểm tra:
curl -s http://localhost:8765/ | head -c 100
```

Mở tunnel để iPhone truy cập được (iOS bắt buộc HTTPS):

```bash
cloudflared tunnel --url http://localhost:8765
# → lấy URL https://xxx.trycloudflare.com, điền vào IPA_PUSH_BASE_URL trong .env, restart server
```

Muốn chạy bền vững sau khi restart máy: tạo LaunchAgent `~/Library/LaunchAgents/dev.ipapush.plist`
gọi `/Users/<ban>/ipa-push/run-web.sh`, rồi `launchctl load` nó.

## Nó làm gì

Bạn (hoặc agent của bạn) đưa 1 file `.ipa` → server lưu lại, tự sinh `manifest.plist`,
trả về **link cài đặt**. Mở link đó bằng **Safari trên iPhone** → bấm *Cài đặt* → app
xuất hiện ngoài màn hình chính. Không cần cắm cáp, không cần TestFlight.

Có **2 đường cài**:

| Đường | Cách | Yêu cầu với IPA |
|---|---|---|
| **OTA qua web** (chính) | Mở link `itms-services://` / quét QR trên iPhone | IPA ký **Ad Hoc** hoặc **Enterprise**, UDID máy đã đăng ký |
| **Cài trực tiếp** (tool `install_to_device`) | Server trên Mac gọi `devicectl`, app tự hiện trên iPhone, không chạm vào điện thoại | Bản **Development** cũng được — nhưng iPhone phải pair với Mac (USB/WiFi sync) |

## Kiến trúc

```
ipa-push/
├── ipapush/
│   ├── web.py        # FastAPI: trang web + API upload + serve manifest/ipa/QR
│   ├── mcp_server.py # MCP server: 7 tools (stdio + HTTP)
│   ├── core.py       # logic chung: push/list/get/delete, sinh link
│   ├── ipa.py        # đọc Info.plist trong IPA (bundle id, version, icon)
│   ├── manifest.py   # sinh manifest.plist cho itms-services
│   ├── store.py      # lưu metadata JSON
│   └── templates/    # index.html (quản lý), install.html (trang cài đặt)
├── run-web.sh        # chạy web app (+ MCP tại /mcp)
├── run-mcp.sh        # chạy MCP qua stdio (cho Claude Code / agent local)
└── tests/test_e2e.py # test end-to-end
```

## Cài đặt trên Mac Studio

Server nên chạy trên **Mac Studio** (là nơi có file `.ipa` sau khi build).

```bash
cd ~/ipa-push
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# sửa .env: IPA_PUSH_BASE_URL=https://<domain-cua-ban>, IPA_PUSH_TOKEN=<token-ngau-nhien>
./run-web.sh
```

Mở `http://<mac>:8765`, nhập token, tải IPA lên thử.

### Cho iPhone truy cập từ ngoài: Cloudflare Tunnel

iOS **bắt buộc HTTPS** mới chịu cài OTA. Cách nhanh nhất: `cloudflared tunnel`
trỏ về `localhost:8765`, lấy domain `https://ipa-push.<domain-cua-ban>`,
rồi đặt vào `IPA_PUSH_BASE_URL` trong `.env` và restart server.

## ⚠️ Bước bắt buộc: ký IPA dạng Ad Hoc

Cài qua web **không** dùng được bản Development. Cần:

1. **Lấy UDID iPhone**: cắm iPhone vào Mac → Xcode → *Window → Devices and Simulators*
   → copy UDID (hoặc dùng Apple Configurator).
2. **Đăng ký UDID**: [developer.apple.com](https://developer.apple.com)
   → *Certificates, Identifiers & Profiles → Devices* → thêm UDID.
3. **Tạo Ad Hoc provisioning profile** cho App ID của app (kèm device vừa thêm).
4. **Export IPA**: Xcode → *Product → Archive → Distribute App → Ad Hoc*
   → chọn profile vừa tạo → được file `.ipa`.

Sau đó agent gọi `push_ipa` (hoặc bạn tải lên web) → mở link trên iPhone → cài.

## Kết nối agent qua MCP

**Cách 1 — stdio (agent chạy cùng máy Mac, vd. Claude Code):**

```json
// ~/.claude.json hoặc claude_desktop_config.json
{ "mcpServers": { "ipa-push": {
    "command": "/Users/<ban>/ipa-push/run-mcp.sh"
} } }
```

**Cách 2 — HTTP (agent ở xa, vd. Muse):** endpoint `https://<domain>/mcp`
(streamable HTTP), auth bằng header `Authorization: Bearer <IPA_PUSH_TOKEN>`
hoặc `?token=`.

## 7 tools của MCP

| Tool | Mô tả |
|---|---|
| `push_ipa(path, display_name="")` | Đẩy IPA (đường dẫn local trên máy chạy server) → trả JSON gồm `itms_url`, `install_page`, `qr_url` |
| `list_ipas()` | Liệt kê IPA đã upload kèm link cài đặt |
| `get_install_info(ipa_id)` | Lấy link cài đặt của 1 IPA |
| `delete_ipa(ipa_id)` | Xóa IPA |
| `list_devices()` | Liệt kê iPhone đang kết nối Mac (cần Xcode) |
| `install_to_device(ipa_id, udid="")` | Cài **trực tiếp** lên iPhone qua USB/WiFi, không cần Ad Hoc |
| `server_info()` | Xem cấu hình server |

Ví dụ flow của agent: build xong `.ipa` → `push_ipa` → gửi `install_page`
cho bạn → bạn mở bằng Safari trên iPhone → bấm Cài đặt. Hoặc nếu iPhone
đang pair với Mac: `install_to_device` là app tự hiện, khỏi chạm điện thoại.

## Web app

- `/` — trang quản lý: nhập token, tải IPA lên, xem danh sách, nút **📲 Cài đặt**,
  QR code, copy link, xóa.
- `/i/<id>` — trang cài đặt gọn cho iPhone (nút Cài đặt to + QR).
- API: `GET /api/ipas`, `POST /api/upload` (multipart: `file`, `name`, `token`),
  `DELETE /api/ipas/<id>` — đều cần token.

## Bảo mật

- API upload/xóa và MCP qua HTTP **cần token** (`IPA_PUSH_TOKEN`). Đừng để trống
  khi expose ra internet.
- Link cài đặt chứa id ngẫu nhiên 12 ký tự hex — khó đoán nhưng không phải bí mật
  tuyệt đối; IPA Ad Hoc vốn chỉ cài được trên máy đã đăng ký UDID.

## Test

```bash
.venv/bin/python tests/test_e2e.py   # 33 checks: parse, manifest, web, MCP stdio+HTTP
```
