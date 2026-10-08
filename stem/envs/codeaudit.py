"""Security review of synthetic Python web services.

Each task is a generated repository of ~90 files with a handful of planted
vulnerabilities and look-alike safe code. Held-out repositories mix the
idioms seen in training with idioms that never appear there, so a scanner
that only memorised training patterns will miss part of them.
"""
from __future__ import annotations

import random
import re

from .base import Action, Environment, Task

CATEGORIES = ["sql_injection", "command_injection", "path_traversal", "hardcoded_secret",
              "insecure_deserialization", "weak_password_hash", "code_injection",
              "missing_authorization"]

# Each snippet is a list of lines; the line marked with "#!" is where the issue is.
# The marker is stripped before the file is shown.
VULNS: dict[str, dict[str, list[list[str]]]] = {
    "sql_injection": {
        "train": [
            ["def find_user(cur, name):",
             "    cur.execute(f\"SELECT id, email FROM users WHERE name = '{name}'\")  #!",
             "    return cur.fetchone()"],
            ["def load_order(cur, order_id):",
             "    cur.execute(\"SELECT * FROM orders WHERE id = %s\" % order_id)  #!",
             "    return cur.fetchall()"],
        ],
        "test": [
            ["def drop_session(db, token):",
             "    query = \"DELETE FROM sessions WHERE token = '\" + token + \"'\"",
             "    db.execute(query)  #!"],
            ["def set_stock(conn, sku, qty):",
             "    conn.execute(\"UPDATE items SET qty = {} WHERE sku = '{}'\".format(qty, sku))  #!"],
        ],
    },
    "command_injection": {
        "train": [
            ["def make_thumbnail(filename):",
             "    os.system(\"convert \" + filename + \" -resize 128x128 thumb.png\")  #!"],
            ["def ping_host(host):",
             "    return subprocess.call(f\"ping -c 1 {host}\", shell=True)  #!"],
        ],
        "test": [
            ["def unpack(archive):",
             "    subprocess.run(\"tar -xzf \" + archive, shell=True, check=True)  #!"],
            ["def lookup(domain):",
             "    return os.popen(f\"nslookup {domain}\").read()  #!"],
        ],
    },
    "path_traversal": {
        "train": [
            ["def download(request):",
             "    name = request.args[\"file\"]",
             "    return open(os.path.join(UPLOAD_DIR, name), \"rb\").read()  #!"],
            ["def serve_static(request):",
             "    filename = request.args.get(\"path\", \"index.html\")",
             "    return send_file(STATIC_ROOT + \"/\" + filename)  #!"],
        ],
        "test": [
            ["def read_report(params):",
             "    name = params[\"report\"]",
             "    with open(f\"{REPORT_DIR}/{name}\") as fh:  #!",
             "        return fh.read()"],
            ["def asset(user_path):",
             "    return (Path(ASSET_ROOT) / user_path).read_bytes()  #!"],
        ],
    },
    # Invented values in no real provider's key format: the planted flaw is a
    # credential written into the code, which the name and the literal show.
    "hardcoded_secret": {
        "train": [
            ["STRIPE_API_KEY = \"payments-live-7Hq2xKb9Tz2LmQwE\"  #!"],
            ["DB_PASSWORD = \"Pr0d-Passw0rd!2023\"  #!"],
        ],
        "test": [
            ["AWS_SECRET_ACCESS_KEY = \"backup-store-secret-Xq81kdTmX\"  #!"],
            ["def github_client():",
             "    return Client(token=\"deploy-token-4fT9xQ2mZ7cL8vB1\")  #!"],
        ],
    },
    "insecure_deserialization": {
        "train": [
            ["def restore_session(request):",
             "    return pickle.loads(request.data)  #!"],
            ["def read_cookie(cookie):",
             "    return pickle.loads(base64.b64decode(cookie))  #!"],
        ],
        "test": [
            ["def parse_config_upload(body):",
             "    return yaml.load(body, Loader=yaml.Loader)  #!"],
            ["def decode_job(raw):",
             "    return jsonpickle.decode(raw)  #!"],
        ],
    },
    "weak_password_hash": {
        "train": [
            ["def hash_password(password):",
             "    return hashlib.md5(password.encode()).hexdigest()  #!"],
        ],
        "test": [
            ["def set_password(user, pwd):",
             "    user.password_hash = hashlib.sha1(pwd.encode()).hexdigest()  #!"],
        ],
    },
    "code_injection": {
        "train": [
            ["def calculate(request):",
             "    return eval(request.args.get(\"expr\", \"0\"))  #!"],
        ],
        "test": [
            ["def apply_formula(formula, x):",
             "    fn = eval(f\"lambda x: {formula}\")  #!",
             "    return fn(x)"],
            ["def run_plugin(user_code):",
             "    exec(compile(user_code, \"<plugin>\", \"exec\"))  #!"],
        ],
    },
    "missing_authorization": {
        "train": [
            ["@route(\"/admin/users/<int:uid>/delete\", methods=[\"POST\"])",
             "def delete_user(uid):  #!",
             "    User.query.get(uid).delete()",
             "    return {\"deleted\": uid}"],
        ],
        "test": [
            ["@router.post(\"/internal/refunds\")",
             "def issue_refund(payload: RefundIn):  #!",
             "    return refunds.create(payload.order_id, payload.amount)"],
        ],
    },
}

