"""Build the data toolkit site from what actually exists and runs.

Everything on the site is collected at build time from five places:
  - the Python code in src/            -> call graph (parsed with ast)
  - the dbt project in dbt/            -> lineage, tests, descriptions
  - the Power BI project in dashboards/ -> report lineage, relationships, measures
  - BigQuery                            -> schemas, row counts, job history, samples, test results
  - the GitHub Actions API              -> workflow run history

Run from the repo root (needs `gcloud auth application-default login`):
    python toolkit/build.py
Then open docs/index.html (GitHub Pages serves it from docs/).
"""

import ast
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import urllib.request

import yaml
from google.cloud import bigquery

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = "dynamic-pricing-tracker"
REGION = "region-europe-west2"
REPO = "Osmane97/Dynamic-Pricing-Project"
DATASETS = ["amazon_raw", "dbt_prod"]
PROD = "dbt_prod"
JOB_DAYS = 30

client = bigquery.Client(project=PROJECT)


def query(sql):
    return [dict(row.items()) for row in client.query(sql).result()]


def rel(path):
    return path.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- git

def git_info():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "commit_date": git("log", "-1", "--format=%cI"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "commits": int(git("rev-list", "--count", "HEAD") or 0),
    }


# ---------------------------------------------------------------- python call graph

