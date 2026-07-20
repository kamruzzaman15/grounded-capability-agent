"""Three tools. Each returns a dict with an "ok" flag so the agent observes
failure as data rather than an exception.

- web_search : DuckDuckGo, no API key. Empty results is a handled failure.
- fetch_url  : single attempt. Retry and fallback are the node's job, so a
               failure is visible in the trace and the counters.
- calculator : arithmetic only, via AST. Rejects names, calls, attributes.
"""

import ast
import operator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression):
    try:
        tree = ast.parse(expression, mode="eval")
        return {"ok": True, "result": _eval_node(tree.body), "expr": expression}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"calculator error: {e}", "expr": expression}


def web_search(query, max_results=5):
    try:
        try:
            from ddgs import DDGS  # package renamed from duckduckgo_search
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                url = r.get("href") or r.get("link") or r.get("url") or ""
                results.append(
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("body", "") or r.get("snippet", ""),
                        "url": url,
                    }
                )
        if not results:
            return {"ok": False, "error": "no results found", "results": []}
        return {"ok": True, "results": results}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"search error: {e}", "results": []}


def fetch_url(url, max_chars=2500):
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(
            url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (capability-agent)"}
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.extract()
        text = " ".join(soup.get_text(" ").split())
        return {"ok": True, "text": text[:max_chars], "url": url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"fetch error: {e}", "url": url}
