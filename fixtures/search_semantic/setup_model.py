"""Download only public model assets; inference never downloads anything."""

import argparse
import json
from pathlib import Path
from urllib.request import urlretrieve

from academic_search.semantic import MODEL_ID, REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for remote, local in (("onnx/model.onnx", "model.onnx"), ("tokenizer.json", "tokenizer.json"),
                          ("README.md", "MODEL_CARD.md")):
        path = args.directory / local
        urlretrieve(f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{remote}", path)
        sizes[local] = path.stat().st_size
    (args.directory / "revision.txt").write_text(REVISION + "\n")
    print(json.dumps({"revision": REVISION, "bytes": sizes, "total_bytes": sum(sizes.values())}))


if __name__ == "__main__":
    main()
