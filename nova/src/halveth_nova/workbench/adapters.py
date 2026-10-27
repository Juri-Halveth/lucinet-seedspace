"""Source adapters produce derivations and explicit coverage, never execute sources."""
from __future__ import annotations

import ast
import io
import json
import math
import struct
import wave
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ..jsonutil import sha256_bytes, strict_loads
from .graph import CONTRACT, validate_graph

MAX_BYTES = 8_000_000
MAX_TEXT = 250_000
ADAPTER_BUNDLE_VERSION = "2.0.1"


def capabilities() -> dict:
    import importlib.util
    import shutil
    return {"text": True, "python_ast": True, "declared_graph": True, "docx": True,
            "wav_signal": True, "image_pixels": importlib.util.find_spec("PIL") is not None,
            "pdf_text": importlib.util.find_spec("pypdf") is not None,
            "image_ocr": "EXPLICIT_LOCAL_VISION_DERIVATION", "video_frames": importlib.util.find_spec("av") is not None,
            "audio_transcription": "LOCAL_MODEL_DIRECTORY_REQUIRED" if importlib.util.find_spec("faster_whisper") else False,
            "image_semantic_model": "EXPLICIT_LOCAL_VISION_MODEL_REQUIRED",
            "github": bool(shutil.which("gh")), "local_model": "EXPLICIT_SELECTION_REQUIRED"}


def extract(locator: str, data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise ValueError("ADAPTER_MAX_BYTES")
    suffix = Path(locator).suffix.lower()
    result = {"contract": "nova.adapter-result.v1", "adapter_version": "1.0.0",
              "parent_digest": sha256_bytes(data), "adapter": "binary", "text": "",
              "graphs": [], "facts": {}, "gaps": [], "coverage": {"input_bytes": len(data)}}
    if suffix == ".docx":
        result["adapter"] = "docx-xml"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            parts = [x for x in z.infolist() if x.filename.startswith("word/") and
                     (x.filename == "word/document.xml" or "header" in x.filename or "footer" in x.filename)]
            if sum(x.file_size for x in parts) > MAX_BYTES:
                raise ValueError("DOCX_EXPANSION_LIMIT")
            texts = []
            for entry in parts:
                body = z.read(entry)
                if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
                    raise ValueError("DOCX_XML_DECLARATION_REJECTED")
                root = ElementTree.fromstring(body)
                texts.extend("".join(p.itertext()) for p in root.iter()
                             if p.tag.endswith("}t"))
            result["text"] = "\n".join(texts)
            result["coverage"]["xml_parts"] = [x.filename for x in parts]
            result["gaps"] = ["embedded images, layout and comments not interpreted"]
    elif suffix == ".pdf":
        result["adapter"] = "pdf-text"
        try:
            from pypdf import PdfReader
        except ImportError:
            result["gaps"] = ["PDF_TEXT_ADAPTER_UNAVAILABLE: install optional pypdf"]
            return result
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:50]
        result["text"] = "\n".join(f"[page {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(pages))
        result["coverage"].update(pages_read=len(pages), total_pages=len(reader.pages))
        result["gaps"] = ["scanned pixels and layout not interpreted"]
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        result["adapter"] = "image-pixels"
        try:
            from PIL import Image
        except ImportError:
            result["gaps"] = ["IMAGE_PIXEL_ADAPTER_UNAVAILABLE: install optional Pillow"]
            return result
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > 20_000_000:
                raise ValueError("IMAGE_PIXEL_LIMIT")
            result["facts"].update(width=im.width, height=im.height, format=im.format, frames=getattr(im, "n_frames", 1))
            thumb = im.convert("RGB"); thumb.thumbnail((128, 128))
            pixels = list(thumb.get_flattened_data() if hasattr(thumb, "get_flattened_data") else thumb.getdata())
            result["facts"]["mean_rgb"] = [round(sum(p[c] for p in pixels) / len(pixels), 3) for c in range(3)]
            result["facts"]["red_dominant_fraction"] = sum(r > 100 and r > g * 1.5 and r > b * 1.5 for r, g, b in pixels) / len(pixels)
            result["coverage"].update(sample_width=thumb.width, sample_height=thumb.height, frame=0)
            result["text"] = json.dumps(result["facts"], ensure_ascii=False)
        result["gaps"] = ["pixel statistics do not identify objects, meaning, ownership or user intent"]
    elif suffix == ".wav":
        result["adapter"] = "wav-signal"
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            result["facts"].update(channels=channels, sample_width=width, sample_rate=rate,
                                   frames=count, duration_seconds=count / rate)
            n = min(count, rate * 30)
            raw = w.readframes(n)
            if width == 2:
                samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)
                result["facts"]["rms_first_window"] = math.sqrt(sum(x * x for x in samples) / max(1, len(samples)))
            result["coverage"]["frames_read"] = n
            result["text"] = json.dumps(result["facts"])
        result["gaps"] = ["signal metadata is not speech or music recognition"]
    elif suffix in {".mp4", ".mov", ".mkv", ".mp3", ".flac", ".ogg"}:
        result["adapter"] = "timed-media"
        from .media import decode
        decoded = decode(data)
        result["facts"]["media"] = decoded
        result["text"] = json.dumps({k: v for k, v in decoded.items() if k != "frames"}, ensure_ascii=False)
        result["gaps"] = decoded.get("gaps", [decoded.get("reason", "No semantic media analysis")])
    else:
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            result["gaps"] = ["BINARY_LANGUAGE_ADAPTER_UNAVAILABLE"]
            return result
        result["adapter"] = "utf8-text"
        result["text"] = text
        if suffix == ".json":
            value = strict_loads(text)
            if isinstance(value, dict) and value.get("contract") == CONTRACT:
                result["graphs"] = [validate_graph(value)]
                result["adapter"] = "declared-concept-graph"
            elif isinstance(value, dict) and value.get("contract") == "nova.value-flow-assessment.v1":
                from .value_flow import declared_questions
                result["unknowns"] = declared_questions(value)
                result["adapter"] = "declared-value-inquiry"
        if suffix == ".py":
            result["adapter"] = "python-ast"
            tree = ast.parse(text)
            nodes = [{"id": "module", "kind": "CODE", "label": locator}]
            edges = []
            symbols = []
            for i, node in enumerate(ast.walk(tree)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append({"name": node.name, "kind": type(node).__name__, "line": node.lineno,
                                    "end_line": node.end_lineno})
                if isinstance(node, ast.Call):
                    label = ast.unparse(node.func)
                    key = f"call_{i}"
                    nodes.append({"id": key, "kind": "CODE", "label": label,
                                  "attributes": {"line": node.lineno, "end_line": node.end_lineno}})
                    edges.append({"id": "e_" + str(i), "from": "module", "to": key, "predicate": "CALLS"})
            result["facts"]["symbols"] = symbols
            if len(nodes) <= 256 and len(edges) <= 1024:
                result["graphs"] = [{"contract": CONTRACT, "id": "python_ast", "domain": "python.syntax",
                                     "nodes": nodes, "edges": edges}]
            else:
                result["gaps"].append("AST_GRAPH_LIMIT: complete graph not materialized")
            result["gaps"].append("AST call-sites do not prove runtime dispatch or behavior")
    if len(result["text"]) > MAX_TEXT:
        result["coverage"]["text_total_chars"] = len(result["text"])
        result["gaps"].append("TEXT_PREFIX_ONLY")
        result["text"] = result["text"][:MAX_TEXT]
    result["coverage"]["text_chars"] = len(result["text"])
    return result
