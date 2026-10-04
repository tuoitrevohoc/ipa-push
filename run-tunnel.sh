#!/bin/bash
# Chạy Cloudflare Tunnel đã tạo sẵn cho ipa-push.
# Tunnel token lấy từ file .tunnel-token (không commit lên git)
# hoặc biến môi trường IPA_TUNNEL_TOKEN.
cd "$(dirname "$0")"
TOKEN="${IPA_TUNNEL_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .tunnel-token ]; then
  TOKEN="$(tr -d ' \t\r\n' < .tunnel-token)"
fi
if [ -z "$TOKEN" ]; then
  echo "Thiếu tunnel token: tạo file .tunnel-token hoặc export IPA_TUNNEL_TOKEN" >&2
  exit 1
fi
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Chưa có cloudflared: brew install cloudflared" >&2
  exit 1
fi
exec cloudflared tunnel --no-autoupdate run --token "$TOKEN"
