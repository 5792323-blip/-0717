"""Alpha Ranking Shadow覆盖率、稳定性和换手诊断。"""


def 诊断排序(records):
    valid = [row for row in records if row.get("排名")]
    candidate_sets = [set(row.get("候选股票", [])) for row in valid]
    changes = []
    for before, after in zip(candidate_sets, candidate_sets[1:]):
        union = before | after
        changes.append(1.0 - len(before & after) / len(union) if union else 0.0)
    scores = [item.get("Alpha评分") for row in valid for item in row.get("排名", [])]
    return {
        "记录数": len(records),
        "有效排序数": len(valid),
        "有效覆盖率": len(valid) / max(len(records), 1),
        "平均候选数": sum(len(items) for items in candidate_sets) / max(len(candidate_sets), 1),
        "候选平均变化率": sum(changes) / max(len(changes), 1),
        "评分最小值": min(scores) if scores else None,
        "评分最大值": max(scores) if scores else None,
        "评分平均值": sum(scores) / len(scores) if scores else None,
    }
