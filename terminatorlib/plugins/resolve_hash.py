from terminatorlib.plugin import URLHandler

from resolvehash.resolvehash import parse_config, find_hash

AVAILABLE = ["ResolveHashURLHandler"]


class ResolveHashURLHandler(URLHandler):
    capabilities = ["url_handler"]
    handler_name = "resolve_hash"
    name = "Nasqueron Resolve Hash"

    # Long enough hexadecimal expressions are good hash candidates
    match = r"\b[0-9a-f]{7,40}\b"

    def __init__(self):
        URLHandler.__init__(self)
        self.config = parse_config()

    def callback(self, needle_hash):
        try:
            final_url = find_hash(self.config, needle_hash)

            if final_url.startswith("http"):
                return final_url

        except Exception:
            pass

        return None
