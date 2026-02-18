#!/usr/bin/env python3
"""
实体分类规则测试
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.entity_classification import normalize_entity_mentions


def test_guardrail_person_to_holiday():
    """person 错分应被节日规则纠正"""
    entities = [
        {
            "mention": "退伍军人日",
            "canonical_name": "退伍军人日",
            "entity_type": "person",
            "confidence": 0.93,
        }
    ]
    result = normalize_entity_mentions(entities)
    assert result[0]["entity_type"] == "holiday"


def test_guardrail_organization_to_person():
    """organization 错分的人名应被修正"""
    entities = [
        {
            "mention": "Kurt Cobain",
            "canonical_name": "Kurt Cobain",
            "entity_type": "organization",
            "confidence": 0.88,
        }
    ]
    result = normalize_entity_mentions(entities)
    assert result[0]["entity_type"] == "person"


def test_fallback_from_plain_string():
    """仅有字符串时仍可输出可入库结构"""
    result = normalize_entity_mentions(["科罗拉多州"])
    assert result
    assert result[0]["canonical_name"] == "科罗拉多州"
    assert result[0]["entity_type"] == "location"


if __name__ == "__main__":
    test_guardrail_person_to_holiday()
    test_guardrail_organization_to_person()
    test_fallback_from_plain_string()
    print("entity_classification tests passed")
