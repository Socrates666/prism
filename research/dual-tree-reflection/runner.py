"""research/dual-tree-reflection/runner.py — D1 实验 runner（二重树反思能力验证）。

用法:
  python runner.py --one <prompt.md> --condition tree|base --out runs/<dir> [--max-turns N]
      单 subject 子进程模式: cwd 切到 out 目录, 独立跑一只小白鼠。
  python runner.py --all [--jobs 6] [--max-turns N] [--only game1,game2]
      编排模式: prompts/*.md × {tree, base} 并发生成子进程, stdout 落各 run.log。
  python runner.py --smoke
      冒烟: 第一条 prompt × tree 条件, max_turns=3, 验证装配(reflect 工具/树/事件落盘)。

条件:
  tree = SQLiteForest + enable_cognitive_cycle(启发式直觉) + reflect 工具装配(审计修复的最小 wiring, 零 core 改动)
  base = NullForest, 无认知层(对照组: 无树时模型自发反思的水平)

采集证据(每 run 目录): events.jsonl(订阅事件流) / memory/<name>.json(FileMemory transcript)
  / forest.db(仅 tree) / game.html(agent 产出) / run.log(stdout) / meta.json
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
RUNS_DIR = EXP_DIR / "runs"

# 记录进 events.jsonl 的事件类型(discard message_update/reasoning 增量: 太碎, transcript 已有全文)
_RECORDED_EVENTS = {"agent_start", "agent_end", "turn_start", "turn_end", "message_end",
                    "tool_execution_start", "tool_execution_end", "cognitive",
                    "error", "patch_error", "user_input"}

# 两组共用的中性系统提示基底(角色/环境)。绝不提树/反思 —— 不引导证人。
_BASE_PROMPT = """## 角色
你是一个能干的前端工程师 agent, 在独立的沙盒工作目录里完成任务。

## 环境
- 你有 python 工具: 在当前工作目录的共享命名空间里执行 Python 代码(可写文件、读文件、运行检查、定义变量复用)。
- 当前工作目录是你本次任务的专属沙盒, 所有产出文件都写在这里。
- 认真读需求里的精确规则(数值、时序、边界), 交付前自测。
- 完成任务后不再调用工具, 直接给出最终答复。"""


def run_subject(prompt_path: Path, condition: str, out_dir: Path, name: str,
                max_turns: int) -> int:
    """单 subject: cwd=out_dir, 组装 agent, 跑任务, 落盘证据。返回进程退出码。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    import os
    os.chdir(out_dir)                       # python 工具的文件操作落在本沙盒

    from prism.agent import Agent
    from prism.model import OpenAIModel
    from prism.memory import FileMemory

    started = time.time()
    task = prompt_path.read_text(encoding="utf-8")
    events_path = out_dir / "events.jsonl"
    ev_f = open(events_path, "a", encoding="utf-8")

    def on_event(event: dict) -> None:
        if event.get("type") in _RECORDED_EVENTS:
            rec = dict(event)
            if "result" in rec and isinstance(rec["result"], str):
                rec["result"] = rec["result"][:2000]      # 工具结果截断, 防膨胀
            rec["_t"] = round(time.time() - started, 1)
            ev_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ev_f.flush()

    model = OpenAIModel()                    # PRISM_MODEL / OPENAI_* 环境变量
    agent = Agent(name, model=model, kind="main", actor=False,
                  memory=FileMemory(out_dir / "memory"), max_turns=max_turns,
                  append_system_prompt=[_BASE_PROMPT])
    agent.subscribe(on_event)

    forest_path = None
    if condition == "tree":
        # 最小 wiring(审计修复清单第一项): 认知周期 + reflect 工具 —— 全在 runner 层, 不改 core
        from prism.forest import SQLiteForest
        from prism.cog_patches import enable_cognitive_cycle
        from prism.cog_tools import make_reflect_tool
        forest = SQLiteForest(out_dir / "forest.db", session_id=name)
        agent.forest = forest
        enable_cognitive_cycle(agent, intuition_model=None)   # 启发式直觉(无额外小模型调用)
        agent.add_tool(make_reflect_tool(agent))
        assert "reflect" in [t.name for t in agent._tools()], "reflect 工具未装配!"
        forest_path = str(out_dir / "forest.db")

    agent.run(task)
    ev_f.close()

    game = out_dir / "game.html"
    meta = {"name": name, "condition": condition, "prompt": str(prompt_path),
            "max_turns": max_turns, "forest": forest_path,
            "started": started, "finished": time.time(),
            "duration_s": round(time.time() - started, 1),
            "game_html_bytes": game.stat().st_size if game.exists() else 0,
            "last_result": (agent.last_result or "")[:2000]}
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return 0


