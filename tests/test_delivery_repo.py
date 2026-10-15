"""Phase 3（投递执行 + 状态追踪）仓储层单测。

用内存 SQLite 验证：建表、落库待投递、去重、状态更新、过滤、统计。
无需真实 PostgreSQL。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from storage.database.shared.model import Base
from storage.database.models.delivery import Application, DeliveryStatus
from storage.database.repo import delivery_repo


def _make_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


_SAMPLE_MATCHES = [
    {
        "title": "高级前端开发工程师",
        "company": "示例科技",
        "location": "深圳",
        "salary": "20-35K",
        "url": "https://www.zhipin.com/job/1",
        "description": "React/Next.js/TS",
        "source": "boss",
        "extra": {"experience": "5-10年"},
        "score": 88,
        "matched_points": ["React", "Next.js"],
        "recommendation": "强烈推荐",
        "greeting": "您好，我看到贵司前端岗位，很契合我的经验。",
    },
    {
        "title": "初级测试",
        "company": "低分公司",
        "location": "北京",
        "salary": "8-12K",
        "source": "boss",
        "score": 40,  # 低于 60，不应落库
        "greeting": "",
    },
]


def test_persist_and_dedup():
    s = _make_session()
    try:
        apps = delivery_repo.persist_match_plan(s, _SAMPLE_MATCHES, profile="前端/AI 求职者")
        assert len(apps) == 1, "仅 score>=60 的应落库"
        assert apps[0]["title"] == "高级前端开发工程师"
        assert apps[0]["status"] == DeliveryStatus.PENDING.value

        # 去重：再次落库相同岗位，不应新增
        apps2 = delivery_repo.persist_match_plan(s, _SAMPLE_MATCHES, profile="更新画像")
        assert len(apps2) == 1, "pending 去重应生效"
        total = s.query(Application).count()
        assert total == 1
    finally:
        s.close()


def test_update_status():
    s = _make_session()
    try:
        delivery_repo.persist_match_plan(s, _SAMPLE_MATCHES, profile="p")
        app = s.query(Application).first()
        updated = delivery_repo.update_status(s, app.id, DeliveryStatus.DELIVERED.value, note="已投")
        assert updated.status == DeliveryStatus.DELIVERED.value
        assert updated.applied_at is not None
        assert updated.note == "已投"

        # 再更新为面试邀约
        delivery_repo.update_status(s, app.id, DeliveryStatus.INTERVIEW.value)
        assert s.get(Application, app.id).status == DeliveryStatus.INTERVIEW.value
    finally:
        s.close()


def test_list_and_stats():
    s = _make_session()
    try:
        delivery_repo.persist_match_plan(s, _SAMPLE_MATCHES, profile="p")
        delivery_repo.update_status(s, 1, DeliveryStatus.DELIVERED.value)

        delivered = delivery_repo.list_applications(s, status=DeliveryStatus.DELIVERED.value)
        assert len(delivered) == 1

        all_apps = delivery_repo.list_applications(s)
        assert len(all_apps) == 1

        stats = delivery_repo.get_stats(s)
        assert stats["total"] == 1
        assert stats[DeliveryStatus.DELIVERED.value] == 1
        assert stats[DeliveryStatus.PENDING.value] == 0

        labeled = delivery_repo.stats_with_labels(s)
        assert labeled["total"] == 1
        assert "已投递" in labeled["by_status"]
    finally:
        s.close()


def test_status_label():
    from storage.database.models.delivery import status_label

    assert status_label("delivered") == "已投递"
    assert status_label("unknown") == "unknown"


if __name__ == "__main__":
    test_persist_and_dedup()
    test_update_status()
    test_list_and_stats()
    test_status_label()
    print("ALL_DELIVERY_TESTS_PASSED")
