"""Reference tool for code review: a broad pattern scanner. Used only by
`python -m stem selftest` and tests."""
import re

RULES = [
    (r"execute\((f\"|\".*(%|\.format\()|\w+\))", "sql_injection"),
    (r"os\.system\(.*(\+|\{)|shell=True|os\.popen\(", "command_injection"),
    (r"open\(.*(join|f\").*|send_file\(.*\+|Path\(.*\)\s*/\s*\w+", "path_traversal"),
    (r"^[A-Z_]*(KEY|PASSWORD|SECRET|TOKEN)[A-Z_]*\s*=\s*\"[^\"]{8,}\"|token=\"[^\"]{12,}\"", "hardcoded_secret"),
    (r"pickle\.loads\(|yaml\.load\(.*Loader=yaml\.Loader|jsonpickle\.decode", "insecure_deserialization"),
    (r"(md5|sha1)\((password|pwd)", "weak_password_hash"),
    (r"\beval\(|\bexec\(", "code_injection"),
]


def run(env):
    found = 0
    for f in env.list_files():
        text = env.read_file(path=f["path"], start=1, end=f["lines"])
        lines = [l[6:] for l in text.split("\n")]
        for i, line in enumerate(lines, 1):
            if "basename" in line or "safe_load" in line:
                continue
            for pattern, cat in RULES:
                if re.search(pattern, line):
                    if cat == "sql_injection" and (re.search(r",\s*\(", line) or "{AUDIT_TABLE}" in line):
                        continue
                    if cat == "path_traversal" and i > 1 and "basename" in lines[i - 2]:
                        continue
                    env.report(path=f["path"], line=i, category=cat)
                    found += 1
                    break
            if re.match(r"@(route|router\.\w+)\(\"/(admin|internal)", line):
                nxt = lines[i] if i < len(lines) else ""
                if not nxt.startswith("@require") and "Depends" not in nxt:
                    env.report(path=f["path"], line=i + 1, category="missing_authorization")
                    found += 1
    return f"{found} findings filed"
