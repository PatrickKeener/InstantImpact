#!/usr/bin/env python3
"""Download pinned Flux still weights into a ComfyUI models tree.

Setup-only. Runtime generation stays offline.

  python scripts/bootstrap_models.py --profile krea --i-accept-licenses
  python scripts/bootstrap_models.py --profile bf16 --dry-run
  python scripts/bootstrap_models.py --profile fp8 --i-accept-licenses

Gated Black Forest Labs repos need INSTANTIMPACT_HF_TOKEN or HF_TOKEN
(FLUX.1-dev / FLUX.1-Krea-dev license accepted on Hugging Face).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for extra in (
    _REPO / "packages" / "common",
    _REPO,
):
    sp = str(extra)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from instantimpact_common.flux_inventory import (  # noqa: E402
    dest_dir_for_kind,
    hf_url,
    resolve_comfy_root,
    sha256_file,
)
from instantimpact_common.model_pins import (  # noqa: E402
    PROFILE_ENV,
    PROFILES,
    pins_for_profile,
)
from instantimpact_common.offline import enforce_strict_offline  # noqa: E402


def _load_dotenv() -> None:
    """Pull KEY=VALUE lines from repo .env if they are not already exported."""
    path = _REPO / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _token() -> str:
    return (
        os.environ.get("INSTANTIMPACT_HF_TOKEN")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or ""
    ).strip()


def _download(url: str, dest: Path, *, token: str, expected_sha: str | None) -> None:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": "instantimpact-bootstrap"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resume_from = part.stat().st_size if part.is_file() else 0
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    request = Request(url, headers=headers)
    try:
        response = urlopen(request, timeout=None)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise SystemExit(
                f"Hugging Face returned {exc.code} for {url}. "
                "Accept the FLUX.1-dev and Krea licenses on huggingface.co, "
                "then set INSTANTIMPACT_HF_TOKEN in .env."
            ) from exc
        if exc.code == 416 and dest.is_file():
            return
        raise SystemExit(f"Download failed ({exc.code}): {url}") from exc
    status = getattr(response, "status", None) or response.getcode()
    mode = "ab" if resume_from and status == 206 else "wb"
    if mode == "wb" and part.exists():
        part.unlink()
    downloaded = resume_from if mode == "ab" else 0
    total = response.headers.get("Content-Length")
    total_i = int(total) + (resume_from if mode == "ab" else 0) if total else None
    try:
        with part.open(mode) as fh:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if total_i:
                    pct = 100 * downloaded / total_i
                    print(
                        f"\r  {dest.name}: {downloaded / 1e9:.2f} / "
                        f"{total_i / 1e9:.2f} GB ({pct:.0f}%)",
                        end="",
                        flush=True,
                    )
        print()
    finally:
        response.close()
    if expected_sha:
        got = sha256_file(part)
        if got.lower() != expected_sha.lower():
            part.unlink(missing_ok=True)
            raise SystemExit(
                f"SHA-256 mismatch for {dest.name}: got {got}, expected {expected_sha}"
            )
    part.replace(dest)
    _chown_like_comfy(dest)


def _chown_like_comfy(path: Path) -> None:
    """Keep weights owned by the Comfy tree user when bootstrap runs as root."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0 or not path.exists():
        return
    try:
        st = path.parent.stat()
        os.chown(path, st.st_uid, st.st_gid)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="krea",
        choices=sorted(PROFILES),
        help="Weight set to install",
    )
    parser.add_argument(
        "--comfy-dir",
        default=os.environ.get("INSTANTIMPACT_COMFY_DIR") or "",
        help="ComfyUI root (models/ lives under this)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print URLs and destinations only")
    parser.add_argument(
        "--i-accept-licenses",
        action="store_true",
        help="Required for downloads. Accepts each pin's license (BFL FLUX.1 [dev]).",
    )
    parser.add_argument("--force", action="store_true", help="Re-download files that already exist")
    args = parser.parse_args(argv)

    strict = (os.environ.get("INSTANTIMPACT_STRICT_OFFLINE") or "").lower() in {"1", "true", "yes"}
    if strict and not args.dry_run:
        raise SystemExit("STRICT_OFFLINE is set — bootstrap downloads are blocked.")

    root = resolve_comfy_root(args.comfy_dir or None)
    if root is None:
        raise SystemExit(
            "Could not find ComfyUI. Pass --comfy-dir or set INSTANTIMPACT_COMFY_DIR "
            "(directory that contains models/ or main.py)."
        )

    pins = pins_for_profile(args.profile)
    print(f"Profile: {args.profile} — {PROFILES[args.profile]}")
    print(f"Comfy root: {root}")
    token = _token()
    if any(p.gated for p in pins) and not token and not args.dry_run:
        print(
            "Warning: gated pins need INSTANTIMPACT_HF_TOKEN after you accept the "
            "FLUX.1-dev / Krea license on Hugging Face.",
            file=sys.stderr,
        )

    if not args.dry_run and not args.i_accept_licenses:
        raise SystemExit(
            "Refusing to download without --i-accept-licenses. "
            "FLUX.1 [dev] and Krea are non-commercial; you must accept their cards."
        )

    for pin in pins:
        dest = dest_dir_for_kind(root, pin.dest_kind) / pin.filename
        url = hf_url(pin.hf_repo, pin.hf_path)
        exists = dest.is_file()
        print(f"{pin.id}: {pin.filename} ({pin.approx_gb} GB) -> {dest}")
        print(f"  {url}")
        if args.dry_run:
            print(f"  {'present' if exists else 'missing'}")
            continue
        if exists and not args.force:
            if pin.sha256:
                got = sha256_file(dest)
                if got.lower() != pin.sha256.lower():
                    print("  SHA mismatch on existing file, re-downloading")
                else:
                    print("  already present (sha ok)")
                    continue
            else:
                print("  already present")
                continue
        if pin.gated:
            enforce_strict_offline(url, strict)
        _download(url, dest, token=token, expected_sha=pin.sha256)
        print(f"  sha256 {sha256_file(dest)}")

    print("\nSet these in .env (then restart Comfy + the GPU worker):")
    for key, value in PROFILE_ENV[args.profile].items():
        print(f"  {key}={value}")
    if args.profile in {"krea", "krea-fp8", "bf16"}:
        print(
            "Retrain every character LoRA after this swap — "
            "old LoRAs are deltas against the previous base."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
