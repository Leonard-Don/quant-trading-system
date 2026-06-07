"""Pure K-Means clustering for IndustryAnalyzer.

Lifted out of ``IndustryAnalyzer.cluster_hot_industries`` — everything after the
momentum/money-flow frames have been fetched and merged. Takes the prepared
``merged_df`` plus the requested cluster count and returns the clustering result
dict. Pure: no instance state, no provider/network access.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


def cluster_merged_industries(
    merged_df: pd.DataFrame, n_clusters: int = 4
) -> dict[str, Any]:
    """Run K-Means over a merged momentum/money-flow frame and summarize clusters.

    Features are (涨跌幅, 资金强度, PE, PB) when available. The cluster count is
    auto-selected by silhouette score within a bounded range. Returns the same
    payload shape ``cluster_hot_industries`` historically produced.
    """
    # 准备聚类特征 (4D: 涨跌幅, 资金强度, PE, PB)
    feature_cols = ["weighted_change", "flow_strength"]
    if "pe_ttm" in merged_df.columns:
        # PE/PB 取对数或倒数处理，避免长尾影响；这里简单填充并标准化
        merged_df["pe_feat"] = merged_df["pe_ttm"].apply(
            lambda x: np.log(max(x, 1.0)) if pd.notna(x) else 0
        )
        feature_cols.append("pe_feat")
    if "pb" in merged_df.columns:
        merged_df["pb_feat"] = merged_df["pb"].apply(
            lambda x: np.log(max(x, 1.0)) if pd.notna(x) else 0
        )
        feature_cols.append("pb_feat")

    features = merged_df[feature_cols].fillna(0).values

    # 标准化特征
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    min_clusters = max(2, min(int(n_clusters or 4), len(merged_df) - 1))
    max_clusters = min(
        max(min_clusters, int(n_clusters or 4) + 2), max(2, len(merged_df) - 1), 8
    )
    selected_clusters = min_clusters
    selected_silhouette = None
    cluster_candidates: dict[int, float] = {}

    if len(merged_df) >= 4:
        for candidate in range(min_clusters, max_clusters + 1):
            if candidate >= len(merged_df):
                continue
            candidate_model = KMeans(n_clusters=candidate, random_state=42, n_init=10)
            labels = candidate_model.fit_predict(features_scaled)
            if len(set(labels)) < 2:
                continue
            try:
                cluster_candidates[candidate] = float(
                    silhouette_score(features_scaled, labels)
                )
            except Exception:
                continue

        if cluster_candidates:
            selected_clusters, selected_silhouette = max(
                cluster_candidates.items(), key=lambda item: item[1]
            )

    # K-Means 聚类
    kmeans = KMeans(n_clusters=selected_clusters, random_state=42, n_init=10)
    merged_df["cluster"] = kmeans.fit_predict(features_scaled)

    # 识别热门行业簇（平均动量最高的簇）
    cluster_stats = {}
    for i in range(selected_clusters):
        cluster_data = merged_df[merged_df["cluster"] == i]
        avg_momentum = (
            cluster_data["weighted_change"].mean() if len(cluster_data) > 0 else 0
        )
        avg_flow = cluster_data["flow_strength"].mean() if len(cluster_data) > 0 else 0
        cluster_stats[i] = {
            "count": len(cluster_data),
            "avg_momentum": float(avg_momentum) if pd.notna(avg_momentum) else 0.0,
            "avg_flow": float(avg_flow) if pd.notna(avg_flow) else 0.0,
            "industries": cluster_data["industry_name"].tolist(),
        }

    # 找出平均动量最高的簇作为热门簇
    hot_cluster = max(cluster_stats.keys(), key=lambda k: cluster_stats[k]["avg_momentum"])

    clean_df = merged_df.replace([np.inf, -np.inf], np.nan).copy()
    for column in (
        "cluster",
        "weighted_change",
        "flow_strength",
        "change_pct",
        "main_net_inflow",
        "pe_ttm",
        "pb",
    ):
        if column in clean_df.columns:
            clean_df[column] = pd.to_numeric(clean_df[column], errors="coerce").fillna(0)
    points = []
    for _, row in clean_df.iterrows():
        points.append(
            {
                "industry_name": row.get("industry_name", ""),
                "cluster": int(row.get("cluster", -1)),
                "weighted_change": float(row.get("weighted_change", 0)),
                "flow_strength": float(row.get("flow_strength", 0)),
                "change_pct": float(row.get("change_pct", row.get("weighted_change", 0))),
                "money_flow": float(row.get("main_net_inflow", 0)),
                "pe_ttm": float(row.get("pe_ttm", 0)) if pd.notna(row.get("pe_ttm")) else 0,
                "pb": float(row.get("pb", 0)) if pd.notna(row.get("pb")) else 0,
            }
        )

    return {
        "clusters": {i: stats["industries"] for i, stats in cluster_stats.items()},
        "hot_cluster": hot_cluster,
        "cluster_stats": cluster_stats,
        "points": points,
        "selected_cluster_count": selected_clusters,
        "silhouette_score": selected_silhouette,
        "cluster_candidates": cluster_candidates,
    }


__all__ = ["cluster_merged_industries"]