def dotted(node):
    """Turn a.b.c into ['a', 'b', 'c']; None when the chain does not start with a name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    if isinstance(node, ast.Call):  # e.g. datetime.now(...).isoformat
        inner = dotted(node.func)
        return inner + parts[::-1] if inner else None
    return None


def library_of(qualified):
    top = qualified.split(".")[0]
    if qualified.startswith("google.cloud.bigquery"):
        return "google-cloud-bigquery"
    if top == "selenium":
        return "selenium"
    if top == "dotenv":
        return "python-dotenv"
    return f"stdlib: {top}"


def python_call_graph():
    functions, calls, externals, config_reads = {}, {}, {}, {}
    modules = {}
    for path in sorted((ROOT / "src").rglob("*.py")):
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        if module.endswith("__init__"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = alias.name
        defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        constants = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
                     if isinstance(t, ast.Name) and t.id.isupper()]
        modules[module] = {"path": rel(path), "functions": list(defs), "constants": constants,
                           "imports": sorted(set(imports.values()))}

        # Which local variables hold library objects (driver = webdriver.Chrome(), job = client.load_...)
        var_lib, return_lib = {}, {}

        def lib_of_call(call):
            chain = dotted(call.func)
            if not chain:
                return None
            if chain[0] in imports and not imports[chain[0]].startswith("src."):
                return library_of(imports[chain[0]])
            if chain[0] in var_lib and len(chain) > 1:
                return var_lib[chain[0]]
            if len(chain) == 1 and chain[0] in return_lib:  # driver = create_driver()
                return return_lib[chain[0]]
            return None

        for _ in range(3):
            for name, fn in defs.items():
                for node in ast.walk(fn):
                    if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
                        lib = lib_of_call(node.value)
                        if lib:
                            return_lib[name] = lib
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    lib = lib_of_call(node.value)
                    if lib:
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                var_lib[target.id] = lib
                elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.iter, ast.Call):
                    lib = lib_of_call(node.iter)  # for row in driver.find_elements(...)
                    if lib and isinstance(node.target, ast.Name):
                        var_lib[node.target.id] = lib

        def resolve(func_node):
            chain = dotted(func_node)
            if not chain:
                return None
            head = chain[0]
            if len(chain) == 1:
                if head in defs:
                    return ("internal", f"{module}.{head}")
                if head in imports:
                    q = imports[head]
                    return ("internal", q) if q.startswith("src.") else ("external", q)
                return None  # builtin such as print or len
            if head in imports:
                q = ".".join([imports[head], *chain[1:]])
                return ("internal", q) if q.startswith("src.") else ("external", q)
            if head in var_lib:
                return ("external", f"{var_lib[head]}::{head}.{'.'.join(chain[1:])}")
            return None  # method on a str, dict or list

        def collect(caller, body_node):
            for node in ast.walk(body_node):
                if isinstance(node, ast.Call):
                    target = resolve(node.func)
                    if not target:
                        continue
                    kind, name = target
                    if kind == "internal":
                        calls[(caller, name)] = calls.get((caller, name), 0) + 1
                    else:
                        if "::" in name:
                            lib, member = name.split("::")
                        else:
                            lib, member = library_of(name), name
                        ext = externals.setdefault(lib, {})
                        ext.setdefault(member, set()).add(caller)
                        calls[(caller, f"lib:{lib}")] = calls.get((caller, f"lib:{lib}"), 0) + 1
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    if imports.get(node.value.id) == "src.config":
                        config_reads.setdefault(caller, set()).add(node.attr)

        for name, fn in defs.items():
            qual = f"{module}.{name}"
            functions[qual] = {
                "module": module, "name": name, "path": rel(path), "line": fn.lineno,
                "end": fn.end_lineno, "args": [a.arg for a in fn.args.args],
                "doc": ast.get_docstring(fn) or "",
            }
            collect(qual, fn)
        # module-level code, e.g. the `if __name__ == "__main__"` guard
        for node in tree.body:
            if isinstance(node, ast.If):
                collect(f"{module}:__main__", node)
                if any(isinstance(n, ast.Call) for n in ast.walk(node)):
                    functions[f"{module}:__main__"] = {
                        "module": module, "name": "__main__", "path": rel(path), "line": node.lineno,
                        "end": node.end_lineno, "args": [], "doc": "Entry point for python -m " + module,
                    }

    for caller, attrs in config_reads.items():
        calls[(caller, "src.config")] = len(attrs)
    return {
        "modules": modules,
        "functions": functions,
        "externals": {lib: {m: sorted(c) for m, c in members.items()} for lib, members in externals.items()},
        "config_reads": {k: sorted(v) for k, v in config_reads.items()},
        "edges": [{"from": a, "to": b, "count": n} for (a, b), n in sorted(calls.items())],
    }


# ---------------------------------------------------------------- dbt

def dbt_project():
    dbt_dir = ROOT / "dbt"
    project = yaml.safe_load((dbt_dir / "dbt_project.yml").read_text(encoding="utf-8"))
    folder_config = (project.get("models") or {}).get(project["name"], {}) or {}

    models = {}
    for path in sorted((dbt_dir / "models").rglob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        folder = path.parent.name
        mat = (folder_config.get(folder) or {}).get("+materialized", "view")
        override = re.search(r"config\([^)]*materialized\s*=\s*['\"](\w+)['\"]", sql)
        if override:
            mat = override.group(1)
        models[path.stem] = {
            "name": path.stem, "path": rel(path), "folder": folder, "materialized": mat, "sql": sql,
            "refs": sorted(set(re.findall(r"ref\(\s*['\"](\w+)['\"]\s*\)", sql))),
            "sources": sorted(set(".".join(s) for s in re.findall(
                r"source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)", sql))),
            "description": "", "columns": {},
        }

    sources, tests = {}, []
    for path in sorted((dbt_dir / "models").rglob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for src in doc.get("sources", []):
            for table in src.get("tables", []):
                key = f"{src['name']}.{table['name']}"
                sources[key] = {
                    "name": key, "dataset": src.get("schema", src["name"]), "table": table["name"],
                    "description": table.get("description", ""), "path": rel(path),
                    "columns": {c["name"]: c.get("description", "") for c in table.get("columns", [])},
                }
        for model in doc.get("models", []):
            target = models.get(model["name"])
            if not target:
                continue
            target["description"] = model.get("description", "")
            for col in model.get("columns", []):
                target["columns"][col["name"]] = col.get("description", "")
                for test in col.get("data_tests", col.get("tests", [])) or []:
                    if isinstance(test, str):
                        tests.append({"model": model["name"], "column": col["name"], "type": test, "args": {}})
                    else:
                        (ttype, cfg), = test.items()
                        args = (cfg or {}).get("arguments", cfg or {})
                        tests.append({"model": model["name"], "column": col["name"], "type": ttype, "args": args})
    return {"name": project["name"], "models": models, "sources": sources, "tests": tests}


# ---------------------------------------------------------------- Power BI

def parse_tmdl_table(text):
    lines = text.splitlines()
    table = {"name": lines[0].split(" ", 1)[1].strip().strip("'"), "columns": [], "measures": [], "source": None}
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\tmeasure (.+?) =\s*(.*)$", line)
        if m:
            name, rest = m.group(1).strip().strip("'"), m.group(2)
            expr = []
            if rest.strip() == "```":
                i += 1
                while not lines[i].strip() == "```":
                    expr.append(lines[i].strip("\t"))
                    i += 1
            elif rest.strip():
                expr.append(rest)
            else:
                while i + 1 < len(lines) and lines[i + 1].startswith("\t\t\t"):
                    i += 1
                    expr.append(lines[i][3:])
            measure = {"name": name, "expression": "\n".join(e for e in expr).strip(), "format": ""}
            while i + 1 < len(lines) and (lines[i + 1].startswith("\t\t") or not lines[i + 1].strip()):
                i += 1
                fm = re.match(r"^\t\tformatString: (.*)$", lines[i])
                if fm:
                    measure["format"] = fm.group(1)
            table["measures"].append(measure)
        c = re.match(r"^\tcolumn (.+)$", line)
        if c:
            column = {"name": c.group(1).strip().strip("'"), "dataType": ""}
            while i + 1 < len(lines) and (lines[i + 1].startswith("\t\t") or not lines[i + 1].strip()):
                i += 1
                dm = re.match(r"^\t\tdataType: (.*)$", lines[i])
                if dm:
                    column["dataType"] = dm.group(1)
            table["columns"].append(column)
        i += 1
    schema = re.search(r'Name="([^"]+)",Kind="Schema"', text)
    tbl = re.search(r'Name="([^"]+)",Kind="Table"', text)
    mode = re.search(r"^\t\tmode: (\w+)", text, re.M)
    if schema and tbl:
        table["source"] = {"dataset": schema.group(1), "table": tbl.group(1),
                           "mode": mode.group(1) if mode else ""}
    for measure in table["measures"]:
        measure["refs_columns"] = sorted(set(re.findall(r"(\w+)\[(\w+)\]", measure["expression"])))
        measure["refs_measures"] = sorted(set(re.findall(r"(?<![\w\]])\[([^\]]+)\]", measure["expression"])))
    return table


def walk_fields(node, found):
    """Collect (entity, property) pairs from a visual.json query."""
    if isinstance(node, dict):
        expr = node.get("Expression")
        if isinstance(expr, dict) and "Property" in node:
            entity = expr.get("SourceRef", {}).get("Entity")
            if entity:
                found.add((entity, node["Property"]))
        for value in node.values():
            walk_fields(value, found)
    elif isinstance(node, list):
        for value in node:
            walk_fields(value, found)


def power_bi():
    base = ROOT / "dashboards"
    pbip = next(base.glob("*.pbip"))
    name = pbip.stem
    model_dir = base / f"{name}.SemanticModel" / "definition"
    tables = []
    for path in sorted((model_dir / "tables").glob("*.tmdl")):
        if path.stem.startswith(("LocalDateTable", "DateTableTemplate")):
            continue  # Power BI's hidden auto date tables
        tables.append(parse_tmdl_table(path.read_text(encoding="utf-8")))
    relationships = []
    rel_text = (model_dir / "relationships.tmdl").read_text(encoding="utf-8")
    for block in re.split(r"\n(?=relationship )", rel_text):
        frm = re.search(r"fromColumn: (\S+)", block)
        to = re.search(r"toColumn: (\S+)", block)
        if frm and to and "LocalDateTable" not in block:
            card = re.search(r"fromCardinality: (\w+)", block)
            relationships.append({"from": frm.group(1), "to": to.group(1),
                                  "cardinality": f"{card.group(1) if card else 'many'} to one"})

    visuals = []
    report_dir = base / f"{name}.Report" / "definition" / "pages"
    for page_path in sorted(report_dir.glob("*/page.json")):
        page = json.loads(page_path.read_text(encoding="utf-8"))
        for vpath in sorted(page_path.parent.glob("visuals/*/visual.json")):
            v = json.loads(vpath.read_text(encoding="utf-8"))
            vis = v.get("visual", {})
            fields = set()
            walk_fields(vis.get("query", {}), fields)
            title = ""
            try:
                title = vis["visualContainerObjects"]["title"][0]["properties"]["text"]["expr"]["Literal"]["Value"].strip("'")
            except (KeyError, IndexError, TypeError):
                pass
            if not title:
                try:  # KPI cards keep their label in objects.label
                    title = vis["objects"]["label"][0]["properties"]["text"]["expr"]["Literal"]["Value"].strip("'")
                except (KeyError, IndexError, TypeError):
                    pass
            if vis.get("visualType") == "textbox" or not fields:
                continue
            visuals.append({"id": v.get("name"), "type": vis.get("visualType"), "title": title,
                            "page": page.get("displayName"), "fields": sorted(fields)})
    return {"name": name, "path": rel(pbip), "tables": tables, "relationships": relationships, "visuals": visuals}


# ---------------------------------------------------------------- GitHub Actions

def workflow():
    path = next((ROOT / ".github" / "workflows").glob("*.yml"))
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = wf.get("on", wf.get(True, {})) or {}
    job = next(iter(wf["jobs"].values()))
    steps = []
    service_account = command = ""
    for step in job.get("steps", []):
        steps.append(step.get("name") or step.get("uses"))
        if "google-github-actions/auth" in str(step.get("uses", "")):
            service_account = step.get("with", {}).get("service_account", "")
        if "run" in step and "python -m" in step["run"]:
            command = step["run"].strip()
    return {
        "name": wf.get("name"), "path": rel(path),
        "cron": [s["cron"] for s in triggers.get("schedule", [])],
        "manual": "workflow_dispatch" in triggers, "runner": job.get("runs-on"),
        "steps": steps, "service_account": service_account, "command": command,
    }


def workflow_runs():
    url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=100"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "data-toolkit-build"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as exc:  # offline build still works
        return {"error": str(exc), "runs": []}
    runs = []
    for r in data.get("workflow_runs", []):
        start = dt.datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
        runs.append({"started": r["run_started_at"], "event": r["event"], "status": r["status"],
                     "conclusion": r["conclusion"], "minutes": round((end - start).total_seconds() / 60, 1),
                     "url": r["html_url"]})
    return {"error": None, "runs": runs}


# ---------------------------------------------------------------- BigQuery

def bq_tables():
    tables = {}
    for dataset in DATASETS:
        for item in client.list_tables(f"{PROJECT}.{dataset}"):
            t = client.get_table(item.reference)
            key = f"{dataset}.{t.table_id}"
            tables[key] = {
                "id": key, "dataset": dataset, "name": t.table_id, "type": t.table_type,
                "rows": t.num_rows, "bytes": t.num_bytes,
                "created": t.created.isoformat() if t.created else None,
                "modified": t.modified.isoformat() if t.modified else None,
                "partitioning": (f"{t.time_partitioning.type_} on {t.time_partitioning.field}"
                                 if t.time_partitioning else None),
                "partition_expiry_days": (round(t.time_partitioning.expiration_ms / 86400000)
                                          if t.time_partitioning and t.time_partitioning.expiration_ms else None),
                "clustering": t.clustering_fields,
                "columns": [{"name": f.name, "type": f.field_type, "mode": f.mode,
                             "bq_description": f.description or ""} for f in t.schema],
            }
    return tables


def bq_jobs():
    """Who wrote and read which table in the last JOB_DAYS days, from BigQuery's own job log."""
    rows = query(f"""
        select
            user_email,
            job_type,
            statement_type,
            destination_table.dataset_id as dest_dataset,
            destination_table.table_id as dest_table,
            array(select distinct concat(r.dataset_id, '.', r.table_id)
                  from unnest(referenced_tables) r) as refs,
            creation_time,
            error_result is not null as failed,
            total_bytes_processed
        from `{REGION}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
        where creation_time > timestamp_sub(current_timestamp(), interval {JOB_DAYS} day)
    """)
    writes, reads = {}, {}
    for r in rows:
        # keep service accounts by name; hide personal email addresses
        if "gserviceaccount.com" not in r["user_email"]:
            r["user_email"] = "personal account"

        dest = (f"{r['dest_dataset']}.{r['dest_table']}"
                if r["dest_dataset"] and not r["dest_dataset"].startswith("_") else None)
        stamp = r["creation_time"].isoformat()
        if dest and r["dest_dataset"] in DATASETS:
            key = (r["user_email"], dest, r["job_type"], r["statement_type"] or "")
            w = writes.setdefault(key, {"count": 0, "failed": 0, "last": stamp, "first": stamp})
            w["count"] += 1
            w["failed"] += int(r["failed"])
            w["last"] = max(w["last"], stamp)
            w["first"] = min(w["first"], stamp)
        for ref in r["refs"] or []:
            if ref.split(".")[0] not in DATASETS or ref == dest:
                continue
            key = (r["user_email"], ref)
            rd = reads.setdefault(key, {"count": 0, "last": stamp})
            rd["count"] += 1
            rd["last"] = max(rd["last"], stamp)
    return {
        "days": JOB_DAYS, "total": len(rows),
        "writes": [{"user": u, "table": t, "job_type": j, "statement": s, **v}
                   for (u, t, j, s), v in sorted(writes.items())],
        "reads": [{"user": u, "table": t, **v} for (u, t), v in sorted(reads.items())],
    }


