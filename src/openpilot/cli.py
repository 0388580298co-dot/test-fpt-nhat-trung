import argparse
import json
from .agent import as_json, run
from .auto_pipeline import run_auto
from .github_tool import inspect_repository
from .pipeline import process_video
from .providers import provider_from_env
from .test_runner import run_pytest


def main():
    parser = argparse.ArgumentParser(description="OpenPilot Studio - AI Content Factory")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Create a safe plan for a task")
    plan.add_argument("task")
    plan.add_argument("--workspace", default=".")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--ai", action="store_true", help="Use the configured optional LLM provider")
    gh = sub.add_parser("github", help="Inspect a public GitHub repository (read-only)")
    gh.add_argument("repo", help="owner/repo or GitHub URL")
    test = sub.add_parser("test", help="Run the safe pytest runner")
    test.add_argument("--workspace", default=".")
    video = sub.add_parser("video", help="Process an authorized video with Whisper + SRT + 9:16 FFmpeg render")
    video.add_argument("input_video")
    video.add_argument("--output-dir", default="output")
    video.add_argument("--whisper-model", default="small")
    video.add_argument("--json", action="store_true")
    auto = sub.add_parser("auto", help="Find Douyin trend videos -> AI Vietnamese -> voice -> 9:16 render -> optional official publishing")
    auto.add_argument("--output-dir", default="output")
    auto.add_argument("--whisper-model", default="small")
    auto.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        provider = provider_from_env() if args.ai else None
        report = run(args.task, args.workspace, provider)
        if args.json:
            print(json.dumps(as_json(report), indent=2, ensure_ascii=False)); return
        print("OpenPilot Studio\n")
        for i, step in enumerate(report.plan, 1): print(f"{i}. {step}")
        print(f"\nProvider: {report.provider}")
        print("\nWorkspace:")
        for item in report.workspace_items[:20]: print(f"- {item}")
        if report.ai_summary: print("\nAI assessment:\n" + report.ai_summary)
    elif args.command == "github":
        print(json.dumps(inspect_repository(args.repo), indent=2, ensure_ascii=False))
    elif args.command == "test":
        result = run_pytest(args.workspace); print(result.stdout, end="")
        if result.stderr: print(result.stderr, end="")
        print(f"\nExit code: {result.returncode}"); raise SystemExit(result.returncode)
    elif args.command == "video":
        try: result = process_video(args.input_video, args.output_dir, args.whisper_model)
        except Exception as exc: parser.error(str(exc))
        payload = {"input_video": result.input_video, "subtitle_file": result.subtitle_file, "output_video": result.output_video, "segments": result.segments}
        if args.json: print(json.dumps(payload, indent=2, ensure_ascii=False))
        else: print(f"OpenPilot Studio - Video Pipeline\n\nInput: {result.input_video}\nSubtitle: {result.subtitle_file}\nVideo: {result.output_video}\nSegments: {result.segments}")
    elif args.command == "auto":
        try: result = run_auto(args.output_dir, args.whisper_model)
        except Exception as exc: parser.error(str(exc))
        payload = {
            "trend": result.trend, "batch_size": len(result.results), "source_url": result.source_url,
            "input_video": result.input_video, "subtitle_file": result.subtitle_file, "output_video": result.output_video,
            "status": result.status, "title": result.title, "hashtags": result.hashtags,
            "published": result.published, "message": result.message, "results": result.results,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("\nOpenPilot Studio - AUTO FINAL REPORT\n")
            print(f"Trend:       {result.trend}")
            print(f"Batch:       {len(result.results)} Douyin video")
            print(f"Status:      {result.status}")
            print(f"Manifest:    {args.output_dir}\\auto-manifest.json")
            print(f"\nFirst output: {result.output_video}")
            print(f"Subtitle:     {result.subtitle_file}")
            print(f"Title:        {result.title}")
            print(f"Hashtags:     {result.hashtags}")
            print(f"Publish:      {result.published}")
            print(f"\n{result.message}")
            print("\nCompleted outputs:")
            for item in result.results:
                if item["status"] != "failed":
                    print(f"  {item['index']:02d}. {item['output_video']}")
            failed = [item for item in result.results if item["status"] == "failed"]
            if failed:
                print("\nFailed videos:")
                for item in failed:
                    print(f"  {item['index']:02d}. {item['error']}")


if __name__ == "__main__":
    main()
