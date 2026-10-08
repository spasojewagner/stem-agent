"""A searchable archive of business news about fictional companies.

Every task has its own generated archive (~100 documents) and one question
that needs facts from many documents: acquisitions, yearly revenue, company
profiles. The archive contains the usual traps: corrections of earlier
figures, deals that were announced and then called off, companies that
changed their name. Held-out archives also use phrasings that never appear
in training archives.
"""
from __future__ import annotations

import math
import random
import re
from collections import Counter

from .base import Action, Environment, Task

PREFIX = ["Norvik", "Halden", "Aster", "Brava", "Corvel", "Delmar", "Eskil", "Fjord", "Gantry",
          "Helix", "Iberra", "Jorvik", "Kestrel", "Lumen", "Marlow", "Nexa", "Orrin", "Pellio",
          "Quarry", "Rosen", "Solvi", "Tamber", "Ulric", "Vantor"]
SUFFIX = ["Systems", "Foods", "Labs", "Logistics", "Energy", "Retail", "Holdings", "Works",
          "Analytics", "Freight"]
CITIES = ["Lisbon", "Ghent", "Tartu", "Graz", "Lyon", "Porto", "Malmo", "Brno"]
SECTORS = ["logistics", "software", "food", "energy", "retail", "biotech"]
MONTHS = ["January", "March", "April", "June", "July", "September", "October", "November"]
YEARS = [2021, 2022, 2023, 2024]

REVENUE_PHRASES = {
    "train": ["{n} reported revenue of €{v} million for fiscal {y}.",
              "In {y}, {n}'s revenue reached EUR {v}m.",
              "{n}: full-year {y} revenue came in at {v} million euros."],
    "test": ["For the {y} financial year {n} posted sales of €{v}M.",
             "{n} closed {y} with turnover of EUR {v} million."],
}
ACQ_PHRASES = {
    "train": ["{a} has completed its acquisition of {t} for €{p} million. The deal closed in {m} {y}.",
              "{a} acquired {t} in {m} {y} in a transaction valued at EUR {p}m."],
    "test": ["{t} is now part of {a}, which closed the purchase in {m} {y} for €{p} million."],
}
PROFILE_PHRASES = {
    "train": ["{n} is a {s} company headquartered in {c}. It was founded in {f}.",
              "Founded in {f}, {n} is a {s} business based in {c}."],
    "test": ["Based in {c} since its founding in {f}, {n} operates in the {s} sector."],
}
FILLER = ["The company expects demand to remain stable.", "Management highlighted cost discipline.",
          "Headcount grew to {k} employees.", "A new office opened with {k} square meters of space.",
          "The board proposed a dividend of {d} cents per share.", "Analysts had expected a weaker quarter.",
          "Investments in automation continued throughout the year."]

_TASKS = [
    ("ar-train-1", "train", 51, "acq_revenue"),
    ("ar-train-2", "train", 52, "acq_spend"),
    ("ar-train-3", "train", 53, "city_top"),
    ("ar-test-1", "test", 61, "acq_revenue"),
    ("ar-test-2", "test", 62, "sector_avg"),
    ("ar-test-3", "test", 63, "growth_top"),
]


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}"


