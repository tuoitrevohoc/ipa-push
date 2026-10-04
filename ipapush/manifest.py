"""Generate the OTA manifest.plist consumed by itms-services:// links."""

import plistlib


def build_manifest(ipa_url: str, bundle_id: str, version: str, title: str) -> bytes:
    """Return manifest.plist content (XML plist bytes)."""
    manifest = {
        "items": [
            {
                "assets": [
                    {"kind": "software-package", "url": ipa_url},
                ],
                "metadata": {
                    "bundle-identifier": bundle_id,
                    "bundle-version": str(version),
                    "kind": "software",
                    "title": title,
                },
            }
        ]
    }
    return plistlib.dumps(manifest, fmt=plistlib.FMT_XML)