def bq_profile(tables):
    """Sample rows and per-column stats for every table."""
    for key, t in tables.items():
        cols = [c for c in t["columns"] if c["type"] not in ("RECORD", "STRUCT", "JSON")]
        exprs = ["count(*) as _rows"]
        for i, c in enumerate(cols):
            exprs.append(f"countif(`{c['name']}` is null) as n{i}")
            exprs.append(f"approx_count_distinct(`{c['name']}`) as d{i}")
            if c["type"] in ("INTEGER", "INT64", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC",
                             "TIMESTAMP", "DATE", "DATETIME"):
                exprs.append(f"cast(min(`{c['name']}`) as string) as lo{i}")
                exprs.append(f"cast(max(`{c['name']}`) as string) as hi{i}")
        stats = query(f"select {', '.join(exprs)} from `{PROJECT}.{key}`")[0]
        total = stats["_rows"] or 0
        t["row_count"] = total
        for i, c in enumerate(cols):
            c["null_pct"] = round(100 * stats[f"n{i}"] / total, 1) if total else None
            c["distinct"] = stats[f"d{i}"]
            c["min"] = stats.get(f"lo{i}")
            c["max"] = stats.get(f"hi{i}")
        names = {c["name"] for c in t["columns"]}
        order = next((o for o in ("scrape_time", "last_seen_at") if o in names), None)
        sample = query(f"select * from `{PROJECT}.{key}` "
                       f"{'order by ' + order + ' desc' if order else ''} limit 5")
        t["sample"] = [{k: (v.isoformat() if hasattr(v, "isoformat") else
                            float(v) if type(v).__name__ == "Decimal" else v)
                        for k, v in row.items()} for row in sample]
        top = {}
        for c in cols:
            if c["type"] == "STRING" and c["distinct"] and c["distinct"] <= 2000:
                vals = query(f"select `{c['name']}` v, count(*) n from `{PROJECT}.{key}` "
                             f"where `{c['name']}` is not null group by 1 order by n desc limit 3")
                top[c["name"]] = [{"value": v["v"], "count": v["n"]} for v in vals]
        t["top_values"] = top


