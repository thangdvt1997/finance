# data-keeper
Agent cục bộ giữ dữ liệu giá đầy đủ cho mọi mã (kiểm kê, tự chữa, backfill, nạp lịch sử). Xem docs/handoff/DK_BRIEF.md, docs/DATA_KEEPER.md.
Cờ DATA_KEEPER_ENABLED=false = kill-switch (chỉ phục vụ /healthz, không chạy vòng lặp). READ-ONLY: không có đường đặt lệnh.
Module nạp lỏng (thiếu thì bỏ qua): inventory, heal, backfill, histload, llm, api. Hợp đồng ở main.py.
