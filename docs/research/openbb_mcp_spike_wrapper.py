"""SPIKE (chưa gắn vào hệ thống): MCP server CHỈ ĐỌC bọc api-gateway qua HTTP.

Không dùng `openbb-mcp` trực tiếp vì nó luôn đăng ký thêm `install_skill` (ghi file lên đĩa) và `run_pipeline`.
Ở đây chỉ dựng FastMCP (OSS) từ OpenAPI của gateway, chỉ route GET /v1/*, token gateway nằm ở header của
httpx client (LLM không nhìn thấy token, không có đối số x-api-key).
Chạy: GATEWAY_URL=http://api-gateway:8000 GATEWAY_TOKEN=... python openbb_mcp_spike_wrapper.py  (cổng 8002, 127.0.0.1)
"""
import os

import httpx2 as httpx  # fastmcp 4.x dùng httpx2 (fork của httpx)
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap

BASE = os.environ.get("GATEWAY_URL", "http://api-gateway:8000")
TOKEN = os.environ["GATEWAY_TOKEN"]

spec = httpx.get(f"{BASE}/openapi.json", timeout=10).json()
# Gỡ tham số header x-api-key khỏi schema công cụ: token do client httpx tự gắn.
for path in spec.get("paths", {}).values():
    for op in path.values():
        if isinstance(op, dict) and "parameters" in op:
            op["parameters"] = [p for p in op["parameters"] if not (p.get("in") == "header" and p.get("name", "").lower() == "x-api-key")]

client = httpx.AsyncClient(base_url=BASE, headers={"x-api-key": TOKEN}, timeout=15)
mcp = FastMCP.from_openapi(
    openapi_spec=spec, client=client, name="trading-system-readonly",
    route_maps=[
        RouteMap(methods=["GET"], pattern=r"^/v1/", mcp_type=MCPType.TOOL),   # chỉ đọc dữ liệu thị trường/hệ thống
        RouteMap(mcp_type=MCPType.EXCLUDE),                                    # mọi thứ khác (kể cả POST/PUT/DELETE, /metrics, /ui) bị loại
    ],
)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=int(os.environ.get("MCP_PORT", "8002")))
