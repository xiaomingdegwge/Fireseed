from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DependencyCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

#判断当前机器能不能真的跑 sandbox
def check_dependencies() -> DependencyCheck:
    result = DependencyCheck()
    if platform.system() != "Linux": #是否是 Linux
        result.errors.append(f"Sandbox requires Linux (current: {platform.system()})")
        return result

    if not shutil.which("bwrap"): #有没有安装 bwrap
        result.errors.append("bubblewrap (bwrap) not found. Install: apt install bubblewrap")
        return result
    #有些 Linux 禁用了非特权用户 namespace，这种情况下 bwrap 也跑不起来
    userns_path = Path("/proc/sys/kernel/unprivileged_userns_clone") #用户命名空间是否允许
    try:
        if userns_path.read_text(encoding="utf-8").strip() == "0":
            result.errors.append("User namespaces disabled; sandbox requires user namespace support.")
            return result
    except OSError:
        pass

    try:
        #实际跑一次 bwrap 测试 是否能正常运行
        proc = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        result.errors.append(f"bwrap test failed: {exc}")
        return result

    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace").strip()
        result.errors.append(f"bwrap test failed: {stderr}")
    return result
