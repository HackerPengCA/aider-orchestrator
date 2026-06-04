"""
安全沙盒：限制文件写入和命令执行只能在项目目录内
读文件不受限制
"""

import os
import subprocess
from pathlib import Path
from config import COMMAND_TIMEOUT


class Sandbox:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise ValueError(f"项目目录不存在: {project_path}")

    def _assert_within_project(self, path: str):
        """确保路径在项目目录内，防止路径穿越"""
        target = Path(path).resolve()
        try:
            target.relative_to(self.project_path)
        except ValueError:
            raise PermissionError(
                f"安全限制：路径 {path} 超出项目目录 {self.project_path}\n"
                f"写入和执行只允许在项目目录内。"
            )

    def safe_write(self, path: str, content: str):
        """安全写文件（只允许项目目录内）"""
        self._assert_within_project(path)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def safe_read(self, path: str) -> str:
        """读文件（不受限制）"""
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def run_command(self, command: str, cwd: str = None) -> tuple[str, str, int]:
        """
        在项目目录内执行命令
        返回 (stdout, stderr, returncode)
        """
        work_dir = cwd or str(self.project_path)
        self._assert_within_project(work_dir)

        print(f"\n  ▶ 执行: {command}")
        print(f"  📁 目录: {work_dir}")

        import os
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            command,
            shell=True,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(f"  stdout: {result.stdout[:500]}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")
        print(f"  返回码: {result.returncode}")

        return result.stdout, result.stderr, result.returncode

    def list_files(self, max_files: int = 200) -> list[str]:
        """列出项目目录下所有文件（排除常见无关目录）"""
        exclude = {".git", "__pycache__", "node_modules", ".venv", "venv", ".env", "dist", "build"}
        files = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in exclude]
            for f in filenames:
                rel = os.path.relpath(os.path.join(root, f), self.project_path)
                files.append(rel)
                if len(files) >= max_files:
                    return files
        return files
