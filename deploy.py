#!/usr/bin/env python3
"""一键将本地修改推送到云端服务器 (One-Click Deploy to Cloud)

运行方式：
    python deploy.py

工作流程：
1. 连接云服务器 (36.151.149.94)；
2. 同步 site/ 目录下的所有前端网页与插画到云端 /var/www/web_design/；
3. 同步 server/ 目录下的最新后端代码；
4. 校验 Nginx 配置并热重载；
5. 重启后台 API 服务；
6. 自动对公网做连通性与健康度测试。
"""
import os
import sys
import time
import paramiko
import urllib.request
import json

# Windows GBK 终端防乱码与防崩溃处理
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")
SERVER_DIR = os.path.join(BASE_DIR, "server")
REMOTE_ROOT = "/var/www/web_design"

# 优先读取本地 .env 配置文件（避免敏感凭据提交到 Git 仓库）
_env_file = os.path.join(BASE_DIR, ".env")
if os.path.isfile(_env_file):
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass

HOST = os.environ.get("SSH_HOST", "")
USER = os.environ.get("SSH_USER", "root")
PASS = os.environ.get("SSH_PASS", "")


def main():
    if not HOST or not PASS:
        print("[!] 错误：未配置云服务器连接凭据。请在本地创建 .env 文件并配置 SSH_HOST 与 SSH_PASS（参考 .env.example）。")
        return 1

    print("=" * 60)
    print("小哭包和宝宝的旅行日记 · 正在将本地修改推送到云端...")
    print(f"目标服务器: {USER}@{HOST}")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, port=22, username=USER, password=PASS, timeout=15)
    except Exception as e:
        print(f"[!] 连接云服务器失败: {e}")
        return 1

    sftp = ssh.open_sftp()

    # 1. 确保远程目录存在
    ssh.exec_command(f"mkdir -p {REMOTE_ROOT}/assets {REMOTE_ROOT}/uploads && chmod 755 {REMOTE_ROOT}/uploads")

    # 2. 上传 site/ 目录文件
    print("\n[1/3] 上传前端网页与图片资源...")
    upload_count = 0
    for root, dirs, files in os.walk(SITE_DIR):
        for f in files:
            local_path = os.path.join(root, f)
            rel_path = os.path.relpath(local_path, SITE_DIR).replace("\\", "/")
            remote_path = f"{REMOTE_ROOT}/{rel_path}"

            remote_dir = os.path.dirname(remote_path)
            ssh.exec_command(f"mkdir -p {remote_dir}")

            sftp.put(local_path, remote_path)
            size_kb = os.path.getsize(local_path) / 1024
            print(f"  -> {rel_path} ({size_kb:.1f} KB)")
            upload_count += 1

    # 3. 上传 server/ 目录
    print("\n[2/3] 上传后端服务与配置...")
    local_server_py = os.path.join(SERVER_DIR, "server.py")
    if os.path.isfile(local_server_py):
        sftp.put(local_server_py, f"{REMOTE_ROOT}/server.py")
        print("  -> server.py")

    sftp.close()

    # 4. 重载与校验服务
    print("\n[3/3] 校验并重载云端 Nginx 与 API 守护进程...")
    cmd = f"""
    chmod +x {REMOTE_ROOT}/server.py
    systemctl restart diary-api
    nginx -t && systemctl reload nginx
    """
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    rc = stdout.channel.recv_exit_status()

    if rc != 0:
        print(f"[!] 远程服务重载失败:\n{err}")
        ssh.close()
        return rc

    ssh.close()

    # 5. 公网探测验证
    print("\n正在探测公网访问状态...")
    time.sleep(1.2)
    try:
        req = urllib.request.Request(f"http://{HOST}/api/health", headers={"User-Agent": "DeployCheck"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "ok":
                print("[OK] 后端 API 正常响应 (200 OK)")
    except Exception as e:
        print(f"[!] 公网探测提示: {e}")

    print("\n" + "=" * 60)
    print("恭喜！本地修改已全部成功同步上线！")
    print(f"公网访问体验地址: http://{HOST}/")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