DECOYS = [
    ["def find_user_safe(cur, name):",
     "    cur.execute(\"SELECT id, email FROM users WHERE name = %s\", (name,))",
     "    return cur.fetchone()"],
    ["def count_rows(cur):",
     "    cur.execute(f\"SELECT count(*) FROM {AUDIT_TABLE}\")",
     "    return cur.fetchone()[0]"],
    ["def ping_safe(host):",
     "    return subprocess.run([\"ping\", \"-c\", \"1\", host], check=False).returncode"],
    ["def clear_screen():",
     "    os.system(\"clear\")"],
    ["def download_safe(request):",
     "    name = os.path.basename(request.args[\"file\"])",
     "    return open(os.path.join(UPLOAD_DIR, name), \"rb\").read()"],
    ["STRIPE_API_KEY = os.environ[\"STRIPE_API_KEY\"]"],
    ["DB_PASSWORD = os.getenv(\"DB_PASSWORD\", \"\")"],
    ["PASSWORD_MIN_LENGTH = 12"],
    ["def parse_settings(body):",
     "    return yaml.safe_load(body)"],
    ["def parse_json(request):",
     "    return json.loads(request.data)"],
    ["def etag(content: bytes):",
     "    return hashlib.md5(content).hexdigest()"],
    ["def hash_password_safe(password):",
     "    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())"],
    ["def parse_literal(value):",
     "    return ast.literal_eval(value)"],
    ["@route(\"/health\")",
     "def health():",
     "    return {\"status\": \"ok\"}"],
    ["@route(\"/admin/stats\")",
     "@require_admin",
     "def admin_stats():",
     "    return stats.collect()"],
]

FILLER = [
    ["def format_money(amount, currency=\"EUR\"):",
     "    return f\"{amount:,.2f} {currency}\""],
    ["def chunked(items, size):",
     "    for i in range(0, len(items), size):",
     "        yield items[i:i + size]"],
    ["class {Name}Repository:",
     "    def __init__(self, session):",
     "        self.session = session",
     "",
     "    def get(self, pk):",
     "        return self.session.get({Name}, pk)",
     "",
     "    def list(self, limit=50):",
     "        return self.session.query({Name}).limit(limit).all()"],
    ["@dataclass",
     "class {Name}Dto:",
     "    id: int",
     "    name: str",
     "    created_at: datetime"],
    ["def paginate(query, page, per_page=20):",
     "    page = max(1, int(page))",
     "    return query.offset((page - 1) * per_page).limit(per_page)"],
    ["def slugify(text):",
     "    text = re.sub(r\"[^a-zA-Z0-9]+\", \"-\", text).strip(\"-\")",
     "    return text.lower()"],
    ["logger = logging.getLogger(__name__)"],
    ["def retry(fn, attempts=3):",
     "    for i in range(attempts):",
     "        try:",
     "            return fn()",
     "        except TimeoutError:",
     "            logger.warning(\"retry %s\", i)",
     "    raise TimeoutError(\"gave up\")"],
    ["@route(\"/{lower}s\")",
     "@require_login",
     "def list_{lower}s():",
     "    return [{Name}Dto(**row.__dict__) for row in repo.list()]"],
    ["def validate_email(value):",
     "    if \"@\" not in value:",
     "        raise ValueError(\"invalid email\")",
     "    return value.strip().lower()"],
    ["def to_cents(amount):",
     "    return int(round(float(amount) * 100))"],
]

NOUNS = ["Invoice", "Customer", "Shipment", "Product", "Coupon", "Ticket", "Report", "Account",
         "Payment", "Warehouse", "Supplier", "Review", "Session", "Webhook", "Address", "Refund"]
DIRS = ["app/routes", "app/services", "app/models", "app/utils", "app/workers", "config", "scripts",
        "app/integrations"]
HEADER = ["import os", "import re", "import json", "import logging", "import hashlib",
          "import subprocess", "from pathlib import Path", "from datetime import datetime",
          "from dataclasses import dataclass"]

_TASKS = [("ca-train-1", "train", 31), ("ca-train-2", "train", 32), ("ca-train-3", "train", 33),
          ("ca-test-1", "test", 41), ("ca-test-2", "test", 42), ("ca-test-3", "test", 43)]


