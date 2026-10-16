"""In ra (stdout) các dòng KEY=VALUE cho VAPID + khoá mã hoá đăng ký push. Dùng bởi infra/ops/gen_vapid.sh (nạp thẳng vào infra/.env, không hiển thị)."""
from .webpush import generate_keys

if __name__ == "__main__":
    for k, v in generate_keys().items():
        print(f"{k}={v}")