# ---------------------------------------------------------------- data quality

def test_sql(test):
    table = f"`{PROJECT}.{PROD}.{test['model']}`"
    col = f"`{test['column']}`"
    kind, args = test["type"], test["args"]
    if kind == "unique":
        return (f"select count(*) from (select {col} from {table} where {col} is not null "
                f"group by {col} having count(*) > 1)")
    if kind == "not_null":
        return f"select count(*) from {table} where {col} is null"
    if kind == "accepted_values":
        values = ", ".join(f"'{v}'" for v in args["values"])
        return f"select count(*) from {table} where {col} is not null and cast({col} as string) not in ({values})"
    if kind == "relationships":
        parent = re.search(r"ref\(['\"](\w+)['\"]\)", args["to"]).group(1)
        return (f"select count(*) from {table} c left join `{PROJECT}.{PROD}.{parent}` p "
                f"on c.{col} = p.`{args['field']}` where c.{col} is not null and p.`{args['field']}` is null")
    return None


def quality(dbt, tables, jobs):
    gates = []
    for test in dbt["tests"]:
        sql = test_sql(test)
        if not sql:
            continue
        failures = list(query(sql)[0].values())[0]
        label = test["type"]
        if test["type"] == "relationships":
            parent = re.search(r"ref\(['\"](\w+)", test["args"]["to"]).group(1)
            label = f"relationships → {parent}.{test['args']['field']}"
        elif test["type"] == "accepted_values":
            label = f"accepted_values {test['args']['values']}"
        gates.append({"kind": "dbt test", "target": f"{PROD}.{test['model']}", "column": test["column"],
                      "check": label, "failures": failures, "status": "pass" if failures == 0 else "fail",
                      "sql": sql, "source": "dbt/models (re-run against dbt_prod at build time)"})

    # Freshness of raw data: 4 scheduled runs a day, so more than 12 hours means a run was missed.
    fresh = query(f"select timestamp_diff(current_timestamp(), max(scrape_time), minute) m "
                  f"from `{PROJECT}.amazon_raw.gpu_scrapes`")[0]["m"]
    hours = round(fresh / 60, 1)
    gates.append({"kind": "monitor", "target": "amazon_raw.gpu_scrapes", "column": "scrape_time",
                  "check": "freshness: last scrape within 12 h (warn) / 24 h (fail)",
                  "failures": None, "value": f"{hours} h ago",
                  "status": "pass" if hours <= 12 else "warn" if hours <= 24 else "fail",
                  "sql": "select max(scrape_time) from amazon_raw.gpu_scrapes"})

    # dbt_prod lags raw by up to a day because the job runs daily at 07:00 UTC.
    lag = query(f"select timestamp_diff((select max(scrape_time) from `{PROJECT}.amazon_raw.gpu_scrapes`),"
                f" (select max(scrape_time) from `{PROJECT}.{PROD}.fct_prices`), minute) m")[0]["m"]
    lag_h = round(lag / 60, 1)
    gates.append({"kind": "monitor", "target": f"{PROD}.fct_prices", "column": "scrape_time",
                  "check": "dbt_prod lags raw by at most 30 h (daily build)",
                  "failures": None, "value": f"{lag_h} h behind raw",
                  "status": "pass" if lag_h <= 30 else "fail",
                  "sql": "max(raw.scrape_time) - max(fct_prices.scrape_time)"})

    # Rows per scraper run: a new run starts after a 30-minute gap between scrapes.
    runs = query(f"""
        with t as (
            select scrape_time, currency,
                   if(timestamp_diff(scrape_time, lag(scrape_time) over (order by scrape_time), minute) > 30
                      or lag(scrape_time) over (order by scrape_time) is null, 1, 0) as new_run
            from `{PROJECT}.amazon_raw.gpu_scrapes`
        ), r as (select *, sum(new_run) over (order by scrape_time) as run_id from t)
        select run_id, min(scrape_time) as started, count(*) as rows_loaded,
               string_agg(distinct currency) as currency
        from r group by run_id order by run_id
    """)
    run_list = [{"started": r["started"].isoformat(), "rows": r["rows_loaded"], "currency": r["currency"]}
                for r in runs]
    median = statistics.median([r["rows"] for r in run_list]) if run_list else 0
    low = [r for r in run_list if r["rows"] < 0.5 * median]
    gates.append({"kind": "monitor", "target": "amazon_raw.gpu_scrapes", "column": "(rows per run)",
                  "check": "each run loads at least half the median rows",
                  "failures": len(low), "value": f"{len(low)} of {len(run_list)} runs low (median {median:g})",
                  "status": "pass" if not low else "warn", "sql": "rows grouped into runs by 30-minute gaps"})

    # Spec completeness: share of scrapes where the spec table could not be read.
    spec = query(f"select round(100 * countif(brand = 'unknown' or brand is null) / count(*), 1) p "
                 f"from `{PROJECT}.amazon_raw.gpu_scrapes`")[0]["p"]
    gates.append({"kind": "monitor", "target": "amazon_raw.gpu_scrapes", "column": "brand",
                  "check": "specs missing in at most 20% of scrapes",
                  "failures": None, "value": f"{spec}% missing",
                  "status": "pass" if spec <= 20 else "warn",
                  "sql": "countif(brand = 'unknown') / count(*)"})

    # Documentation coverage: every column in BigQuery has a dbt description.
    missing = []
    for key, t in tables.items():
        name = t["name"]
        documented = (dbt["models"].get(name, {}).get("columns")
                      or dbt["sources"].get(f"amazon_raw.{name}", {}).get("columns") or {})
        for c in t["columns"]:
            if not documented.get(c["name"]):
                missing.append(f"{key}.{c['name']}")
    gates.append({"kind": "monitor", "target": "all tables", "column": "(descriptions)",
                  "check": "every column is documented in dbt",
                  "failures": len(missing), "value": ", ".join(missing) or "all documented",
                  "status": "pass" if not missing else "warn", "sql": "dbt YAML vs BigQuery schema"})

    # Failed BigQuery jobs that wrote to pipeline tables.
    failed = sum(w["failed"] for w in jobs["writes"])
    gates.append({"kind": "monitor", "target": "BigQuery jobs", "column": f"(last {jobs['days']} days)",
                  "check": "no failed load or build jobs",
                  "failures": failed, "value": f"{failed} failed",
                  "status": "pass" if failed == 0 else "warn",
                  "sql": "INFORMATION_SCHEMA.JOBS_BY_PROJECT where error_result is not null"})
    return {"gates": gates, "runs": run_list}


# ---------------------------------------------------------------- main

def main():
    print("Reading code, dbt, Power BI and workflow ...")
    data = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": PROJECT, "repo": REPO,
        "git": git_info(),
        "python": python_call_graph(),
        "dbt": dbt_project(),
        "powerbi": power_bi(),
        "workflow": workflow(),
    }
    print("Reading GitHub Actions runs ...")
    data["workflow_runs"] = workflow_runs()
    print("Reading BigQuery schemas, jobs and data ...")
    data["tables"] = bq_tables()
    data["jobs"] = bq_jobs()
    bq_profile(data["tables"])
    print("Running data quality gates ...")
    data["quality"] = quality(data["dbt"], data["tables"], data["jobs"])

    template = (ROOT / "toolkit" / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    out = ROOT / "docs" / "index.html"
    out.write_text(template.replace("/*__DATA__*/null", payload), encoding="utf-8")
    passed = sum(g["status"] == "pass" for g in data["quality"]["gates"])
    print(f"Wrote {rel(out)}: {len(data['tables'])} tables, {passed}/{len(data['quality']['gates'])} gates passing")


if __name__ == "__main__":
    main()
