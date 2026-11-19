from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def with_query(url: str, query: dict) -> str:
    if not url or not query:
        return url
    parts = urlsplit(url)
    merged = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in query.items():
        if value is None:
            continue
        merged[str(key)] = value if isinstance(value, str) else str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))
