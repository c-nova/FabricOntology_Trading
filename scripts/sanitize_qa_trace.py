"""Retain visible messages and executed SQL/results, not model-internal traces."""
import json
from pathlib import Path
import sys


def sanitize(path):
    raw = json.loads(path.read_text())
    if "data" not in raw:
        return
    items = raw["data"]
    names = {x.get("call_id"): x.get("name", "") for x in items
             if x.get("type") == "function_call"}
    result = {"has_more": raw.get("has_more"), "last_id": raw.get("last_id"),
              "messages": [], "sql_executions": [], "source_expansion": []}
    for item in items:
        typ = item.get("type")
        if typ == "message":
            result["messages"].append({k: item[k] for k in ("role", "content") if k in item})
        if typ != "function_call_output":
            continue
        name = names.get(item.get("call_id"), "")
        output = item.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except ValueError:
                pass
        if name.endswith("execute_sql"):
            allowed = ("execution_index", "sql", "rows", "columns", "columns_types",
                       "is_success", "content_format", "content")
            result["sql_executions"].append(
                {k: output[k] for k in allowed if k in output}
                if isinstance(output, dict) else {"error": output})
        elif name == "ontology.context.datasources_attached":
            result["source_expansion"].append(output)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    for filename in sys.argv[1:]:
        sanitize(Path(filename))
