"""Run one extraction system over one split, shardable, with an on-disk LLM cache.

python src/run_system.py --system s1 --split dev --prompt v1 [--shard 0 --nshards 4] [--threads 10]
Systems: s0 rules | s1 llm_zero | s2 llm_valid | s3 llm_fewshot | s4 claude_ref
Writes runs/<tag>_<split>.shard<i>.jsonl : {id, claims, raw, attempts, latency_s, completion_tokens}
Heldout splits (h1,h2) refuse to run unless --open-heldout NAME is given and the pre-registration file hash
recorded in docs/PREREG.sha256 matches docs/PREREG.md (opening is logged to runs/OPEN_LOG.jsonl).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, DATA, jl_read, sha256_file  # noqa: E402
import extractors as X  # noqa: E402

MODEL = os.path.join(os.path.expanduser("~"), "lab-e", "models", os.environ.get("LABE_MODEL", "qwen2.5-1.5b-instruct-q4_k_m.gguf"))
RUNS = os.path.join(ROOT, "runs")
CACHE = os.path.join(ROOT, "llm-io")


def guard_heldout(split, name):
    if split not in ("h1", "h2", "real"):
        return
    pre, shaf = os.path.join(ROOT, "docs", "PREREG.md"), os.path.join(ROOT, "docs", "PREREG.sha256")
    if not name or not os.path.exists(shaf) or open(shaf).read().split()[0] != sha256_file(pre):
        sys.exit(f"REFUSED: {split} is held-out; needs --open-heldout and a PREREG.sha256 matching PREREG.md")
    from preregister import verify
    try:
        verify()
    except ValueError as exc:
        sys.exit("REFUSED: " + str(exc))
    os.makedirs(RUNS, exist_ok=True)
    with open(os.path.join(RUNS, "OPEN_LOG.jsonl"), "a") as f:
        f.write(json.dumps(dict(split=split, who=name, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                prereg_sha=sha256_file(pre))) + "\n")


class Llama3B:
    def __init__(self, threads):
        from llama_cpp import Llama
        self.m = Llama(model_path=MODEL, n_ctx=4096, n_threads=threads, verbose=False)
        self.tag = os.path.basename(MODEL).replace(".gguf", "")

    def chat(self, messages, max_tokens=320):
        key = hashlib.sha256((self.tag + json.dumps(messages) + str(max_tokens)).encode()).hexdigest()
        p = os.path.join(CACHE, key[:2], key + ".json")
        if os.path.exists(p):
            return json.load(open(p))
        t = time.time()
        o = self.m.create_chat_completion(messages=messages, max_tokens=max_tokens, temperature=0, seed=7)
        r = dict(text=o["choices"][0]["message"]["content"], tokens=o["usage"]["completion_tokens"],
                 latency_s=round(time.time() - t, 2))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(r, open(p, "w"))
        return r


class LlamaServer:
    """llama.cpp llama-server (OpenAI-compatible) over HTTP. Used for the GPU host; same cache and prompts."""

    def __init__(self, url, tag):
        from runtime_identity import validate_endpoint
        validate_endpoint(url)
        self.url, self.tag = url.rstrip("/"), tag
        self.metadata = json.load(open(os.path.join(ROOT, "docs", "MODELS.json")))
        self.identity = self.check_identity()

    def check_identity(self):
        import urllib.request
        from runtime_identity import cache_identity
        props = json.load(urllib.request.urlopen(self.url + "/props", timeout=15))
        return cache_identity(props, self.tag, self.metadata)

    def chat(self, messages, max_tokens=320):
        import urllib.request
        identity = self.check_identity()  # refuse a restarted/swapped server before even opening a cache file
        if identity != self.identity:
            raise ValueError("Runtime identity changed during the experiment")
        backend = self.metadata["backend"]
        if max_tokens != backend["max_completion_tokens"]:
            raise ValueError("Completion limit differs from frozen decoding")
        key = hashlib.sha256((identity + json.dumps(messages) + str(max_tokens)).encode()).hexdigest()
        p = os.path.join(CACHE, key[:2], key + ".json")
        if os.path.exists(p):
            return json.load(open(p))
        t = time.time()
        body = json.dumps(dict(messages=messages, max_tokens=max_tokens,
                               temperature=backend["temperature"], seed=backend["seed"])).encode()
        req = urllib.request.Request(self.url + "/v1/chat/completions", body, {"Content-Type": "application/json"})
        o = json.load(urllib.request.urlopen(req, timeout=600))
        r = dict(text=o["choices"][0]["message"]["content"], tokens=o["usage"]["completion_tokens"],
                 latency_s=round(time.time() - t, 2))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(r, open(p, "w"))
        return r


class ClaudeRef:
    tag = "claude-sonnet-cli"

    def chat(self, messages, max_tokens=320):
        # flatten to one prompt; claude CLI preserves configured user safety settings
        prompt = "\n\n".join(("Assistant: " if m["role"] == "assistant" else "") + m["content"] for m in messages)
        key = hashlib.sha256((self.tag + prompt).encode()).hexdigest()
        p = os.path.join(CACHE, key[:2], key + ".json")
        if os.path.exists(p):
            return json.load(open(p))
        t = time.time()
        out = subprocess.run(["claude", "-p", "--model", "sonnet", "--tools", "", "--no-session-persistence",
                              "--disable-slash-commands"], input=prompt,
                             capture_output=True, text=True, timeout=300,
                             cwd=os.environ.get("LABE_NEUTRAL_CWD", ROOT)).stdout
        r = dict(text=out, tokens=0, latency_s=round(time.time() - t, 2))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(r, open(p, "w"))
        return r


def build_demos(pool, k):
    from sklearn.feature_extraction.text import TfidfVectorizer
    docs = [X.text_of(e["subject"], e["body"]) for e in pool]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit(docs)
    mat = vec.transform(docs)

    def demos_for(text):
        sims = (mat @ vec.transform([text]).T).toarray().ravel()
        top = sims.argsort()[::-1][:k]
        out = []
        for i in top:
            g = dict(pool[i]["claims"])
            g = dict(g, lines=[dict(line=l["line"], desc=l["desc"], qty=l["qty"], unit_price=l["unit_price"])
                               for l in g["lines"]])
            out.append(f"EXAMPLE EMAIL:\n{docs[i]}\n\nEXAMPLE JSON:\n{json.dumps(g)}\n\n")
        return "".join(out)
    return demos_for


def run_one(system, llm, prompt_v, email, demos_for):
    text = X.text_of(email["subject"], email["body"])
    if system == "s0":
        return dict(claims=X.rules_extract(email["subject"], email["body"]), raw="", attempts=0, latency_s=0, completion_tokens=0)
    if prompt_v == "v2":
        text = X.supplier_reply(text)
    demos = demos_for(text) if system == "s3" else ""
    pr = X.PROMPTS[prompt_v].replace("{email}", text).replace("{demos}", demos)
    msgs = [{"role": "user", "content": pr}]
    r = llm.chat(msgs)
    lat, tok, attempts = r["latency_s"], r["tokens"], 1
    claims = X.normalise(X.extract_json(r["text"]))
    if system == "s1":
        return dict(claims=claims, raw=r["text"], attempts=1, latency_s=lat, completion_tokens=tok)
    why = X.validate(claims, text)
    first_raw = r["text"]
    if why:
        msgs += [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": why + " Return only the corrected JSON."}]
        r2 = llm.chat(msgs)
        lat, tok, attempts = lat + r2["latency_s"], tok + r2["tokens"], 2
        claims = X.normalise(X.extract_json(r2["text"]))
        why = X.validate(claims, text)
        if why:
            claims = dict(X.ABSTAIN)  # abstain: routes to a human
    return dict(claims=claims, raw=first_raw, attempts=attempts, latency_s=round(lat, 2), completion_tokens=tok, abstained=bool(why))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--threads", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--open-heldout", default=None)
    a = ap.parse_args()
    tag = a.tag or f"{a.system}-{a.prompt}"
    if a.split in ("h1", "h2"):
        selection = json.load(open(os.path.join(ROOT, "docs", "SELECTION.json")))
        allowed = {("s0", "v1", "s0-v1"), (selection["system"], selection["prompt"], selection["candidate"])}
        if (a.system, a.prompt, tag) not in allowed:
            sys.exit("REFUSED: held-out system/prompt/tag is not the pre-selected experiment")
        if a.system != "s0" and (not os.environ.get("LABE_SERVER_URL") or
                                   os.environ.get("LABE_MODEL_TAG", selection["model"]) != selection["model"]):
            sys.exit("REFUSED: held-out inference needs the frozen server model identity")
    guard_heldout(a.split, a.open_heldout)
    cases = {c["id"]: c for c in jl_read(os.path.join(DATA, "cases.jsonl"))}
    emails = {e["id"]: e for e in jl_read(os.path.join(DATA, "emails.jsonl"))}
    ids = sorted(i for i in emails if cases[i]["split"] == a.split)
    ids = [i for n, i in enumerate(ids) if n % a.nshards == a.shard]
    if a.limit:
        ids = ids[:a.limit]
    llm = None
    if a.system in ("s1", "s2", "s3"):
        llm = (LlamaServer(os.environ["LABE_SERVER_URL"], os.environ.get("LABE_MODEL_TAG", "qwen2.5-7b-instruct-q4_k_m"))
               if os.environ.get("LABE_SERVER_URL") else Llama3B(a.threads))
    elif a.system == "s4":
        llm = ClaudeRef()
    demos_for = None
    if a.system == "s3":
        demos_for = build_demos([dict(emails[i], claims=cases[i]["claims"]) for i in emails if cases[i]["split"] == "pool"], a.k)
    os.makedirs(RUNS, exist_ok=True)
    out = os.path.join(RUNS, f"{tag}_{a.split}.shard{a.shard}.jsonl")
    done = {r["id"] for r in jl_read(out)} if os.path.exists(out) else set()
    t0 = time.time()
    for n, i in enumerate(ids):
        if i in done:
            continue
        r = run_one(a.system, llm, a.prompt, emails[i], demos_for)
        r.update(id=i, system=tag, model=getattr(llm, "tag", "rules"), runtime_identity=getattr(llm, "identity", None))
        with open(out, "a") as f:
            f.write(json.dumps(r, sort_keys=True) + "\n")
        if n % 20 == 0:
            print(f"{tag} {a.split} shard{a.shard} {n+1}/{len(ids)} {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
