import operator
import numpy as np
from interarray.geometric import is_same_side
from interarray.interarraylib import make_graph_metrics
import networkx as nx


def edgeXing_iter(u, v, G, A):
    '''This is broken, do not use!'''
    planar = A.graph['planar']
    _, s = A.next_face_half_edge(u, v)
    _, t = A.next_face_half_edge(v, u)
    if s == t:
        # <u, v> and the 3rd vertex are hull
        return
    if (s, t) in A.edges:
        # the diagonal conflicts with the Delaunay edge
        yield ((u, v), (s, t))
        conflicting = [(s, t)]
    else:
        conflicting = []
    # examine the two triangles (u, v) belongs to
    for a, b, c in ((u, v, s),
                    (v, u, t)):
        # this is for diagonals crossing diagonals
        triangle = tuple(sorted((a, b, c)))
        if triangle not in checked:
            checked.add(triangle)
            _, e = A.next_face_half_edge(c, b)
            if (a, e) in A.edges:
                conflicting.append((a, e))
            _, d = A.next_face_half_edge(a, c)
            if (b, d) in A.edges:
                conflicting.append((b, d))
            if len(conflicting) > 1:
                yield conflicting


def layout_edgeXing_iter(G, A):
    '''does this even make sense?'''
    for edge in G.edges:
        yield from edgeXing_iter(edge, G, A)


def edgeset_edgeXing_iter(A, include_roots=False):
    '''Iterator over all edge crossings in an expanded
    Delaunay edge set `A`. Each crossing is a 2 or 3-tuple
    of (u, v) edges.'''
    planar = A.graph['planar']
    checked = set()
    # iterate over all Delaunay edges
    for u, v in planar.edges:
        if u > v or (not include_roots and (u < 0 or v < 0)):
            # planar is a DiGraph, so skip one half-edge of the pair
            continue
        # get diagonal
        _, s = planar.next_face_half_edge(u, v)
        _, t = planar.next_face_half_edge(v, u)
        if s == t or (not include_roots and (s < 0 or t < 0)):
            # <u, v> and the 3rd vertex are hull
            continue
        triangles = []
        if (s, u) in planar.edges:
            triangles.append((u, v, s))
        if (t, v) in planar.edges:
            triangles.append((v, u, t))
        s, t = (s, t) if s < t else (t, s)
        has_diagonal = (s, t) in A.edges
        if has_diagonal:
            # the diagonal conflicts with the Delaunay edge
            yield ((u, v), (s, t))
        # examine the two triangles (u, v) belongs to
        for a, b, c in triangles:
            # this is for diagonals crossing diagonals
            triangle = tuple(sorted((a, b, c)))
            if triangle not in checked:
                checked.add(triangle)
                conflicting = [(s, t)] if has_diagonal else []
                _, e = planar.next_face_half_edge(c, b)
                if ((e, c) in planar.edges
                        and (a, e) in A.edges
                        and (include_roots or (a >= 0 and e >= 0))):
                    conflicting.append((a, e) if a < e else (e, a))
                _, d = planar.next_face_half_edge(a, c)
                if ((d, a) in planar.edges
                        and (b, d) in A.edges
                        and (include_roots or (b >= 0 and d >= 0))):
                    conflicting.append((b, d) if b < d else (d, b))
                if len(conflicting) > 1:
                    yield conflicting


# adapted edge_crossings() from geometric.py
# delaunay() does not create `triangles` and `triangles_exp`
# anymore, so this is broken
def edgeXing_iter_deprecated(A):
    '''
    This is broken, do not use!
    
    Iterates over all pairs of crossing edges in `A`. This assumes `A`
    has only expanded Delaunay edges (with triangles and triangles_exp).

    Used in constraint generation for MILP model.
    '''
    triangles = A.graph['triangles']
    # triangles_exp maps expanded Delaunay to Delaunay edges
    triangles_exp = A.graph['triangles_exp']
    checked = set()
    for uv, (s, t) in triangles_exp.items():
        # <(u, v) is an expanded Delaunay edge>
        u, v = uv
        checked.add(uv)
        if (u, v) not in A.edges:
            continue
        if (s, t) in A.edges:
            yield (((u, v) if u < v else (v, u)),
                   ((s, t) if s < t else (t, s)))
        else:
            # this looks wrong...
            # the only case where this might happen is
            # when a Delaunay edge is removed because of
            # the angle > pi/2 blocking of a root node
            # but even in this case, we should check for
            # crossings with other expanded edges
            continue
        for a_b in ((u, s), (u, t), (s, v), (t, v)):
            if a_b not in triangles:
                continue
            cd = triangles[frozenset(a_b)]
            if cd in checked:
                continue
            if (cd in triangles_exp
                    and tuple(cd) in A.edges
                    # this last condition is for edges that should have been
                    # eliminated in delaunay()'s hull_edge_is_overlapping(),
                    # but weren't
                    and set(triangles_exp[cd]) <= {u, v, s, t}):
                c, d = cd
                yield (((u, v) if u < v else (v, u)),
                       ((c, d) if c < d else (d, c)))


def gateXing_iter(A, all_gates=True, touch_is_cross=True):
    '''
    Iterate over all crossings between non-gate edges and gate edges of `A`.
    If `A` does not include gates, all nodes will be considered as gates.
    Arguments:
    - all_gates: if True, consider all nodes as gates, otherwise use A's gates

    Used in constraint generation for MILP model.
    '''
    M = A.graph['M']
    roots = tuple(range(-M, 0))
    VertexC = A.graph['VertexC']
    anglesRank = A.graph.get('anglesRank', None)
    if anglesRank is None:
        make_graph_metrics(A)
        anglesRank = A.graph['anglesRank']
    anglesXhp = A.graph['anglesXhp']
    anglesYhp = A.graph['anglesYhp']
    # iterable of non-gate edges:
    Edge = nx.subgraph_view(A, filter_node=lambda n: n >= 0).edges()
    if all_gates or sum(A.degree(r) for r in roots) == 0:
        # consider gates from all nodes
        IGate = (slice(None),)*M
    else:
        # only consider as gates the nodes connected to a root
        IGate = tuple(list(A.neighbors(r)) for r in roots)
    # it is important to consider touch as crossing
    # because if a gate goes precisely through a node
    # there will be nothing to prevent it from spliting
    # that node's subtree
    less = operator.le if touch_is_cross else operator.lt
    for u, v in Edge:
        uC = VertexC[u]
        vC = VertexC[v]
        for root, iGate in zip(roots, IGate):
            rootC = VertexC[root]
            uR, vR = anglesRank[u, root], anglesRank[v, root]
            highRank, lowRank = (uR, vR) if uR >= vR else (vR, uR)
            Xhp = anglesXhp[[u, v], root]
            uYhp, vYhp = anglesYhp[[u, v], root]
            # get a vector of gate edges' ranks for current root
            gaterank = anglesRank[iGate, root]
            # check if angle of <u, v> wraps across +-pi
            if (not any(Xhp)) and uYhp != vYhp:
                # <u, v> wraps across zero
                is_rank_within = np.logical_or(less(gaterank, lowRank),
                                               less(highRank, gaterank))
            else:
                # <u, v> does not wrap across zero
                is_rank_within = np.logical_and(less(lowRank, gaterank),
                                                less(gaterank, highRank))
            for n in np.flatnonzero(is_rank_within):
                if not isinstance(iGate, slice):
                    n = iGate[n]
                if not is_same_side(uC, vC, rootC, VertexC[n]):
                    u, v = (u, v) if u < v else (v, u)
                    yield u, v, root, n