def build_repo(seed: int, split: str) -> tuple[dict[str, list[str]], list[tuple[str, int, str]]]:
    rng = random.Random(seed)
    paths: list[str] = []
    while len(paths) < 90:
        noun = rng.choice(NOUNS).lower()
        p = f"{rng.choice(DIRS)}/{noun}_{rng.choice(['api', 'service', 'store', 'tasks', 'helpers', 'views'])}.py"
        if p not in paths:
            paths.append(p)
    files = {p: [] for p in paths}

    # choose 6 vulnerabilities from 6 different categories
    cats = rng.sample(CATEGORIES, 6)
    planted: list[tuple[str, list[str]]] = []
    for i, cat in enumerate(cats):
        pool = VULNS[cat]["train"] if split == "train" else (
            VULNS[cat]["test"] if i % 2 == 0 else VULNS[cat]["train"])
        planted.append((cat, rng.choice(pool)))
    vuln_files = rng.sample(paths, len(planted))
    decoy_files = rng.sample(paths, 10)
    decoys = rng.sample(DECOYS, 10)

    inserts: dict[str, list[tuple[str | None, list[str]]]] = {p: [] for p in paths}
    for (cat, snippet), p in zip(planted, vuln_files):
        inserts[p].append((cat, snippet))
    for d, p in zip(decoys, decoy_files):
        inserts[p].append((None, d))

    truth: list[tuple[str, int, str]] = []
    for p in paths:
        name = p.split("/")[-1].split("_")[0].capitalize()
        lines = rng.sample(HEADER, rng.randint(3, 6)) + [""]
        blocks: list[tuple[str | None, list[str]]] = []
        for _ in range(rng.randint(3, 6)):
            blk = rng.choice(FILLER)
            blocks.append((None, [l.replace("{Name}", name).replace("{lower}", name.lower()) for l in blk]))
        for item in inserts[p]:
            blocks.insert(rng.randint(0, len(blocks)), item)
        for cat, blk in blocks:
            lines.append("")
            for l in blk:
                if "#!" in l:
                    l = l.replace("  #!", "").replace("#!", "")
                    truth.append((p, len(lines) + 1, cat or ""))
                lines.append(l)
        files[p] = lines
    return files, truth


class CodeAudit(Environment):
    name = "codeaudit"
    brief = ("A collection of Python web-service repositories. Each task is one repository of "
             "around ninety files. You can list files, read them, and file findings. Findings use "
             "these categories: " + ", ".join(CATEGORIES) + ". Findings are compared with the real "
             "issues in the repository; a finding counts if the file and category match and the "
             "line is within 3 lines of the issue.")
    max_steps = 14

    def tasks(self, split: str) -> list[Task]:
        return [Task(tid, sp, f"Review repository {tid} and report every security vulnerability "
                              f"in it with `report`. Missed issues and false reports both lower the score.",
                     {"seed": seed})
                for tid, sp, seed in _TASKS if sp == split]

    def _start(self, task: Task) -> None:
        self.files, self.truth = build_repo(task.params["seed"], task.split)
        self.findings: list[dict] = []

    def list_files(self) -> list[dict]:
        return [{"path": p, "lines": len(l)} for p, l in sorted(self.files.items())]

    def read_file(self, path: str, start: int = 1, end: int | None = None) -> str:
        if path not in self.files:
            raise ValueError(f"no such file '{path}'")
        lines = self.files[path]
        start = max(1, int(start))
        end = min(len(lines), int(end) if end else start + 149, start + 149)
        return "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(start, end + 1))

    def report(self, path: str, line: int, category: str, note: str = "") -> str:
        category = category.strip().lower()
        if category not in CATEGORIES:
            raise ValueError(f"unknown category '{category}'. Use one of {CATEGORIES}")
        if path not in self.files:
            raise ValueError(f"no such file '{path}'")
        if len(self.findings) >= 25:
            raise ValueError("report limit (25) reached")
        for f in self.findings:
            if f["path"] == path and f["category"] == category and abs(f["line"] - int(line)) <= 3:
                return "duplicate of an earlier finding; ignored"
        self.findings.append({"path": path, "line": int(line), "category": category, "note": note[:200]})
        return f"recorded finding #{len(self.findings)}"

    def actions(self) -> list[Action]:
        obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
        return [
            Action("list_files", "All files in the repository with their line counts.", obj({}), self.list_files),
            Action("read_file", "Read a file with line numbers (up to 150 lines per call).",
                   obj({"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}},
                       ["path"]), self.read_file),
            Action("report", "File one finding.",
                   obj({"path": {"type": "string"}, "line": {"type": "integer"},
                        "category": {"type": "string", "enum": CATEGORIES}, "note": {"type": "string"}},
                       ["path", "line", "category"]), self.report),
        ]

    def score(self, answer: str) -> tuple[float, str]:
        matched_truth, matched = set(), 0
        for f in self.findings:
            for i, (p, ln, cat) in enumerate(self.truth):
                if i not in matched_truth and f["path"] == p and f["category"] == cat and abs(f["line"] - ln) <= 3:
                    matched_truth.add(i)
                    matched += 1
                    break
        n_rep, n_true = len(self.findings), len(self.truth)
        precision = matched / n_rep if n_rep else 0.0
        recall = matched / n_true if n_true else 0.0
        f1 = 2 * precision * recall / (precision + recall) if matched else 0.0
        missed = sorted({self.truth[i][2] for i in range(n_true) if i not in matched_truth})
        note = (f"{n_rep} findings, {matched} correct, {n_true - matched} of {n_true} issues missed "
                f"(missed categories: {', '.join(missed) or 'none'}); precision {precision:.2f}, "
                f"recall {recall:.2f}, F1 {f1:.2f}")
        return round(f1, 3), note
