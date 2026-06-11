from hushline.embeds import EMBED_IFRAME_SANDBOX


def test_embed_iframe_sandbox_preserves_same_origin_form_origin() -> None:
    sandbox_tokens = EMBED_IFRAME_SANDBOX.split()

    assert "allow-forms" in sandbox_tokens
    assert "allow-same-origin" in sandbox_tokens
    assert "allow-scripts" in sandbox_tokens
