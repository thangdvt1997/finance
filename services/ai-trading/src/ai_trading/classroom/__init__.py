"""AI Training Class (lõi, thuần mã): LLMClient, state machine hỏi sâu, hồ sơ kịch bản, "học 1 hiểu 10", gợi ý hành động, chống injection, xuất YAML.

CHỈ nghiên cứu/paper. Không có đường đặt lệnh; action chỉ trả "ý định" có cấu trúc cho lớp backend thực thi (P2b).
"""
from .commands import Intent, chips_for, parse_command  # noqa: F401
from .export import export_scenario  # noqa: F401
from .llm import LLMClient, LLMError, build_client  # noqa: F401
from .machine import Classroom, Turn  # noqa: F401
from .profile import Profile, ProfileHistory  # noqa: F401
