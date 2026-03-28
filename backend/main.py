from pathlib import Path
import sys


# 这个文件是后端的极简启动入口。
# 它只做两件事：
# 1. 把 backend/src 加入 Python 搜索路径。
# 2. 调用真正的 HTTP 服务入口 risk_backend.api_server.main。
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from risk_backend.api_server import main


if __name__ == "__main__":
    main()
