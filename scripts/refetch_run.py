#!/usr/bin/env python3
"""补拉受损 run：同一 anchor 下多 reference 的候选曾因输出目录缺 reference 维度而互相覆盖。

本脚本基于 run.json 中保存的 task_id（每个 job 各自独立，未丢失），按修复后的
anchor/<reference>/candidate-0N 目录结构重新下载并回灌音频，重建 review manifest。

用法：
    python scripts/refetch_run.py <run_dir> [--config video-workspace.json] [--dry-run]

示例：
    python scripts/refetch_run.py \
        runtime/outputs/街道风/run_20260817_015910_004488
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig
from idolmv_pipeline.video_tasks.factory import adapter_from_task
from idolmv_pipeline.video_tasks.runner import VideoTaskRunner
from idolmv_pipeline.video_tasks.store import TaskStore
from idolmv_pipeline.seedance.state import RunState


def _load_env() -> None:
    """把项目根 .env 的 KEY=VALUE 注入 os.environ（不覆盖已存在的），
    确保补拉时 credentials.py 能读到 SEEDANCE_API_KEY 等。不依赖 python-dotenv。"""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def refetch(run_dir: Path, config_path: str, dry_run: bool) -> None:
    _load_env()
    run_dir = run_dir.resolve()
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        raise SystemExit(f"未找到 run.json: {run_json}")

    state = RunState(run_json)
    data = state.data
    task_id = data.get("task")
    if not task_id:
        raise SystemExit("run.json 缺少 task 字段，无法定位素材/音频配置")

    config = VideoWorkspaceConfig.load(Path(config_path))
    store = TaskStore(config)
    task = store.get(task_id)

    # skip_material_check：补拉只需 task 配置（拿到 references 做音频回灌），
    # 不强制校验素材文件存在（素材可能已就位，缺失会在 mux 阶段报错而非此处阻塞）
    adapter = adapter_from_task(task, config, store, skip_material_check=True)

    jobs = state.jobs()
    fixed = 0
    for job in jobs:
        anchor = job["anchor"]
        reference = job["reference"]
        cand = job["candidate"]
        new_dir = run_dir / anchor / reference / f"candidate-{cand:02d}"
        new_result = new_dir / "result.mp4"
        new_final = new_dir / "final.mp4"
        old_result = job.get("result")
        old_final = job.get("final")
        if old_result == str(new_result) and job.get("status") == "done":
            print(f"[skip] {job['id']} 路径已正确，无需补拉")
            continue
        # 重置为待拉取状态并指向修复后的目录；_finish_job 会因新 final 不存在而重新下载
        job["status"] = "pending"
        job.pop("error", None)
        job["result"] = str(new_result)
        job["final"] = str(new_final)
        fixed += 1
        print(f"[{'DRY' if dry_run else 'fix'}] {job['id']} -> {new_dir}")

    if dry_run:
        print(f"\n[dry-run] 将重拉 {fixed} 个候选；加 --no-dry-run 实际执行")
        return

    if fixed:
        state.save()

    print(f"\n重新拉取 {fixed} 个候选（其余已正确者跳过）...")
    # 实际拉取时才构造 runner（需要 API key）
    runner = VideoTaskRunner(adapter)
    runner.poll(run_dir.name)
    print("done. manifest 已重建于 run 目录下。")


def main() -> None:
    parser = argparse.ArgumentParser(description="补拉受损 run（多 reference 覆盖修复）")
    parser.add_argument("run_dir", help="run 目录，如 runtime/outputs/街道风/run_xxx")
    parser.add_argument("--config", default="video-workspace.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要修复的路径，不实际下载")
    args = parser.parse_args()
    refetch(Path(args.run_dir), args.config, args.dry_run)


if __name__ == "__main__":
    main()