class World:
    def __init__(self, seed: int, split: str):
        rng = self.rng = random.Random(seed)
        self.split = split
        names = rng.sample([f"{p} {s}" for p in PREFIX for s in SUFFIX], 12)
        self.companies = {n: {"city": rng.choice(CITIES), "sector": rng.choice(SECTORS),
                              "founded": rng.randint(1981, 2016)} for n in names}
        self.revenue = {}
        for n in names:
            v = rng.uniform(40, 700)
            for y in YEARS:
                v = max(15.0, v * rng.uniform(0.82, 1.3))
                self.revenue[(n, y)] = round(v, 1)
        # acquisitions
        acquirers = rng.sample(names, 3)
        pool = [n for n in names if n not in acquirers]
        rng.shuffle(pool)
        self.deals = []  # (acquirer, target, year, month, price, completed)
        for a in acquirers:
            for _ in range(rng.randint(2, 3)):
                if not pool:
                    break
                t = pool.pop()
                self.deals.append((a, t, rng.choice(YEARS[:-1]), rng.choice(MONTHS),
                                   float(rng.randint(30, 600)), True))
        for a in acquirers[:2]:   # announced, then cancelled
            t = rng.choice([n for n in names if n not in acquirers])
            self.deals.append((a, t, rng.choice(YEARS), rng.choice(MONTHS), float(rng.randint(30, 600)), False))
        # renames: two acquired companies change name in 2023
        self.renames = {}
        renamed_targets = [d[1] for d in self.deals if d[5]][:2]
        for old in renamed_targets:
            base = old.split()[0]
            new = f"{base} {rng.choice([s for s in SUFFIX if s not in old])}"
            if new not in self.companies:
                self.renames[old] = (new, 2023)
        # corrections: wrong figure published first, corrected later
        self.corrections = {}
        for n in rng.sample(names, 3):
            y = rng.choice(YEARS)
            self.corrections[(n, y)] = round(self.revenue[(n, y)] * rng.choice([1.1, 0.9, 1.2]), 1)
        self.docs = self._documents()

    def name_in(self, n: str, year: int) -> str:
        if n in self.renames and year >= self.renames[n][1]:
            return self.renames[n][0]
        return n

    def _phr(self, table: dict, **kw) -> str:
        options = table["train"] + (table["test"] * 2 if self.split == "test" else [])
        return self.rng.choice(options).format(**kw)

    def _filler(self) -> str:
        r = self.rng
        return " ".join(r.choice(FILLER).format(k=r.randint(80, 4000), d=r.randint(5, 90))
                        for _ in range(r.randint(1, 3)))

    def _documents(self) -> list[dict]:
        r, docs = self.rng, []

        def add(title: str, date: str, text: str) -> None:
            docs.append({"title": title, "date": date, "text": text})

        for n, c in self.companies.items():
            add(f"About {n}", f"{r.randint(2019, 2020)}-0{r.randint(1, 9)}-1{r.randint(0, 9)}",
                self._phr(PROFILE_PHRASES, n=n, s=c["sector"], c=c["city"], f=c["founded"]) + " " + self._filler())
        for (n, y), v in self.revenue.items():
            shown = self.corrections.get((n, y), v)
            name = self.name_in(n, y)
            title = r.choice([f"{name} annual results {y}", f"{name} {y} results",
                              f"Press release {y + 1}-0{r.randint(1, 3)}-{r.randint(10, 28)}"])
            add(title, f"{y + 1}-0{r.randint(1, 3)}-{r.randint(10, 28)}",
                self._phr(REVENUE_PHRASES, n=name, v=_fmt(shown), y=y) + " " + self._filler())
        for (n, y), wrong in self.corrections.items():
            name = self.name_in(n, y)
            add(f"Correction: {name} {y} figures", f"{y + 1}-0{r.randint(4, 9)}-0{r.randint(1, 9)}",
                f"Correction: {name}'s revenue for {y} was €{_fmt(self.revenue[(n, y)])} million, "
                f"not €{_fmt(wrong)} million as stated in an earlier release.")
        for a, t, y, m, p, done in self.deals:
            an, tn = self.name_in(a, y), self.name_in(t, y)
            if done:
                add(r.choice([f"{an} completes {tn.split()[0]} deal", f"Deal news {y}", f"{an} expands"]),
                    f"{y}-{MONTHS.index(m) + 2:02d}-15",
                    self._phr(ACQ_PHRASES, a=an, t=tn, p=_fmt(p), m=m, y=y) + " " + self._filler())
            else:
                add(f"{an} to buy {tn}", f"{y}-{MONTHS.index(m) + 2:02d}-02",
                    f"{an} announced an agreement to acquire {tn} for €{_fmt(p)} million, subject to approval.")
                add(f"{an} and {tn} end talks", f"{y}-{MONTHS.index(m) + 3:02d}-20",
                    f"{an} and {tn} have terminated their agreement; the acquisition will not proceed.")
        for old, (new, y) in self.renames.items():
            add(f"{old} becomes {new}", f"{y}-0{r.randint(1, 6)}-0{r.randint(1, 9)}",
                f"{old} will operate under the name {new} from {r.choice(MONTHS)} {y}. Nothing else changes.")
        for _ in range(16):
            n = r.choice(list(self.companies))
            add(r.choice([f"{n} opens new site", f"{n} hiring update", f"{n} product launch"]),
                f"{r.choice(YEARS)}-0{r.randint(1, 9)}-{r.randint(10, 28)}",
                f"{n} " + r.choice(["opened a facility of {k} square meters.", "plans to hire {k} people.",
                                    "launched a product line priced from €{d}."])
                .format(k=r.randint(100, 9000), d=r.randint(9, 400)) + " " + self._filler())
        r.shuffle(docs)
        for i, d in enumerate(docs, 1):
            d["id"] = f"D{i:03d}"
        return docs

    # -- questions ------------------------------------------------------------
    def question(self, kind: str) -> tuple[str, str, float | str]:
        r = self.rng
        done = [d for d in self.deals if d[5]]
        if kind == "acq_revenue":
            a = max({d[0] for d in done}, key=lambda x: sum(1 for d in done if d[0] == x and d[1] in self.renames))
            y = 2024
            targets = [d[1] for d in done if d[0] == a]
            ans = round(sum(self.revenue[(t, y)] for t in targets), 1)
            return (f"What was the combined {y} revenue, in million EUR, of all companies that {a} acquired? "
                    "Count completed acquisitions only. Answer with one number.", "number", ans)
        if kind == "acq_spend":
            a = sorted({d[0] for d in self.deals if not d[5]})[0]
            ans = sum(d[4] for d in done if d[0] == a)
            return (f"How much did {a} spend in total, in million EUR, on acquisitions completed "
                    f"between 2021 and 2024? Answer with one number.", "number", ans)
        if kind == "city_top":
            cities = Counter(c["city"] for c in self.companies.values())
            city = max(cities, key=lambda c: (cities[c], c))
            y = 2023
            members = [n for n, c in self.companies.items() if c["city"] == city]
            best = max(members, key=lambda n: self.revenue[(n, y)])
            return (f"Which company headquartered in {city} had the highest revenue in {y}? "
                    f"Answer with the company's name as it was in {y}.", "name", self.name_in(best, y))
        if kind == "sector_avg":
            sectors = Counter(c["sector"] for c in self.companies.values())
            sector = max(sectors, key=lambda s: (sectors[s], s))
            members = sorted((n for n, c in self.companies.items() if c["sector"] == sector),
                             key=lambda n: self.companies[n]["founded"])
            cutoff = self.companies[members[-1]]["founded"] if len(members) > 2 else 2100
            chosen = [n for n in members if self.companies[n]["founded"] < cutoff]
            y = 2022
            ans = round(sum(self.revenue[(n, y)] for n in chosen) / len(chosen), 1)
            return (f"What was the average {y} revenue, in million EUR rounded to one decimal, of the "
                    f"{sector} companies founded before {cutoff}? Answer with one number.", "number", ans)
        if kind == "growth_top":
            best = max(self.companies, key=lambda n: self.revenue[(n, 2024)] / self.revenue[(n, 2021)])
            return ("Which company had the largest percentage revenue growth from 2021 to 2024? "
                    "Answer with the company's name as it was in 2024.", "name", self.name_in(best, 2024))
        raise ValueError(kind)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Archive(Environment):
    name = "archive"
    brief = ("A news archive about a set of companies: press releases, results announcements, deal "
             "news, profiles. Each task comes with its own archive of about a hundred documents and "
             "one question. You can search the archive, list it page by page, and read documents. "
             "The question is answered once, with finish(answer).")
    max_steps = 14

    def tasks(self, split: str) -> list[Task]:
        out = []
        for tid, sp, seed, kind in _TASKS:
            if sp != split:
                continue
            q, _, _ = World(seed, sp).question(kind)
            out.append(Task(tid, sp, f"Archive {tid}. {q}", {"seed": seed, "kind": kind}))
        return out

    def _start(self, task: Task) -> None:
        self.world = World(task.params["seed"], task.split)
        _, self.answer_kind, self.expected = self.world.question(task.params["kind"])
        self.docs = {d["id"]: d for d in self.world.docs}
        self._df = Counter(t for d in self.world.docs for t in set(_tokens(d["title"] + " " + d["text"])))

    def search(self, query: str) -> list[dict]:
        q = _tokens(query)
        n = len(self.docs)
        scored = []
        for d in self.docs.values():
            toks = _tokens(d["title"] + " " + d["text"])
            tf = Counter(toks)
            s = sum(tf[t] * math.log((n + 1) / (self._df.get(t, 0) + 1)) for t in q)
            if s > 0:
                scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        return [{"id": d["id"], "title": d["title"], "date": d["date"], "snippet": d["text"][:140]}
                for _, d in scored[:6]]

    def list_documents(self, page: int = 1) -> dict:
        ids = sorted(self.docs)
        page = max(1, int(page))
        chunk = ids[(page - 1) * 30: page * 30]
        return {"page": page, "pages": math.ceil(len(ids) / 30),
                "documents": [{"id": i, "title": self.docs[i]["title"], "date": self.docs[i]["date"]} for i in chunk]}

    def read(self, doc_id: str) -> dict:
        d = self.docs.get(doc_id.strip().upper())
        if not d:
            raise ValueError(f"no document '{doc_id}'")
        return {"id": d["id"], "title": d["title"], "date": d["date"], "text": d["text"]}

    def actions(self) -> list[Action]:
        obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
        return [
            Action("search", "Keyword search over titles and text.",
                   obj({"query": {"type": "string"}}, ["query"]), self.search,
                   'list of up to 6 {"id", "title", "date", "snippet"}'),
            Action("list_documents", "List the archive, 30 documents per page (page starts at 1).",
                   obj({"page": {"type": "integer"}}), self.list_documents,
                   '{"page", "pages", "documents": [{"id", "title", "date"}]}'),
            Action("read", "Read one document in full.", obj({"doc_id": {"type": "string"}}, ["doc_id"]), self.read,
                   '{"id", "title", "date", "text"}'),
        ]

    def score(self, answer: str) -> tuple[float, str]:
        if self.answer_kind == "number":
            nums = [float(x.replace(" ", "").replace(",", "")) for x in
                    re.findall(r"-?\d[\d,]*(?:\.\d+)?", answer or "")]
            got = nums[-1] if nums else None
            ok = got is not None and abs(got - self.expected) <= max(0.6, abs(self.expected) * 0.005)
            note = f"answered {got}, expected {self.expected}"
        else:
            text = (answer or "").lower()
            others = [n for n in list(self.world.companies) + [v[0] for v in self.world.renames.values()]
                      if n.lower() in text and n != self.expected]
            ok = self.expected.lower() in text and not others
            note = f"answered '{(answer or '')[:60]}', expected '{self.expected}'"
        return (1.0 if ok else 0.0), note + (" -> correct" if ok else " -> wrong")
