"""Widening intervals for metric-scale uncertainty (image-only tiers)."""
import numpy as np


def widen_for_scale(polys, heights, openings, s: float) -> None:
    """Add a relative 1-sigma scale error `s` to every measurement.

    Scale error is fully correlated within a reconstruction, so it is added to
    each length (in quadrature with its geometric error) rather than averaged.
    """
    for poly in polys:
        poly.length_sigmas = [float(np.hypot(sg, s * L)) for L, sg in zip(poly.lengths, poly.length_sigmas)]
        poly.area_sigma = float(np.hypot(poly.area_sigma, 2 * s * poly.area))
    for h in heights:
        if h.ceiling is not None:
            h.ceiling.sigma = float(np.hypot(h.ceiling.sigma, s * h.height))
    for o in openings:
        o.width_sigma = float(np.hypot(o.width_sigma, s * o.width))
