#!/usr/bin/env python3
"""Select compatible CoolOS repositories before target package installation."""

import argparse
import pathlib
import re
import subprocess


# CachyOS uses a distinct -march=znver4 tier for Zen 4 and Zen 5. Require
# usable v4 support, known AMD families/models, and the additional ISA flags.
# Reference: https://wiki.cachyos.org/features/optimized_repos/
ZEN4_FLAGS = set("""
abm adx aes avx512_bf16 avx512_bitalg avx512ifma avx512vbmi avx512_vbmi2
avx512_vnni avx512_vpopcntdq clflushopt clwb clzero fsgsbase gfni mwaitx
pclmulqdq pku rdrand rdseed sha_ni sse4a vaes vpclmulqdq wbnoinvd
xsavec xsaveopt xsaves
""".split())
REPOSITORIES = ("coolos-znver4", "coolos-v4", "coolos-v3", "coolos")


def cpu_records(cpuinfo):
    return [dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
            for block in cpuinfo.strip().split("\n\n") if block.strip()]


def select_target(loader_help, cpuinfo):
    supported = set(re.findall(r"(x86-64-v[34]) \(supported, searched\)", loader_help))
    if "x86-64-v3" not in supported:
        return "x86-64"
    if "x86-64-v4" not in supported:
        return "x86-64-v3"
    records = [{key.strip(): value.strip() for key, value in record.items()}
               for record in cpu_records(cpuinfo)]
    for record in records:
        try:
            family, model = int(record["cpu family"]), int(record["model"])
        except (KeyError, ValueError):
            return "x86-64-v4"
        known_amd = record.get("vendor_id") == "AuthenticAMD" and (
            family == 0x1A or (family == 0x19 and (
                0x10 <= model <= 0x1F or 0x60 <= model <= 0xAF)))
        if not known_amd or not ZEN4_FLAGS <= set(record.get("flags", "").split()):
            return "x86-64-v4"
    return "znver4" if records else "x86-64-v4"


def detect_target():
    try:
        result = subprocess.run(["/lib/ld-linux-x86-64.so.2", "--help"],
                                check=True, capture_output=True, text=True)
        return select_target(result.stdout, pathlib.Path("/proc/cpuinfo").read_text())
    except (OSError, subprocess.SubprocessError):
        return "x86-64"


def configure(text, target):
    first = {"znver4": 0, "x86-64-v4": 1, "x86-64-v3": 2, "x86-64": 3}[target]
    sections = []
    skip = False
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*\[([^]]+)\]\s*(?:#.*)?$", line)
        if match:
            skip = match[1] in REPOSITORIES
        if not skip:
            sections.append(line)
    cleaned = "".join(sections)
    if not re.search(r"^\s*\[options\]\s*(?:#.*)?$", cleaned, re.MULTILINE):
        raise ValueError("Pacman configuration is missing [options]")
    block = ""
    for repo in REPOSITORIES[first:]:
        suffix = "" if repo == "coolos" else f"/{repo}"
        block += f"[{repo}]\nServer = https://coolos-repo.sarulean.com/$arch{suffix}\n\n"
    match = re.search(r"^\s*\[(?!options\])[^]]+\]", cleaned, re.MULTILINE)
    position = match.start() if match else len(cleaned)
    return cleaned[:position].rstrip() + "\n\n" + block + cleaned[position:].lstrip("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=pathlib.Path)
    parser.add_argument("--print-target", action="store_true")
    args = parser.parse_args()
    target = detect_target()
    if args.print_target:
        print(target)
    elif args.config:
        args.config.write_text(configure(args.config.read_text(), target))
        print(f"CoolOS repositories configured for {target}")
    else:
        parser.error("provide a Pacman configuration path or --print-target")


if __name__ == "__main__":
    main()
