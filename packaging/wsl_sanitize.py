"""
WSL 镜像导出前脱敏（CDS / ERA5），及部署后向 WSL 注入客户 CDS 配置。
"""
from __future__ import annotations

import subprocess
from typing import Callable, Optional

from cds_wsl_bridge import push_cdsapirc_to_wsl, sync_cdsapirc_from_windows_to_wsl

DecodeFn = Callable[[bytes | None], str]


def _bash_sanitize_script(keep_secrets: bool) -> str:
    if keep_secrets:
        return "echo 'SANITIZE_SKIPPED=1'"
    return r"""
set +e
removed_cds=0
if [ -f "$HOME/.cdsapirc" ]; then
  rm -f "$HOME/.cdsapirc"
  removed_cds=1
fi
scrub_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  if grep -qE 'WEATHER_DIR|CDS_API|CDSAPIRC|ERA5' "$f" 2>/dev/null; then
    sed -i.bak-insar '/WEATHER_DIR/d;/CDS_API/d;/CDSAPIRC/d;/\bERA5\b/d' "$f" 2>/dev/null \
      || sed -i '/WEATHER_DIR/d;/CDS_API/d;/CDSAPIRC/d;/\bERA5\b/d' "$f" 2>/dev/null
    rm -f "${f}.bak-insar" 2>/dev/null
  fi
}
scrub_file "$HOME/insar-wsl/env_isce2.sh"
scrub_file "$HOME/.bashrc"
scrub_file "$HOME/.profile"
for d in "$HOME/weather" "$HOME/ERA5" "$HOME/.cache/pyaps" "$HOME/insar-wsl/weather"; do
  if [ -d "$d" ]; then
    rm -rf "$d"/* 2>/dev/null
  fi
done
echo "SANITIZE_OK removed_cds=${removed_cds}"
"""


def run_wsl_sanitize_before_export(
    distro: str,
    *,
    keep_secrets: bool = False,
    decode: DecodeFn,
    creationflags: int = 0,
    timeout: int = 120,
) -> tuple[bool, str]:
    """在 wsl --export 前于指定发行版内执行脱敏。"""
    inner = _bash_sanitize_script(keep_secrets)
    argv = ["wsl", "-d", distro, "-e", "bash", "-c", inner]
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        out = decode(r.stdout) or decode(r.stderr)
        if r.returncode != 0:
            return False, out or "脱敏脚本执行失败"
        if keep_secrets:
            return True, "已跳过脱敏（内部构建）"
        if "SANITIZE_OK" not in out:
            return False, out or "脱敏未返回预期结果"
        return True, out.strip()
    except subprocess.TimeoutExpired:
        return False, "脱敏超时"
    except Exception as e:
        return False, str(e)


def ensure_weather_dir_windows() -> Optional[str]:
    """创建本机气象缓存目录，返回 Windows 路径。"""
    from wsl_config_path import ensure_config_dir, get_weather_dir_path

    if not ensure_config_dir():
        return None
    p = get_weather_dir_path()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return str(p.resolve())
    except OSError:
        return None


def main() -> int:
    """CLI: python -m packaging.wsl_sanitize --distro Ubuntu [--keep-secrets]"""
    import argparse
    import sys

    def _decode(data: bytes | None) -> str:
        if not data:
            return ""
        for enc in ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1"):
            try:
                return data.decode(enc, errors="strict").strip()
            except (UnicodeDecodeError, LookupError):
                continue
        return data.decode("utf-8", errors="replace").strip()

    flags = 0
    if sys.platform == "win32":
        import subprocess as sp

        flags = getattr(sp, "CREATE_NO_WINDOW", 0x08000000)

    p = argparse.ArgumentParser(description="WSL export sanitize (CDS/ERA5)")
    p.add_argument("--distro", required=True)
    p.add_argument("--keep-secrets", action="store_true")
    args = p.parse_args()
    ok, msg = run_wsl_sanitize_before_export(
        args.distro,
        keep_secrets=args.keep_secrets,
        decode=_decode,
        creationflags=flags,
    )
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
