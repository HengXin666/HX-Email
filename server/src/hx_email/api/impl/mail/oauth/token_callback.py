"""Token OAuth callback page rendering."""


def token_callback_html(message: str, is_error: bool = False) -> str:
    color: str = "#f85149" if is_error else "#3fb950"
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>OAuth Callback</title>"
        "</head><body style='font-family:sans-serif;background:#0d1117;color:#c9d1d9;"
        "display:grid;place-items:center;min-height:100vh;margin:0'>"
        f"<main style='max-width:520px'><h1 style='color:{color};font-size:20px'>"
        f"{message}</h1><p>可以关闭此页面。</p></main></body></html>"
    )
