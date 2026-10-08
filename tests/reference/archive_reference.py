"""Reference tool for the archive: crawl every document, extract facts with
patterns, answer the question. Used only by `python -m stem selftest` and
tests."""
import re

N = r"(?P<n>[A-Z]\w+ [A-Z]\w+)"
V = r"(?P<v>\d+(?:\.\d+)?)"
Y = r"(?P<y>\d{4})"
REVENUE = [rf"{N} reported revenue of €{V} million for fiscal {Y}",
           rf"In {Y}, {N}'s revenue reached EUR {V}m",
           rf"{N}: full-year {Y} revenue came in at {V} million",
           rf"For the {Y} financial year {N} posted sales of €{V}M",
           rf"{N} closed {Y} with turnover of EUR {V} million"]
PROFILE = [r"(?P<n>[A-Z]\w+ [A-Z]\w+) is a (?P<s>\w+) company headquartered in (?P<c>\w+)\. It was founded in (?P<f>\d{4})",
           r"Founded in (?P<f>\d{4}), (?P<n>[A-Z]\w+ [A-Z]\w+) is a (?P<s>\w+) business based in (?P<c>\w+)",
           r"Based in (?P<c>\w+) since its founding in (?P<f>\d{4}), (?P<n>[A-Z]\w+ [A-Z]\w+) operates in the (?P<s>\w+) sector"]
A, T, P = r"(?P<a>[A-Z]\w+ [A-Z]\w+)", r"(?P<t>[A-Z]\w+ [A-Z]\w+)", r"(?P<p>\d+(?:\.\d+)?)"
DEALS = [rf"{A} has completed its acquisition of {T} for €{P} million\. The deal closed in \w+ {Y}",
         rf"{A} acquired {T} in \w+ {Y} in a transaction valued at EUR {P}m",
         rf"{T} is now part of {A}, which closed the purchase in \w+ {Y} for €{P} million"]


def run(env, question=""):
    docs, page = [], 1
    while True:
        listing = env.list_documents(page=page)
        docs += [env.read(doc_id=d["id"]) for d in listing["documents"]]
        if page >= listing["pages"]:
            break
        page += 1
    rev, corr, prof, deals, ren = {}, {}, {}, [], {}
    for d in docs:
        t = d["text"]
        for pat in REVENUE:
            for m in re.finditer(pat, t):
                rev[(m["n"], int(m["y"]))] = float(m["v"])
        for m in re.finditer(rf"Correction: {N}'s revenue for {Y} was €{V} million", t):
            corr[(m["n"], int(m["y"]))] = float(m["v"])
        for pat in PROFILE:
            for m in re.finditer(pat, t):
                prof[m["n"]] = (m["c"], m["s"], int(m["f"]))
        for pat in DEALS:
            for m in re.finditer(pat, t):
                deals.append((m["a"], m["t"], int(m["y"]), float(m["p"])))
        for m in re.finditer(r"(?P<o>[A-Z]\w+ [A-Z]\w+) will operate under the name (?P<n>[A-Z]\w+ [A-Z]\w+) from \w+ (?P<y>\d{4})", t):
            ren[m["o"]] = (m["n"], int(m["y"]))
    rev.update(corr)
    old_of = {new: old for old, (new, _) in ren.items()}

    def revenue(name, year):
        for cand in (name, ren.get(name, (name, 0))[0], old_of.get(name, name)):
            if (cand, year) in rev:
                return rev[(cand, year)]
        return 0.0

    def name_in(name, year):
        return ren[name][0] if name in ren and year >= ren[name][1] else name

    q = question
    if m := re.search(r"combined (\d{4}) revenue.*companies that (.+?) acquired", q):
        y, a = int(m[1]), m[2]
        return str(round(sum(revenue(t, y) for aa, t, _, _ in deals if aa == a), 1))
    if m := re.search(r"did (.+?) spend", q):
        return str(sum(p for aa, _, _, p in deals if aa == m[1]))
    if m := re.search(r"headquartered in (\w+) had the highest revenue in (\d{4})", q):
        c, y = m[1], int(m[2])
        best = max((n for n, v in prof.items() if v[0] == c), key=lambda n: revenue(n, y))
        return name_in(best, y)
    if m := re.search(r"average (\d{4}) revenue.*of the (\w+) companies founded before (\d{4})", q):
        y, s, cut = int(m[1]), m[2], int(m[3])
        chosen = [n for n, v in prof.items() if v[1] == s and v[2] < cut]
        return str(round(sum(revenue(n, y) for n in chosen) / len(chosen), 1))
    if "largest percentage revenue growth" in q:
        best = max(prof, key=lambda n: revenue(n, 2024) / (revenue(n, 2021) or 1e9))
        return name_in(best, 2024)
    return "unknown question"
