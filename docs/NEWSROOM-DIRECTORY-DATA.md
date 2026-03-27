# Newsroom Directory Sync

- Source index: `https://findyournews.org/explore/`
- Local artifact: `hushline/data/newsroom_directory_listings.json`
- Refresh script: `scripts/refresh_newsroom_directory_listings.py`

## Notes

- The artifact is intentionally derived only from organization detail pages linked from the public Explore page.
- The broader WordPress organization API includes records that are not visible in the public Explore experience and should not be treated as the user-facing newsroom directory.

## Commands

Refresh the artifact:

```bash
make refresh-newsroom-listings
```

Verify the committed artifact is current:

```bash
make refresh-newsroom-listings REFRESH_NEWSROOM_ARGS="--check"
```