def orchestrate(jobs: int, max_turns: int, only: list[str] | None,
                per_subject_timeout: int = 2700) -> None:
    """全量编排: prompts/*.md × {tree, base} → 子进程并发池。"""
    sys.path.insert(0, str(PROJECT_ROOT))
    prompts = sorted(EXP_DIR.glob("prompts/[0-9]*.md"))
    if only:
        prompts = [p for p in prompts if p.stem.split("-", 1)[-1] in only
                   or p.stem in only]
    if not prompts:
        sys.exit("prompts/ 下没有任务文件")
    subjects = []
    for p in prompts:
        for cond in ("tree", "base"):
            subjects.append((p, cond, RUNS_DIR / f"{p.stem}-{cond}"))
    print(f"[orchestrator] {len(prompts)} prompts x 2 conditions = {len(subjects)} subjects, jobs={jobs}, max_turns={max_turns}")
    results: dict[str, str] = {}

    def spawn(prompt: Path, cond: str, out: Path) -> tuple[str, str]:
        name = out.name
        out.mkdir(parents=True, exist_ok=True)
        log = open(out / "run.log", "w", encoding="utf-8")
        cmd = [sys.executable, str(Path(__file__).resolve()), "--one", str(prompt),
               "--condition", cond, "--out", str(out), "--max-turns", str(max_turns),
               "--name", name]
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                  cwd=PROJECT_ROOT, timeout=per_subject_timeout)
            status = "ok" if proc.returncode == 0 else f"exit={proc.returncode}"
        except subprocess.TimeoutExpired:
            status = f"timeout>{per_subject_timeout}s"
        except Exception as e:
            status = f"spawn_error: {e}"
        finally:
            log.close()
        return name, status

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futs = {pool.submit(spawn, p, c, o): o.name for p, c, o in subjects}
        for fut in as_completed(futs):
            name, status = fut.result()
            results[name] = status
            print(f"  [{len(results)}/{len(subjects)}] {name}: {status}  (+{round(time.time()-t0)}s)")
    (RUNS_DIR / "orchestrator.json").write_text(
        json.dumps({"finished": time.time(), "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[orchestrator] done in {round(time.time()-t0)}s -> {RUNS_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--condition", choices=["tree", "base"], default="tree")
    ap.add_argument("--out")
    ap.add_argument("--name")
    ap.add_argument("--max-turns", type=int, default=25)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", help="逗号分隔的游戏 slug 过滤")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        first = sorted(EXP_DIR.glob("prompts/[0-9]*.md"))
        if not first:
            sys.exit("冒烟需要 prompts/ 里至少一个任务文件")
        rc = run_subject(first[0], "tree", RUNS_DIR / "_smoke", "smoke-mouse", max_turns=3)
        print(f"[smoke] exit={rc}")
        return
    if args.all:
        only = [s.strip() for s in args.only.split(",")] if args.only else None
        orchestrate(args.jobs, args.max_turns, only)
        return
    if not (args.one and args.out):
        sys.exit("需要 --one + --out, 或 --all / --smoke")
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        rc = run_subject(Path(args.one).resolve(), args.condition, Path(args.out).resolve(),
                         args.name or Path(args.out).name, args.max_turns)
        sys.exit(rc)
    except Exception:
        traceback.print_exc()
        (Path(args.out) / "CRASH.txt").write_text(traceback.format_exc(), encoding="utf-8")
        sys.exit(1)


if __name__ == "__main__":
    main()
