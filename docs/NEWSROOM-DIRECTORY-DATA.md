# Newsroom Directory Sync

- Source indexes:
  - `https://findyournews.org/explore/`
  - `https://journalismdirectory.org/search-networks/`
- Local artifact: `hushline/data/newsroom_directory_listings.json`
- Refresh script: `scripts/refresh_newsroom_directory_listings.py`

## Notes

- The artifact is intentionally derived only from public detail pages linked from the public browse pages above.
- The broader WordPress organization API includes records that are not visible in the public Explore experience and should not be treated as the user-facing newsroom directory.
- The European journalism source is limited to public network detail pages linked from `search-networks`; non-public submission/contact fields must not be ingested.

## Commands

Refresh the artifact:

```bash
make refresh-newsroom-listings
```

Verify the committed artifact is current:

```bash
make refresh-newsroom-listings REFRESH_NEWSROOM_ARGS="--check"
```
