"""Verify actual served properties before inference or cache reuse.

The frozen metadata records independently observed hashes of the owned host's
GGUF files. The HTTP server reports its alias/path/build, not weight hashes;
those hashes are an operational attestation, not a server cryptographic proof.
"""
import hashlib
import json
import urllib.parse


def validate_endpoint(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password:
        raise ValueError("Use a localhost HTTP server or an owned-host SSH tunnel")


def basename(path):
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def verify_props(props, tag, metadata):
    if tag not in metadata["models"]:
        raise ValueError("Unregistered model tag")
    files = metadata["models"][tag]["files"]
    first = sorted(files)[0]
    if any(basename(props.get(k, "")) != first for k in ("model_path", "model_alias")):
        raise ValueError("Served model path/alias does not match frozen weights")
    backend = metadata["backend"]
    if props.get("build_info") != f"b{backend['build']}-{backend['commit']}":
        raise ValueError("Served build does not match frozen backend")
    if props.get("total_slots") != 4 or props.get("default_generation_settings", {}).get("n_ctx") != 4096:
        raise ValueError("Server context/parallelism differs from frozen runtime")
    return props


def cache_identity(props, tag, metadata):
    verify_props(props, tag, metadata)
    identity = {"schema": 2, "model": metadata["models"][tag],
                "build": props["build_info"], "slots": props["total_slots"], "context": 4096,
                "decoding": {k: metadata["backend"][k] for k in
                             ("temperature", "seed", "max_completion_tokens")}}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
