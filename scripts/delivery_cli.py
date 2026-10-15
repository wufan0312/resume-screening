#!/usr/bin/env python3
"""投递状态管理 CLI（Phase 3）。

用法（在仓库根目录执行，确保 src 在 PYTHONPATH）：
  python scripts/delivery_cli.py init                 # 建表
  python scripts/delivery_cli.py list [--status X]    # 查看投递记录
  python scripts/delivery_cli.py stats                # 按状态统计
  python scripts/delivery_cli.py status --id 3 --status read [--note "已读"]
"""
from __future__ import annotations

import argparse
import os
import sys

# 让 src 包可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from storage.database.db import get_session
from storage.database.models.delivery import status_label
from storage.database.repo import delivery_repo


def _cmd_init(_args):
    delivery_repo.create_delivery_tables()
    print("投递相关表已创建（若不存在）。")


def _cmd_list(args):
    session = get_session()
    try:
        apps = delivery_repo.list_applications(session, status=args.status or None)
        if not apps:
            print("暂无投递记录。" if not args.status else f"状态「{args.status}」下暂无记录。")
            return
        print(f"共 {len(apps)} 条：")
        for a in apps:
            print(
                f"  #{a.id} {a.title} @ {a.company}"
                f" ｜ {status_label(a.status)} ｜ 薪资 {a.salary or '—'}"
                f" ｜ 来源 {a.source or '—'} ｜ 匹配 {a.matched_score} 分"
            )
    finally:
        session.close()


def _cmd_stats(_args):
    session = get_session()
    try:
        stats = delivery_repo.stats_with_labels(session)
        print("投递统计：")
        print(f"  总计：{stats['total']}")
        for label, cnt in stats["by_status"].items():
            print(f"  {label}：{cnt}")
    finally:
        session.close()


def _cmd_status(args):
    session = get_session()
    try:
        app = delivery_repo.update_status(session, args.id, args.status, args.note or "")
        if app is None:
            print(f"未找到 ID={args.id} 的投递记录。")
            return
        print(f"已更新 #{app.id}《{app.title} @ {app.company}》状态为：{status_label(app.status)}。")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="投递状态管理 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="创建投递相关表")

    p_list = sub.add_parser("list", help="查看投递记录")
    p_list.add_argument("--status", default="", help="状态过滤")

    sub.add_parser("stats", help="按状态统计")

    p_status = sub.add_parser("status", help="更新某条投递状态")
    p_status.add_argument("--id", type=int, required=True, help="投递记录 ID")
    p_status.add_argument(
        "--status", required=True,
        help="新状态：pending/delivered/read/replied/interview/rejected/withdrawn",
    )
    p_status.add_argument("--note", default="", help="备注")

    args = parser.parse_args()
    {"init": _cmd_init, "list": _cmd_list, "stats": _cmd_stats, "status": _cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
