#!/usr/bin/env python3
"""Baseline: send each photo and instruction to Apertus with a plain prompt. This is the score to beat.

    vllm serve swiss-ai/Apertus-v1.5-8B --chat-template-content-format string
    python baseline/baseline.py --data dataset --out results.json
    python starter/evaluate.py results.json --data dataset

No scene graph, no vision model, no tools, no constrained decoding: Apertus alone, reading
the photo and answering in JSON. Works with any OpenAI-compatible server (--base-url, --model).

    --mock      no model at all: answers "pick the centre of the image" (checks your setup)
    --limit 5   only the first 5 instructions

Writes results.json (the file you score) and results.raw.jsonl (every raw model reply).
"""
from __future__ import annotations

import argparse, base64, json, re, sys, time, urllib.error, urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "starter"))
from evaluate import answer_type  # noqa: E402
from scene_io import load_scene  # noqa: E402

PROMPT = """You control a robot arm above a table. The photo is {w} x {h} pixels.
A pixel [u, v] is column u counted from the left and row v counted from the top.
"Left" and "right" mean as seen in the photo. The gripper holds one object at a time and opens at most 85 mm.

Instruction: "{text}"

Answer with exactly one JSON object and nothing else:
- If you can do it: {{"target_pixel": [u, v], "actions": [{{"action": "pick", "object": "<name>"}}, {{"action": "place", "object": "<name>"}}]}}
  target_pixel is the pixel of the first object you pick. List picks and places in order.
- If the instruction is ambiguous: {{"target_pixel": null, "actions": [{{"action": "ask_user", "question": "<question>"}}]}}
- If it is impossible or unsafe: {{"target_pixel": null, "actions": [{{"action": "refuse", "reason": "<reason>"}}]}}"""


def encode(rgb, max_side: int):
    h, w = rgb.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    small = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode(), small.shape[1], small.shape[0], scale


def ask(base_url: str, model: str, image_b64: str, prompt: str, timeout: float) -> str:
    body = {"model": model, "temperature": 0, "max_tokens": 400, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        {"type": "text", "text": prompt}]}]}
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer none"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def parse(text: str):
    """First JSON object in the reply, or None. Plain prompting: no repair beyond this."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
        start = text.find("{", start + 1)
    return None


def rescale(ans: dict, scale: float) -> dict:
    """Pixels the model gave in the small image -> pixels in the full-resolution image."""
    fix = lambda p: [int(round(p[0] / scale)), int(round(p[1] / scale))] if isinstance(p, list) and len(p) == 2 \
        and all(isinstance(x, (int, float)) for x in p) else p
    if "target_pixel" in ans:
        ans["target_pixel"] = fix(ans["target_pixel"])
    for a in ans.get("actions", []) if isinstance(ans.get("actions"), list) else []:
        if isinstance(a, dict) and "pixel" in a:
            a["pixel"] = fix(a["pixel"])
    return ans


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("dataset"))
    ap.add_argument("--out", type=Path, default=Path("results.json"))
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="swiss-ai/Apertus-v1.5-8B")
    ap.add_argument("--max-side", type=int, default=1024, help="resize the photo so its long side is at most this")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--mock", action="store_true", help="no model: always pick the image centre")
    ap.add_argument("--team", default="baseline")
    args = ap.parse_args()

    scenes = sorted(p for p in args.data.iterdir() if p.is_dir() and (p / "rgb.png").exists())
    jobs = [(d, iid, text) for d in scenes for iid, _, text in load_scene(d).instructions]
    if args.limit:
        jobs = jobs[: args.limit]
    results, raw_path, bad, cache = [], args.out.with_suffix(".raw.jsonl"), 0, {}
    t0 = time.time()
    with raw_path.open("w") as raw:
        for n, (d, iid, text) in enumerate(jobs, 1):
            if d not in cache:
                sc = load_scene(d)
                cache = {d: (sc, *encode(sc.rgb, args.max_side))}
            sc, b64, w, h, scale = cache[d]
            if args.mock:
                reply = json.dumps({"target_pixel": [w // 2, h // 2], "actions": [{"action": "pick", "object": "object"}]})
            else:
                try:
                    reply = ask(args.base_url, args.model, b64, PROMPT.format(w=w, h=h, text=text), args.timeout)
                except (urllib.error.URLError, TimeoutError, KeyError) as e:
                    sys.exit(f"cannot reach the model at {args.base_url} ({e}). Start it first, or try --mock.")
            ans = parse(reply)
            ans = rescale(ans, scale) if isinstance(ans, dict) else {"actions": []}
            ans["instruction_id"] = iid
            kind, err = answer_type(ans)
            bad += err is not None
            results.append(ans)
            raw.write(json.dumps({"instruction_id": iid, "instruction": text, "reply": reply}) + "\n")
            print(f"[{n}/{len(jobs)}] {iid}: {kind or 'INVALID (' + err + ')'}")
    args.out.write_text(json.dumps({"team": args.team, "results": results}, indent=2))
    print(f"\n{len(results)} answers in {args.out} ({bad} do not match the schema) in {time.time() - t0:.0f}s")
    print(f"raw replies: {raw_path}\nscore it:    python starter/evaluate.py {args.out} --data {args.data}")


if __name__ == "__main__":
    main()
