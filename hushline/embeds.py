import html

from hushline.external_urls import canonical_external_url
from hushline.model import Username

EMBED_IFRAME_SANDBOX = (
    "allow-forms allow-popups allow-scripts allow-top-navigation-by-user-activation"
)
EMBED_IFRAME_HEIGHT = 700
EMBED_IFRAME_MAX_WIDTH = 720


def embed_profile_url(username: Username) -> str:
    return canonical_external_url("embed_profile", username=username.username)


def embed_iframe_snippet(username: Username) -> str:
    src = html.escape(embed_profile_url(username), quote=True)
    title = html.escape(
        f"Send a secure Hush Line message to {username.display_name or username.username}"
    )
    return (
        f'<iframe src="{src}" '
        f'title="{title}" '
        f'sandbox="{EMBED_IFRAME_SANDBOX}" '
        'referrerpolicy="no-referrer" '
        'width="100%" '
        f'height="{EMBED_IFRAME_HEIGHT}" '
        f'style="width:100%;max-width:{EMBED_IFRAME_MAX_WIDTH}px;'
        f'height:{EMBED_IFRAME_HEIGHT}px;border:0;"></iframe>'
    )
