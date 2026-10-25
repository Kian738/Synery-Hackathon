"""Independent reconstruction measurements. Source JSON is used only after import."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import math

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree


def ratio(n, d):
    return n / d if d else 1.0


def polygon(points):
    p = Polygon(points)
    return p if p.is_valid else p.buffer(0)


def match_spaces(truth, predicted, threshold=.5):
    left, right = list(truth), list(predicted)
    overlaps = np.zeros((len(left), len(right)))
    intersections = []
    shapes = list(predicted.values())
    tree = STRtree(shapes)
    for i, tid in enumerate(left):
        candidates = []
        for j in tree.query(truth[tid]):
            j = int(j)
            intersection = truth[tid].intersection(shapes[j]).area
            if intersection <= 0:
                continue
            union = truth[tid].area + shapes[j].area - intersection
            overlaps[i, j] = intersection / max(union, 1e-9)
            if intersection / max(min(truth[tid].area, shapes[j].area), 1e-9) >= .5:
                candidates.append(j)
        intersections.append(candidates)
    match, scores = {}, []
    if overlaps.size:
        # Maximize the number of eligible matches first, then their IoU.
        weights = (overlaps >= threshold) * (min(overlaps.shape) + 1) + overlaps
        rows, cols = linear_sum_assignment(-weights)
        for i, j in zip(rows, cols):
            if overlaps[i, j] >= threshold:
                match[left[i]] = right[j]
                scores.append(float(overlaps[i, j]))
    merged = sum(sum(j in candidates for candidates in intersections) > 1 for j in range(len(right)))
    split = sum(len(candidates) > 1 for candidates in intersections)
    return match, scores, merged, split


def adjacency(data, include_outside=False, step_free=False):
    graph = nx.Graph()
    graph.add_nodes_from(s['id'] for s in data['spaces'])
    for opening in data.get('openings', []):
        ids = opening['space_ids']
        if len(ids) != 2 or (not include_outside and 'outside' in ids):
            continue
        if step_free and not opening.get('step_free', True):
            continue
        graph.add_edge(*ids)
    for connector in data.get('vertical_connectors', []):
        if step_free and not connector.get('step_free', connector['kind'] == 'lift'):
            continue
        ids = connector['space_ids']
        pairs = combinations(ids, 2) if connector['kind'] == 'lift' else zip(ids, ids[1:])
        graph.add_edges_from(pairs)
    return graph


def component_ids(graph):
    return {sid: i for i, component in enumerate(nx.connected_components(graph)) for sid in component}


def pair_agreement(truth, predicted, match):
    """All source pairs, with unmatched spaces penalized; outside is never a shortcut."""
    ids = sorted(truth.nodes)
    total = len(ids) * (len(ids)-1) // 2
    if not total:
        return {'pairwise_reachability': float(all(s in match for s in ids)), 'pair_count': total,
                'false_connected_pairs': 0, 'false_disconnected_pairs': 0, 'unmapped_pairs': 0}
    tc, pc = component_ids(truth), component_ids(predicted)
    correct = false_positive = false_negative = unknown = 0
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            if a not in match or b not in match:
                unknown += 1
                continue
            expected = tc[a] == tc[b]
            got = pc[match[a]] == pc[match[b]]
            correct += expected == got
            false_positive += not expected and got
            false_negative += expected and not got
    return {'pairwise_reachability': correct/total, 'pair_count': total,
            'false_connected_pairs': false_positive, 'false_disconnected_pairs': false_negative,
            'unmapped_pairs': unknown}


def opening_metrics(source, predicted, match, radius=1.):
    """One-to-one opening matches; a nearby door cannot satisfy two source doors."""
    inverse = {v: k for k, v in match.items()}
    truth = source.get('openings', [])
    got = predicted.get('openings', [])
    distances = np.full((len(truth), len(got)), 1e9)
    wrong_adjacency = 0
    for j, door in enumerate(got):
        mapped = [inverse.get(s, 'outside' if s == 'outside' else None) for s in door['space_ids']]
        pair = frozenset(mapped)
        adjacent_truth = [i for i, expected in enumerate(truth) if frozenset(expected['space_ids']) == pair and None not in pair]
        if not adjacent_truth:
            wrong_adjacency += 1
        for i in adjacent_truth:
            distance = math.dist(door['position'], truth[i]['position'])
            if distance <= radius:
                distances[i, j] = distance
    hits = []
    if distances.size:
        rows, cols = linear_sum_assignment(distances)
        hits = [(int(i), int(j)) for i, j in zip(rows, cols) if distances[i, j] <= radius]
    matched_true = {i for i, _ in hits}
    matched_pred = {j for _, j in hits}
    return {'door_recall': ratio(len(hits), len(truth)), 'door_precision': ratio(len(hits), len(got)),
            'doors_true': len(truth), 'doors_predicted': len(got), 'doors_matched': len(hits),
            'missed_doors': [d['id'] for i, d in enumerate(truth) if i not in matched_true],
            'invented_doors': [d['id'] for j, d in enumerate(got) if j not in matched_pred],
            'wrong_adjacency_count': wrong_adjacency}


def measure(source, predicted, threshold=.5):
    truth = {s['id']: polygon(s['polygon']) for s in source['spaces']}
    rebuilt = {s['id']: polygon(s['polygon']) for s in predicted['spaces']}
    # Stacked identical outlines must never match rooms on different floors.
    source_levels = {f['id']: f['level'] for f in source['floors']}
    predicted_levels = {f['id']: f['level'] for f in predicted['floors']}
    match, ious, merged, split = {}, [], 0, 0
    for level in set(source_levels.values()) | set(predicted_levels.values()):
        left = {s['id']: truth[s['id']] for s in source['spaces'] if source_levels[s['floor_id']] == level}
        right = {s['id']: rebuilt[s['id']] for s in predicted['spaces'] if predicted_levels[s['floor_id']] == level}
        pairs, scores, merges, splits = match_spaces(left, right, threshold)
        match.update(pairs); ious.extend(scores); merged += merges; split += splits
    metrics = {'room_recall': ratio(len(match), len(truth)), 'room_precision': ratio(len(match), len(rebuilt)),
               'mean_iou': sum(ious)/len(ious) if ious else 0., 'spaces_true': len(truth),
               'spaces_rebuilt': len(rebuilt), 'missing_rooms': sorted(set(truth)-set(match)),
               'invented_rooms': sorted(set(rebuilt)-set(match.values())),
               'merged_region_count': merged, 'split_region_count': split}
    metrics.update(opening_metrics(source, predicted, match))
    tg, pg = adjacency(source), adjacency(predicted)
    metrics.update(pair_agreement(tg, pg, match))
    inverse = {v: k for k, v in match.items()}
    expected = {frozenset(edge) for edge in tg.edges}
    actual = {frozenset(inverse.get(s, 'unmatched:'+s) for s in edge) for edge in pg.edges}
    metrics['topology_recall'] = ratio(len(expected & actual), len(expected))
    metrics['topology_precision'] = ratio(len(expected & actual), len(actual))
    for step_free, suffix in [(False, ''), (True, '_step_free')]:
        truth_exits = adjacency(source, include_outside=True, step_free=step_free)
        pred_exits = adjacency(predicted, include_outside=True, step_free=step_free)
        tr = nx.node_connected_component(truth_exits, 'outside') if 'outside' in truth_exits else set()
        pr = nx.node_connected_component(pred_exits, 'outside') if 'outside' in pred_exits else set()
        metrics['exit_reachability_agreement'+suffix] = ratio(sum(s in match and ((s in tr) == (match[s] in pr)) for s in truth),len(truth))
        metrics['false_exit_access'+suffix] = sum(s in match and s not in tr and match[s] in pr for s in truth)
    metrics['matched_spaces'] = match
    return metrics


def quality(metrics, threshold=.9, complete=False):
    checks = ['room_recall', 'room_precision', 'door_recall', 'door_precision',
              'topology_recall', 'topology_precision', 'pairwise_reachability']
    if complete:
        checks += ['exit_reachability_agreement', 'exit_reachability_agreement_step_free']
    return all(metrics.get(k, 0.) >= threshold for k in checks) and not metrics.get('false_connected_pairs',0) and not metrics.get('false_exit_access',0) and not metrics.get('false_exit_access_step_free',0)
