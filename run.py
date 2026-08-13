#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from idolmv_pipeline.web.logging import configure as configure_logging
configure_logging()


def workspace(args):
    from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig

    return VideoWorkspaceConfig.load(Path(args.config) if getattr(args, "config", None) else None)


def video_runner(args):
    from idolmv_pipeline.video_tasks.factory import adapter_from_task
    from idolmv_pipeline.video_tasks.runner import VideoTaskRunner
    from idolmv_pipeline.video_tasks.store import TaskStore

    config = workspace(args)
    store = TaskStore(config)
    task = store.get(args.task)
    return VideoTaskRunner(adapter_from_task(task, config, store))


def cmd_anchor(args):
    from idolmv_pipeline.image_tasks.runner import AnchorTaskRunner
    from idolmv_pipeline.image_tasks.store import AnchorTaskStore

    store = AnchorTaskStore(workspace(args))
    runner = AnchorTaskRunner(store)
    if args.anchor_command == "list":
        for task in store.list():
            print(f"{task['id']}\trefs={len(task['references'])} candidates={task['candidates']} size={task['size']}")
        return
    if args.anchor_command == "validate":
        print(f"[OK] {store.load(args.task).id}")
        return
    run_id = getattr(args, "run_id", None) or datetime.now().strftime("anchor_%Y%m%d_%H%M%S")
    if args.anchor_command == "run":
        print(runner.run(args.task, run_id, args.candidates, args.submit_only).path)
    elif args.anchor_command == "resume":
        print(runner.resume(args.task, run_id).path)
    elif args.anchor_command == "status":
        print(json.dumps(runner.status(args.task, run_id), indent=2, ensure_ascii=False))


def cmd_video(args):
    if args.video_command == "web":
        from dataclasses import replace

        from idolmv_pipeline.web.server import serve

        config = workspace(args)
        overrides = {key: value for key, value in {"host": args.host, "port": args.port}.items() if value is not None}
        serve(replace(config, **overrides) if overrides else config)
        return

    if args.video_command == "list":
        from idolmv_pipeline.video_tasks.store import TaskStore

        for task in TaskStore(workspace(args)).list():
            kind = "dance" if task["mode"] == "motion" else "singing"
            if args.kind and args.kind != kind:
                continue
            print(f"{task['id']}\tkind={kind} anchors={len(task['anchors'])} refs={len(task['references'])} candidates={task['candidates']}")
        return

    if args.video_command == "tunnel":
        from idolmv_pipeline.seedance import tunnel

        if args.tunnel_command == "start":
            config = workspace(args)
            tunnel.configure(config.tunnel_root or config.project_root, config.tunnel_port)
            print(tunnel.start(args.provider))
        elif args.tunnel_command == "status":
            print(json.dumps(tunnel.status(), indent=2, ensure_ascii=False))
        else:
            tunnel.stop()
            print("Seedance tunnel stopped")
        return

    runner = video_runner(args)
    if args.video_command == "validate":
        errors = runner.validate()
        if errors:
            raise ValueError("Invalid video task:\n- " + "\n- ".join(errors))
        print(f"[OK] {args.task}")
    elif args.video_command == "prepare":
        runner.prepare()
    elif args.video_command == "upload":
        print(runner.upload(args.provider))
    elif args.video_command == "run":
        print(runner.run(args.run_id, args.candidates, args.variant, args.provider, args.submit_only).path)
    elif args.video_command == "resume":
        print(runner.resume(args.run_id).path)
    elif args.video_command == "status":
        print(json.dumps(runner.status(args.run_id), indent=2, ensure_ascii=False))



def main() -> None:
    parser = argparse.ArgumentParser(description="IdolFlow Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    anchor = sub.add_parser("anchor", help="Run GPT Image 2 Anchor tasks")
    anchor_sub = anchor.add_subparsers(dest="anchor_command", required=True)
    for command in ("list", "validate", "run", "resume", "status"):
        command_parser = anchor_sub.add_parser(command)
        command_parser.add_argument("--config", default="video-workspace.json")
        if command != "list":
            command_parser.add_argument("--task", required=True)
        if command in {"resume", "status"}:
            command_parser.add_argument("--run-id", required=True)
        if command == "run":
            command_parser.add_argument("--run-id")
            command_parser.add_argument("--candidates", type=int)
            command_parser.add_argument("--submit-only", action="store_true")
        command_parser.set_defaults(func=cmd_anchor)

    video = sub.add_parser("video", help="Run configured Seedance video tasks")
    video_sub = video.add_subparsers(dest="video_command", required=True)

    web = video_sub.add_parser("web", help="Start the generation and review workspace")
    web.add_argument("--host")
    web.add_argument("--port", type=int)
    web.add_argument("--config", default="video-workspace.json")
    web.set_defaults(func=cmd_video)

    listing = video_sub.add_parser("list", help="List configured video tasks")
    listing.add_argument("--kind", choices=["singing", "dance"])
    listing.add_argument("--config", default="video-workspace.json")
    listing.set_defaults(func=cmd_video)

    for command in ("validate", "prepare", "upload", "status", "resume"):
        command_parser = video_sub.add_parser(command)
        command_parser.add_argument("--task", required=True)
        command_parser.add_argument("--config", default="video-workspace.json")
        if command in {"status", "resume"}:
            command_parser.add_argument("--run-id", required=True)
        if command == "upload":
            command_parser.add_argument("--provider", default="auto", choices=["auto", "pinggy", "ngrok"])
        command_parser.set_defaults(func=cmd_video)

    run = video_sub.add_parser("run", help="Prepare, submit, poll, mux, and build a review manifest")
    run.add_argument("--task", required=True)
    run.add_argument("--config", default="video-workspace.json")
    run.add_argument("--run-id")
    run.add_argument("--candidates", type=int)
    run.add_argument("--variant", default="all")
    run.add_argument("--provider", default="auto", choices=["auto", "pinggy", "ngrok"])
    run.add_argument("--submit-only", action="store_true")
    run.set_defaults(func=cmd_video)

    tunnel = video_sub.add_parser("tunnel", help="Manage the Seedance asset tunnel")
    tunnel_sub = tunnel.add_subparsers(dest="tunnel_command", required=True)
    start = tunnel_sub.add_parser("start")
    start.add_argument("--provider", default="auto", choices=["auto", "pinggy", "ngrok"])
    start.add_argument("--config", default="video-workspace.json")
    start.set_defaults(func=cmd_video)
    for command in ("status", "stop"):
        command_parser = tunnel_sub.add_parser(command)
        command_parser.add_argument("--config", default="video-workspace.json")
        command_parser.set_defaults(func=cmd_video)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
