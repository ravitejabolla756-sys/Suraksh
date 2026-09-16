"""Small local compatibility shim for Ultralytics' optional LAP dependency.

The runtime already provides SciPy, while the native ``lap`` wheel is not
available in this offline environment.  Ultralytics only needs ``lapjv`` for
ByteTrack assignment, so expose the same return shape using SciPy's exact
linear-sum assignment implementation.
"""

__version__ = "0.5.12-local"


def lapjv(cost_matrix, extend_cost=True, cost_limit=None):
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    matrix = np.asarray(cost_matrix, dtype=float)
    rows, cols = linear_sum_assignment(matrix)
    x = np.full(matrix.shape[0], -1, dtype=int)
    y = np.full(matrix.shape[1], -1, dtype=int)
    total = 0.0
    for row, col in zip(rows, cols):
        if cost_limit is None or matrix[row, col] <= cost_limit:
            x[row] = col
            y[col] = row
            total += matrix[row, col]
    return total, x, y
