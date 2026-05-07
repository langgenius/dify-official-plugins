from __future__ import annotations

import contextlib
import json
import sys


def main() -> int:
    try:
        args = json.loads(sys.stdin.read())
    except Exception as ex:
        print(json.dumps({"status": "err", "data": f"parse args: {ex}"}))
        return 2

    try:
        with contextlib.redirect_stdout(sys.stderr):
            from dashscope.audio.asr import Recognition
    except Exception as ex:
        print(json.dumps({"status": "err", "data": f"import dashscope: {ex}"}))
        return 3

    try:
        with contextlib.redirect_stdout(sys.stderr):
            recognition = Recognition(
                model=args["model"],
                format=args["audio_format"],
                sample_rate=args["sample_rate"],
                callback=None,
            )
            result = recognition.call(
                file=args["file_path"],
                headers=args.get("headers") or {},
                api_key=args["api_key"],
                base_address=args.get("base_address"),
            )
        status_code = getattr(result, "status_code", 200)
        if status_code != 200:
            message = getattr(result, "message", None) or "Unknown DashScope error"
            print(
                json.dumps(
                    {
                        "status": "err",
                        "data": f"DashScope error: {message} ({status_code})",
                    }
                )
            )
            return 0

        sentences = result.get_sentence()
        normalized = [
            sentence if isinstance(sentence, dict) else {"text": str(sentence)}
            for sentence in (sentences or [])
        ]
        print(json.dumps({"status": "ok", "data": normalized}))
        return 0
    except Exception as ex:
        print(json.dumps({"status": "err", "data": f"{type(ex).__name__}: {ex}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
